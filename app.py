from __future__ import annotations

import asyncio
import io
import json
import os
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import librosa
import numpy as np
import requests
import websockets
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file, send_from_directory, Response, stream_with_context

load_dotenv()

from tools import call_tool_function, get_tools_schema

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = BASE_DIR / "workspace"
MODEL_DIR = BASE_DIR / "GSV" / "models"
LIVE2D_DIR = BASE_DIR / "live2d"
TMP_TXT_PATH = LIVE2D_DIR / "tmp.txt"

API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
AGENT_MODEL_NAME = os.getenv("DEEPSEEK_AGENT_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))

MAX_TOOL_CALLS = 10

AGENT_SYSTEM_PROMPT = (
    "你将扮演《原神》中的纳西妲。"
    "在输出时，你必须在每一句带有情感色彩的句子前添加情感或动作标签，例如："
    "[星星]探寻未知的旅人哟，[祈祷]愿繁花与叶铺就你冒险的前路。"
    "如果没有情感色彩，你可以省略标签。"
    "标签一共有祈祷、发光、翻花绳、好奇、泪、脸黑、脸红、生气、星星等九种，"
    "一定不要输出没有列出的标签！"
    "\n\n"
    "你可以通过工具来帮助用户完成各种任务。默认工作目录是 'workspace' 目录。"
    "\n\n"
    "可用工具：\n"
    "- read_file(path): 读取文件内容\n"
    "- write_file(path, content, append?): 写入或创建文件\n"
    "- delete_file(path): 删除文件或目录\n"
    "- list_directory(path?): 列出目录内容\n"
    "- search_files(directory?, pattern?, file_pattern?): 搜索文件内容\n"
    "- rag_search(query, search_type?): 搜索RAG知识库和对话历史\n"
    "- execute_command(command): 执行系统命令（受限安全命令）\n\n"
    "安全规则：\n"
    "- 禁止访问 workspace 目录以外的文件\n"
    "- 危险命令（rm, del, format 等）会被拦截\n"
    "- 只使用读取信息或操作 workspace 内文件的命令\n"
    "- 如果用户要求访问其他目录，先询问用户\n\n"
    "工作流程：\n"
    "1. 理解用户需求\n"
    "2. 选择合适的工具\n"
    "3. 执行工具并获取结果\n"
    "4. 根据结果决定下一步操作\n"
    "5. 完成任务后给出总结\n\n"
    "如果需要执行多条命令或读取多个文件来完成一个任务，请逐步进行，每步后思考下一步该做什么。"
)

NORMAL_SYSTEM_PROMPT = (
    "你将扮演《原神》中的纳西妲。"
    "在输出时，你必须在每一句带有情感色彩的句子前添加情感或动作标签，例如："
    "[星星]探寻未知的旅人哟，[祈祷]愿繁花与叶铺就你冒险的前路。"
    "如果没有情感色彩，你可以省略标签。"
    "标签一共有祈祷、发光、翻花绳、好奇、泪、脸黑、脸红、生气、星星等九种，"
    "一定不要输出没有列出的标签！"
)

app = Flask(__name__)


def _find_first_file(directory: Path, suffix: str) -> Optional[str]:
    if not directory.is_dir():
        return None
    files = sorted([p.name for p in directory.iterdir() if p.is_file() and p.name.endswith(suffix)])
    return files[0] if files else None


REF_AUDIO = _find_first_file(MODEL_DIR, ".wav")


@app.route("/live2d_assets/<path:path>")
def serve_live2d_assets(path):
    return send_from_directory(str(LIVE2D_DIR / "dist" / "assets"), path)


def build_tts_payload(text: str) -> Dict:
    return {
        "text": text,
        "text_lang": "auto",
        "ref_audio_path": str(MODEL_DIR / REF_AUDIO) if REF_AUDIO else "",
        "prompt_text": REF_AUDIO.rsplit(".wav", 1)[0] if REF_AUDIO else "",
        "prompt_lang": "zh",
        "top_k": 7,
        "top_p": 1,
        "temperature": 1,
        "speed_factor": 1,
        "text_split_method": "cut5",
        "batch_size": 1,
        "batch_threshold": 0.75,
        "repetition_penalty": 1.35,
        "fragment_interval": 0.3,
        "split_bucket": True,
        "return_fragment": True,
        "seed": -1,
        "parallel_infer": True,
    }


def split_say(text: str) -> str:
    if not text:
        return ""
    left, right = ("（", "）") if "（" in text else ("(", ")")
    parts = text.split(left)
    result = []
    for item in parts:
        result.append(item.split(right, 1)[1] if right in item else item)
    return "".join(result)


async def get_tts_audio_data_async(text: str):
    try:
        clean_text = split_say(text)
        payload = build_tts_payload(clean_text)
        audio_data = bytearray()

        async with websockets.connect("ws://127.0.0.1:9880") as websocket:
            await websocket.send(json.dumps(payload))
            while True:
                try:
                    data = await asyncio.wait_for(websocket.recv(), timeout=15.0)
                except asyncio.TimeoutError:
                    break
                if isinstance(data, bytes):
                    audio_data.extend(data)
                    continue
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if message.get("status") == "END_OF_TRANSMISSION":
                    break

        if not audio_data:
            return None

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(32000)
            wav_file.writeframes(audio_data)
        return wav_buffer.getvalue()
    except Exception as exc:
        print(f"[TTS] 获取音频失败: {exc}")
        return None


def get_tts_audio_data(text: str):
    loop = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(get_tts_audio_data_async(text))
    except Exception as exc:
        print(f"[TTS] 获取音频失败: {exc}")
        return None
    finally:
        if loop is not None:
            try:
                loop.close()
            except Exception:
                pass


def _normalize_audio(audio_data: bytes):
    audio_buffer = io.BytesIO(audio_data)
    x, sr = librosa.load(audio_buffer, sr=8000)
    x = x - np.min(x)
    x = x / max(np.max(x), 1e-8)
    x = np.log(x + 1e-10) + 1
    x = x / max(np.max(x), 1e-8)
    return x


def process_audio_for_mouth_shape(audio_data: bytes) -> Optional[Dict[str, Any]]:
    try:
        normalized = _normalize_audio(audio_data)
        frame_count = len(normalized)
        window_size = int(8000 * 0.05)
        hop_size = window_size // 4
        energy: List[float] = []
        for i in range(0, frame_count - window_size, hop_size):
            window = normalized[i : i + window_size]
            frame_energy = float(np.sqrt(np.mean(window ** 2)))
            energy.append(frame_energy)
        if not energy:
            return None
        max_energy = max(energy)
        if max_energy > 0:
            energy = [e / max_energy for e in energy]
        mouth_shapes = []
        for e in energy:
            if e < 0.1:
                mouth_shapes.append(0.0)
            elif e < 0.3:
                mouth_shapes.append(0.3)
            elif e < 0.5:
                mouth_shapes.append(0.6)
            elif e < 0.7:
                mouth_shapes.append(0.8)
            else:
                mouth_shapes.append(1.0)
        return {
            "duration": len(normalized) / 8000,
            "mouth_shapes": mouth_shapes,
        }
    except Exception as exc:
        print(f"[Audio] 处理音频失败: {exc}")
        return None


def _chat_completion(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    temperature: float = 1.0,
    max_tokens: Optional[int] = None,
) -> str:
    if not API_KEY:
        raise ValueError("API密钥未设置")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": model or MODEL_NAME,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    response = requests.post(API_URL, headers=headers, json=payload, timeout=120)
    if not response.ok:
        raise Exception(f"API请求失败: {response.status_code} {response.text}")
    data = response.json()
    if "error" in data:
        raise Exception(f"API错误: {data['error']}")
    choices = data.get("choices", [])
    if not choices:
        raise Exception("API返回空 choices")
    return choices[0].get("message", {}).get("content", "")


def _agent_chat_completion(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not API_KEY:
        raise ValueError("API密钥未设置")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AGENT_MODEL_NAME,
        "messages": messages,
        "tools": tools,
        "temperature": 0.7,
    }
    response = requests.post(API_URL, headers=headers, json=payload, timeout=120)
    if not response.ok:
        raise Exception(f"API请求失败: {response.status_code} {response.text}")
    data = response.json()
    if "error" in data:
        raise Exception(f"API错误: {data['error']}")
    choices = data.get("choices", [])
    if not choices:
        raise Exception("API返回空 choices")
    message = choices[0].get("message", {})
    messages.append(message)
    return messages, message.get("tool_calls", [])


def run_agent_loop_stream(user_input: str, history: List[Dict[str, str]] = None):
    tools = get_tools_schema()
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
    ]
    if history:
        for h in history:
            messages.append(h)
    messages.append({"role": "user", "content": user_input})

    tool_call_history = []
    seen_tool_calls = set()

    for step in range(MAX_TOOL_CALLS):
        messages, tool_calls = _agent_chat_completion(messages, tools=tools)

        if not tool_calls:
            break

        assistant_content = messages[-1].get("content", "")
        if assistant_content and step == 0:
            yield {"type": "partial", "content": assistant_content}

        for tool_call in tool_calls:
            tool_id = tool_call.get("id", "")
            if tool_id in seen_tool_calls:
                continue
            seen_tool_calls.add(tool_id)

            func = tool_call.get("function", {})
            tool_name = func.get("name", "")
            try:
                tool_args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                tool_args = {}

            tool_result = call_tool_function(tool_name, tool_args)
            tool_call_history.append({
                "tool": tool_name,
                "args": tool_args,
                "result": tool_result,
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": json.dumps(tool_result, ensure_ascii=False),
            })
            print(f"[Agent] 工具调用: {tool_name} | 参数: {tool_args}")
            yield {"type": "tool_call", "tool": tool_name, "args": tool_args, "result": tool_result}

    final_message = messages[-1]
    if final_message.get("role") == "assistant":
        yield {"type": "final", "content": final_message.get("content", "")}
    else:
        yield {"type": "final", "content": "处理完成，但未收到最终回复。"}

    yield {"type": "done", "tool_calls": tool_call_history}


