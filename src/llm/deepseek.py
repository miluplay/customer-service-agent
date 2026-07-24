"""使用 DeepSeek 基于检索到的政策片段生成客服回复。"""

import os
import json
from urllib.request import Request, urlopen

from langchain_core.messages import AIMessage, BaseMessage

from src.config import settings


def is_configured() -> bool:
    """是否已提供 DeepSeek API 密钥。"""
    return bool(os.getenv("DEEPSEEK_API_KEY", "").strip())


def generate_tool_call_response(messages: list[BaseMessage], tools: list[dict], system_prompt: str) -> AIMessage:
    """调用 DeepSeek 的 OpenAI 兼容原生 Function Calling 接口。"""
    api_key = os.environ["DEEPSEEK_API_KEY"].strip()
    payload = {
        "model": settings.model_name,
        "messages": [{"role": "system", "content": system_prompt}, *_serialize_messages(messages)],
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.1,
        "max_tokens": 700,
        "stream": False,
    }
    request = Request(
        f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=45) as response:
        result = json.loads(response.read().decode("utf-8"))
    message = result["choices"][0]["message"]
    tool_calls = []
    for call in message.get("tool_calls", []) or []:
        try:
            args = json.loads(call["function"].get("arguments", "{}"))
        except json.JSONDecodeError as error:
            raise RuntimeError("工具调用参数不是有效 JSON") from error
        tool_calls.append({"name": call["function"]["name"], "args": args, "id": call["id"], "type": "tool_call"})
    return AIMessage(content=message.get("content") or "", tool_calls=tool_calls)


def _serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    serialized: list[dict] = []
    for message in messages:
        if message.type == "human":
            serialized.append({"role": "user", "content": str(message.content)})
        elif message.type == "tool":
            serialized.append({"role": "tool", "tool_call_id": message.tool_call_id, "content": str(message.content)})
        elif message.type == "ai":
            item: dict = {"role": "assistant", "content": str(message.content) or None}
            if message.tool_calls:
                item["tool_calls"] = [{"id": call["id"], "type": "function", "function": {"name": call["name"], "arguments": json.dumps(call["args"], ensure_ascii=False)}} for call in message.tool_calls]
            serialized.append(item)
    return serialized
