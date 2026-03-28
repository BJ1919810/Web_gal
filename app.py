from __future__ import annotations

import asyncio
import io
import json
import os
import re
import threading
import time
import wave
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import librosa
import numpy as np
import requests
import websockets
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, send_from_directory

load_dotenv()

from memory import get_memory_context, update_memory
from rag import init_rag, search_context

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "GSV" / "models"
LIVE2D_DIR = BASE_DIR / "live2d"
TMP_TXT_PATH = LIVE2D_DIR / "tmp.txt"

API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

MAX_HISTORY_MESSAGES = 20
DIALOGUE_TOP_K = 3
KNOWLEDGE_TOP_K = 4

BASE_SYSTEM_PROMPT = (
    "你将扮演《原神》中的纳西妲。"
    "在输出时，你必须在每一句带有情感色彩的句子前添加情感或动作标签，例如："
    "“[星星]探寻未知的旅人哟，[祈祷]愿繁花与叶铺就你冒险的前路。”"
    "如果没有情感色彩，你可以省略标签。"
    "标签一共有祈祷、发光、翻花绳、好奇、泪、脸黑、脸红、生气、星星等九种，"
    "一定不要输出没有列出的标签！"
    "当知识库提供了相关的故事或背景信息时，请详细描述，展开叙述，不要只输出简短的几句话。"
)

GREETING_TERMS = {
    "你好", "您好", "嗨", "哈喽", "hello", "hi", "嘿", "早上好", "中午好", "下午好", "晚上好",
    "安安", "在吗", "在嘛", "又见面啦", "又见面了", "晚安", "早安",
}
SOCIAL_SHORT_TERMS = {
    "谢谢", "多谢", "辛苦了", "好的", "好耶", "哈哈", "哈哈哈", "嗯", "嗯嗯", "好哦", "收到",
    "我来了", "想你了", "抱抱", "贴贴",
}
DIALOGUE_CUES = (
    "又见面", "还记得", "上次", "之前", "刚才", "你说过", "我们聊到", "我们刚聊过", "还认识我", "我是",
)
KNOWLEDGE_VERBS = (
    "关于", "是什么", "什么意思", "为什么", "怎么", "怎么办", "如何", "怎么样", "怎么了", "近况", "背景",
    "故事", "设定", "关系", "原因", "经过", "发生了什么", "谁是", "哪位", "介绍", "讲讲", "说说",
)
KNOWLEDGE_ENTITIES = (
    "纳西妲", "须弥", "迪娜泽黛", "花神诞日", "教令院", "流浪者", "阿佩普", "大慈树王", "魔鳞病",
    "提瓦特", "旅行者", "赤王", "世界树", "净善宫",
)
QUESTION_WORDS = ("什么", "为什么", "怎么", "如何", "谁", "哪", "吗", "呢", "？", "?")

app = Flask(__name__)
history = [{"role": "system", "content": BASE_SYSTEM_PROMPT}]


def _find_first_file(directory: Path, suffix: str) -> Optional[str]:
    if not directory.is_dir():
        return None
    files = sorted([p.name for p in directory.iterdir() if p.is_file() and p.name.endswith(suffix)])
    return files[0] if files else None


REF_AUDIO = _find_first_file(MODEL_DIR, ".wav")


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
            print("[TTS] 未收到音频数据")
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
    x = x * 1.2
    return x, sr


def process_audio_for_mouth_shape(audio_data: bytes):
    try:
        x, sr = _normalize_audio(audio_data)
        duration = len(x) / sr
        sample_interval = max(int(sr / 30), 1)
        mouth_shape_data = []
        for i in range(0, len(x), sample_interval):
            segment = x[i: i + sample_interval]
            value = float(max(np.max(segment), 0)) if len(segment) else 0.0
            mouth_shape_data.append(value)
        return {"duration": float(duration), "mouth_shape_data": mouth_shape_data}
    except Exception as exc:
        print(f"[Live2D] 音频处理失败: {exc}")
        return None


def play_audio_and_update_mouth(audio_data: bytes):
    try:
        x, _ = _normalize_audio(audio_data)
        start_time = time.time()
        for _ in range(int(len(x) / 800)):
            current_idx = int((time.time() - start_time) * 8000) + 1
            if 0 <= current_idx < len(x):
                TMP_TXT_PATH.write_text(str(float(max(0, x[current_idx]))), encoding="utf-8")
            time.sleep(0.1)
    except Exception as exc:
        print(f"[Live2D] 更新嘴型失败: {exc}")
    finally:
        TMP_TXT_PATH.write_text("0", encoding="utf-8")


def _chat_completion(messages: List[Dict[str, str]], *, temperature: float = 0.2, max_tokens: Optional[int] = None) -> str:
    if not API_KEY:
        raise RuntimeError("未设置 DEEPSEEK_API_KEY")
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    result = response.json()
    return result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