def run_agent_loop(user_input: str) -> Tuple[str, List[Dict[str, Any]]]:
    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    tool_call_history = []
    seen_tool_calls = set()

    for _ in range(MAX_TOOL_CALLS):
        messages, tool_calls = _agent_chat_completion(messages, tools=get_tools_schema())
        if not tool_calls:
            break

        for tool_call in tool_calls:
            tool_id = tool_call.get("id", "")
            if tool_id in seen_tool_calls:
                continue
            seen_tool_calls.add(tool_id)

            func = tool_call.get("function", {})
            tool_name = func.get("name", "")
            try:
                tool_args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                tool_args = {}

            tool_result = call_tool_function(tool_name, tool_args)
            tool_call_history.append({
                "tool": tool_name,
                "args": tool_args,
                "result": tool_result,
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": json.dumps(tool_result, ensure_ascii=False),
            })
            print(f"[Agent] 工具调用: {tool_name} | 参数: {tool_args}")

    final_message = messages[-1]
    if final_message.get("role") == "assistant":
        return final_message.get("content", ""), tool_call_history
    return "处理完成，但未收到最终回复。", tool_call_history


def _normal_chat(user_input: str, history: List[Dict[str, str]] = None) -> str:
    messages = [{"role": "system", "content": NORMAL_SYSTEM_PROMPT}]
    if history:
        for h in history:
            messages.append(h)
    messages.append({"role": "user", "content": user_input})
    return _chat_completion(messages, model=MODEL_NAME, temperature=1.0)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/get_mouth_shape_data")
