from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
MEMORY_MD_PATH = KNOWLEDGE_DIR / "MEMORY.md"
API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

DEFAULT_MEMORY_MD = """# 核心记忆
> 这个文件存放会始终注入 prompt 的长期记忆。只保留稳定、重要、对后续对话有帮助的信息，避免流水账。
> 每日对话记录写入 memory_YYYY-MM-DD.txt，供 RAG 检索；只有本文件属于核心记忆。

## 身份
*（你究竟是谁？充分了解自己的身份，不断更新自己的身份信息。）*
- 名字：纳西妲
- 称号：草神、智慧之神、小吉祥草王
- 所属：须弥
- 元素：草
- 神之心：草元素神之心（已用来换取“虚假之天”的知识）

## 与用户相关的长期记忆
*（这里只保留长期稳定的信息。例如关系、重要偏好、长期约定、反复提到的重要背景。）*
- 暂无

## 回复风格提示
*（需要 AI 长期遵守的表达方式、身份约束、行为边界，也直接写在这里。）*
- 保持纳西妲的语气：温柔、聪慧、富有共情。
- 优先结合设定与用户历史对话作答。
- 不要把零散的聊天内容都塞进核心记忆。
"""


def ensure_memory_file():
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    if not MEMORY_MD_PATH.exists():
        MEMORY_MD_PATH.write_text(DEFAULT_MEMORY_MD, encoding="utf-8")


def get_memory_context() -> str:
    ensure_memory_file()
    return MEMORY_MD_PATH.read_text(encoding="utf-8").strip()


def _append_daily_log(user_input: str, ai_response: str):
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    hm = datetime.now().strftime("%H:%M")
    path = KNOWLEDGE_DIR / f"memory_{day}.txt"
    is_new = not path.exists()

    with path.open("a", encoding="utf-8") as f:
        if is_new:
            f.write(f"# 对话记录 {day}\n\n")
        f.write(f"## {hm}\n")
        f.write(f"- 用户：{user_input}\n")
        f.write(f"- 纳西妲：{ai_response}\n\n")


def _call_llm(messages):
    if not API_KEY:
        raise RuntimeError("未设置 DEEPSEEK_API_KEY")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"model": MODEL_NAME, "messages": messages, "temperature": 0.2}
    response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


def _update_memory_md(user_input: str, ai_response: str):
    ensure_memory_file()
    old_memory = get_memory_context()

    system_prompt = (
        "你是一个负责维护角色长期核心记忆的编辑器。"
        "你的任务是根据新对话，直接改写整份 MEMORY.md。"
        "只保留长期稳定、重要、会持续影响后续对话的信息。"
        "不要记录一次性闲聊、短期情绪、临时事实、具体某次问答细节。"
        "保持 Markdown 结构清晰，尽量沿用原有标题。"
        "如果没有必要修改，就尽量少改。"
        "输出必须是完整的 MEMORY.md 内容，不要解释。"
    )
    user_prompt = (
        f"当前 MEMORY.md：\n\n{old_memory}\n\n"
        f"新对话：\n用户：{user_input}\n纳西妲：{ai_response}\n\n"
        "请输出更新后的完整 MEMORY.md。"
    )

    try:
        updated = _call_llm([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        if updated:
            MEMORY_MD_PATH.write_text(updated, encoding="utf-8")
            print("[记忆] MEMORY.md 已更新")
    except Exception as exc:
        print(f"[记忆] MEMORY.md 更新失败: {exc}")