def call_chat_api(messages: List[Dict[str, str]]) -> str:
    result = _chat_completion(messages, temperature=0.7)
    return result or "出错了，请稍后再试。"


def _normalize_route_text(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", "", text)
    return text


def _looks_like_pure_greeting(text: str) -> bool:
    normalized = _normalize_route_text(text)
    normalized = re.sub(r"[~～!！,.，。…]+", "", normalized)
    if not normalized:
        return False
    if normalized in GREETING_TERMS or normalized in SOCIAL_SHORT_TERMS:
        return True
    found_parts = re.findall(r"你好|您好|嗨|哈喽|hello|hi|嘿|早上好|中午好|下午好|晚上好|在吗|在嘛|又见面啦|又见面了|晚安|早安|呀|啊|啦|呢|哦|哟", normalized)
    if found_parts and all(part in GREETING_TERMS or part in {"呀", "啊", "啦", "呢", "哦", "哟"} for part in found_parts):
        return True
    return False


def _has_knowledge_signal(text: str) -> bool:
    normalized = _normalize_route_text(text)
    if any(term in normalized for term in KNOWLEDGE_VERBS):
        return True
    if any(mark in text for mark in QUESTION_WORDS) and any(entity in text for entity in KNOWLEDGE_ENTITIES):
        return True
    if any(entity in text for entity in KNOWLEDGE_ENTITIES) and any(verb in normalized for verb in ("近况", "背景", "故事", "设定", "关系", "怎么样", "怎么了", "介绍", "讲讲", "说说")):
        return True
    return False


def _has_dialogue_signal(text: str) -> bool:
    normalized = _normalize_route_text(text)
    return any(cue in normalized for cue in DIALOGUE_CUES)


def rule_route_context(user_input: str) -> Tuple[Optional[str], str]:
    text = user_input.strip()
    normalized = _normalize_route_text(text)
    plain_len = len(normalized)

    if not normalized:
        return "none", "空输入"

    if _looks_like_pure_greeting(text):
        return "dialogue_only", "规则命中：纯寒暄/招呼"

    if _has_knowledge_signal(text):
        return "knowledge", "规则命中：明确知识/设定问题"

    if _has_dialogue_signal(text) and not _has_knowledge_signal(text):
        return "dialogue_only", "规则命中：承接旧对话"

    if plain_len <= 8 and not any(mark in text for mark in "?？") and not any(entity in text for entity in KNOWLEDGE_ENTITIES):
        return "dialogue_only", "规则命中：超短社交语句"

    if plain_len <= 14 and any(term in normalized for term in SOCIAL_SHORT_TERMS) and not any(entity in text for entity in KNOWLEDGE_ENTITIES):
        return "dialogue_only", "规则命中：短社交反馈"

    return None, "灰区，交给LLM路由"


def llm_route_context(user_input: str) -> Tuple[str, str]:
    system_prompt = (
        "你是一个对话路由器。你必须把用户输入分到以下三类之一：\n"
        "1. none：不需要旧对话，也不需要知识库；\n"
        "2. dialogue_only：需要依赖角色长期记忆与旧对话承接语气/关系，但不需要知识资料；\n"
        "3. knowledge：需要知识库资料来回答设定、事实、背景、人物近况、事件经过等问题。\n\n"
        "严格规则：\n"
        "- 寒暄、打招呼、再次见面、简短情绪表达，通常是 dialogue_only，不是 knowledge。\n"
        "- 不能因为重复出现‘你好’‘嗨’‘我们又见面了’就判成 knowledge。\n"
        "- 只有当用户真的在问设定、背景、原因、人物近况、事件经过等信息时，才判为 knowledge。\n"
        "- 只返回一行 JSON，例如：{\"route\":\"dialogue_only\",\"reason\":\"寒暄承接\"}"
    )
    user_prompt = (
        "请判断这句用户输入属于哪一类。\n"
        f"用户输入：{user_input}\n\n"
        "例子：\n"
        "- ‘你好呀，我们又见面啦’ -> dialogue_only\n"
        "- ‘迪娜泽黛现在怎么样了’ -> knowledge\n"
        "- ‘花神诞日为什么会轮回’ -> knowledge\n"
        "- ‘哈哈，谢谢你’ -> dialogue_only"
    )
    try:
        content = _chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=80,
        )
        match = re.search(r"\{.*\}", content, flags=re.S)
        if match:
            data = json.loads(match.group())
            route = data.get("route", "dialogue_only")
            if route not in {"none", "dialogue_only", "knowledge"}:
                route = "dialogue_only"
            return route, f"LLM路由：{data.get('reason', '').strip() or '未提供原因'}"
    except Exception as exc:
        print(f"[Route] LLM 路由失败: {exc}")
    return "dialogue_only", "LLM路由失败，回退为 dialogue_only"