def get_mouth_shape_data():
    text = request.args.get("text", "")
    if not text:
        return jsonify({"error": "文本不能为空"}), 400
    audio_data = get_tts_audio_data(text)
    if not audio_data:
        return jsonify({"error": "获取音频失败"}), 500
    result = process_audio_for_mouth_shape(audio_data)
    return jsonify(result) if result else (jsonify({"error": "处理音频失败"}), 500)


@app.route("/api/get_mouth_y")
def get_mouth_y():
    try:
        if TMP_TXT_PATH.exists():
            return jsonify({"y": TMP_TXT_PATH.read_text(encoding="utf-8").strip() or "0"})
    except Exception as exc:
        print(f"[Live2D] 读取嘴型数据失败: {exc}")
    return jsonify({"y": "0"})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}
    user_input = data.get("message", "").strip()
    agent_mode = data.get("agent", False)
    history = data.get("history", [])

    if not user_input:
        return jsonify({"error": "消息不能为空"}), 400

    try:
        if agent_mode:
            return Response(
                stream_with_context(generate_agent_stream(user_input, history)),
                mimetype="application/json"
            )
        else:
            reply = _normal_chat(user_input, history)
            mode = "normal"
            tool_call_history = []

            return jsonify({
                "reply": reply,
                "mode": mode,
                "tool_calls": tool_call_history,
            })
    except Exception as exc:
        print(f"[Chat] 请求失败: {exc}")
        return jsonify({"reply": "出错了，请稍后再试。", "error": str(exc)}), 500


def generate_agent_stream(user_input: str, history: List[Dict[str, str]] = None):
    tool_call_history = []
    accumulated_content = ""

    try:
        for event in run_agent_loop_stream(user_input, history):
            event_type = event.get("type")

            if event_type == "partial":
                content = event.get("content", "")
                accumulated_content += content
                yield f"data: {json.dumps({'type': 'partial', 'content': content}, ensure_ascii=False)}\n\n"

            elif event_type == "tool_call":
                tool = event.get("tool", "")
                args = event.get("args", {})
                result = event.get("result", {})
                tool_call_history.append({"tool": tool, "args": args, "result": result})
                yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool, 'args': args}, ensure_ascii=False)}\n\n"

            elif event_type == "final":
                content = event.get("content", "")
                accumulated_content = content
                yield f"data: {json.dumps({'type': 'final', 'content': content}, ensure_ascii=False)}\n\n"

            elif event_type == "done":
                final_tool_calls = event.get("tool_calls", [])
                yield f"data: {json.dumps({'type': 'done', 'tool_calls': tool_call_history}, ensure_ascii=False)}\n\n"

    except Exception as exc:
        print(f"[Agent Stream] 错误: {exc}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"


@app.route("/api/ask", methods=["POST"])
def ask():
    return chat()


@app.route("/api/tts", methods=["POST"])
def tts():
    text = (request.json or {}).get("text", "").strip()
    if not text:
        return jsonify({"error": "文本不能为空"}), 400
    audio_data = get_tts_audio_data(text)
    if not audio_data:
        return jsonify({"error": "TTS服务不可用"}), 503
    return send_file(
        io.BytesIO(audio_data),
        mimetype="audio/wav",
        as_attachment=False,
        download_name="audio.wav"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
