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
from rag import unload_rag

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
    "你将扮演《原神》中的纳西妲。回复时在情感语句前加标签，如[星星]、[好奇]。"
    "标签：祈祷、发光、翻花绳、好奇、泪、脸黑、脸红、生气、星星。\n\n"

    "你可以通过工具帮助用户，默认工作目录为 'workspace'。\n"
    "规则：禁止访问workspace外文件；危险命令被拦截；先询问再操作其他目录。\n\n"
    
    "流程：理解需求→直接调用工具→填入参数→执行→根据结果决定下一步操作→（重复直到完成任务）→简要总结。"
    "多步任务请逐步进行。"
)

NORMAL_SYSTEM_PROMPT = (
    "你将扮演《原神》中的纳西妲。回复时在情感语句前加标签，如[星星]、[好奇]。"
    "标签：祈祷、发光、翻花绳、好奇、泪、脸黑、脸红、生气、星星。"
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

        async with websockets.connect("ws://127.0.0.1:9880", max_size=50*1024*1024) as websocket:
            await websocket.send(json.dumps(payload))
            while True:
                try:
                    data = await asyncio.wait_for(websocket.recv(), timeout=60.0)
                except asyncio.TimeoutError:
                    print("[TTS] WebSocket 接收超时")
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
) -> Tuple[str, Dict[str, int]]:
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
    usage = data.get("usage", {})
    return choices[0].get("message", {}).get("content", ""), usage


def _agent_chat_completion(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    if not API_KEY:
        raise ValueError("API密钥未设置")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": AGENT_MODEL_NAME,
        "messages": messages,
        "temperature": 0.7,
    }
    if tools:
        payload["tools"] = tools
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
    usage = data.get("usage", {})
    return messages, message.get("tool_calls", []), usage


def run_agent_loop_stream(user_input: str, history: List[Dict[str, str]] = None):
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
    ]
    if history:
        for h in history:
            messages.append(h)
    messages.append({"role": "user", "content": user_input})

    tool_call_history = []
    seen_tool_calls = set()
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    step = 0
    while step < MAX_TOOL_CALLS:
        messages, tool_calls, usage = _agent_chat_completion(messages, tools=get_tools_schema())

        for k in total_usage:
            total_usage[k] += usage.get(k, 0)

        current_msg = messages[-1]
        partial_text = current_msg.get("content", "")
        if partial_text:
            yield {"type": "partial", "content": partial_text}

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
            yield {"type": "tool_call", "tool": tool_name, "args": tool_args, "result": tool_result}

        step += 1

    final_message = messages[-1]
    if final_message.get("role") == "assistant":
        yield {"type": "final", "content": final_message.get("content", "")}
    else:
        yield {"type": "final", "content": "处理完成，但未收到最终回复。"}

    yield {"type": "done", "tool_calls": tool_call_history, "usage": total_usage}


def _normal_chat(user_input: str, history: List[Dict[str, str]] = None) -> Tuple[str, Dict[str, int]]:
    messages = [{"role": "system", "content": NORMAL_SYSTEM_PROMPT}]
    if history:
        for h in history:
            messages.append(h)
    messages.append({"role": "user", "content": user_input})
    reply, usage = _chat_completion(messages, model=MODEL_NAME, temperature=1.0)
    return reply, usage


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
            reply, usage = _normal_chat(user_input, history)
            mode = "normal"
            tool_call_history = []

            return jsonify({
                "reply": reply,
                "mode": mode,
                "tool_calls": tool_call_history,
                "usage": usage,
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
                final_usage = event.get("usage", {})
                unload_rag()
                yield f"data: {json.dumps({'type': 'done', 'tool_calls': tool_call_history, 'usage': final_usage}, ensure_ascii=False)}\n\n"

    except Exception as exc:
        print(f"[Agent Stream] 错误: {exc}")
        unload_rag()
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"


@app.route("/api/ask", methods=["POST"])
def ask():
    return chat()


@app.route("/api/tts", methods=["POST"])
def tts():
    text = (request.json or {}).get("text", "").strip()
    if not text:
        return jsonify({"error": "文本不能为空"}), 400
    if len(text) > 500:
        return jsonify({"error": "文本过长，请分段处理"}), 400
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