def route_context(user_input: str) -> Tuple[str, str]:
    route, reason = rule_route_context(user_input)
    if route is not None:
        return route, reason
    return llm_route_context(user_input)


def _format_retrieved_items(title: str, items: List[Dict]) -> str:
    if not items:
        return f"[{title}]\n- 无"
    lines = [f"[{title}]"]
    for idx, item in enumerate(items, start=1):
        source = item.get("source", "unknown")
        lines.append(f"- 来源{idx}: {source}")
        lines.append((item.get("content") or "").strip())
    return "\n".join(lines)


def build_system_prompt(base_prompt: str, memory_context: str, rag_context: Dict[str, List[Dict]]) -> str:
    parts = [
        base_prompt,
        "请按以下优先级使用上下文：[Agent] 是长期核心记忆，优先遵循；"
        "[Old Dialogue] 是历史对话片段，只用于回忆用户过往信息与语境，不要把明显过时或随口一说的内容当成硬事实；"
        "[Knowledge] 是资料库内容，用于补充设定、背景和事实。",
    ]
    if memory_context:
        parts.append(f"[Agent]\n{memory_context}")
    parts.append(_format_retrieved_items("Old Dialogue", rag_context.get("old_dialogue", [])))
    parts.append(_format_retrieved_items("Knowledge", rag_context.get("knowledge", [])))
    return "\n\n".join(parts)


@app.route("/live2d_assets/<path:path>")
def serve_live2d_assets(path):
    return send_from_directory(str(LIVE2D_DIR / "dist" / "assets"), path)


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


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/ask", methods=["POST"])
def ask():
    user_input = (request.json or {}).get("message", "").strip()
    if not user_input:
        return jsonify({"error": "消息不能为空"}), 400

    route, route_reason = route_context(user_input)
    init_rag()

    dialogue_top_k = DIALOGUE_TOP_K if route in {"dialogue_only", "knowledge"} else 0
    knowledge_top_k = KNOWLEDGE_TOP_K if route == "knowledge" else 0
    rag_context = search_context(
        user_input,
        dialogue_top_k=dialogue_top_k,
        knowledge_top_k=knowledge_top_k,
    )
    memory_context = get_memory_context()

    print(f"[Route] 策略: {route} | {route_reason}")
    print(f"[RAG] 查询: {user_input}")
    print(f"[RAG] 查询变体: {rag_context.get('query_variants', [])}")
    for section_name, items in (("Old Dialogue", rag_context.get("old_dialogue", [])), ("Knowledge", rag_context.get("knowledge", []))):
        print(f"[RAG] {section_name} 命中 {len(items)} 条")
        for idx, item in enumerate(items, start=1):
            print(
                f"[RAG] {section_name}#{idx} source={item.get('source')} "
                f"distance={item.get('distance')} rerank={item.get('rerank_score')}"
            )

    system_prompt = build_system_prompt(BASE_SYSTEM_PROMPT, memory_context, rag_context)
    messages = [{"role": "system", "content": system_prompt}, *history[1:], {"role": "user", "content": user_input}]

    print("\n========== 最终 Prompt ==========")
    for message in messages:
        print(f"\n[{message['role']}]:\n{message['content']}")
    print("\n================================\n")

    try:
        reply = call_chat_api(messages)
    except Exception as exc:
        print(f"[Chat] 请求失败: {exc}")
        return jsonify({"reply": "出错了，请稍后再试。", "error": str(exc)}), 500

    print(f"[Chat] 回复: {reply}")
    history.extend([
        {"role": "user", "content": user_input},
        {"role": "assistant", "content": reply},
    ])
    while len(history) > MAX_HISTORY_MESSAGES:
        history.pop(1)

    try:
        update_memory(user_input, reply)
    except Exception as exc:
        print(f"[记忆] 写入失败: {exc}")

    def process_tts():
        audio_data = get_tts_audio_data(reply)
        if audio_data:
            play_audio_and_update_mouth(audio_data)

    threading.Thread(target=process_tts, daemon=True).start()
    return jsonify({"reply": reply, "route": route})


@app.route("/api/tts", methods=["POST"])
def tts():
    text = (request.json or {}).get("text", "")
    if not text:
        return jsonify({"error": "文本不能为空"}), 400
    text = split_say(text)
    print(f"[TTS] 请求: {text[:50]}...")
    try:
        audio_data = get_tts_audio_data(text)
        if not audio_data:
            raise RuntimeError("TTS 服务异常")
        print(f"[TTS] 返回音频大小: {len(audio_data)} bytes")
        return Response(audio_data, mimetype="audio/wav")
    except Exception as exc:
        print(f"[TTS] 错误: {exc}")
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    LIVE2D_DIR.mkdir(exist_ok=True)
    if not TMP_TXT_PATH.exists():
        TMP_TXT_PATH.write_text("0", encoding="utf-8")
    app.run(host="0.0.0.0", port=5000, debug=True)
