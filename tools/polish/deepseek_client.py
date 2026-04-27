"""Thin DeepSeek API wrapper for paragraph-level polishing.

The OpenAI-compatible chat completions endpoint is used. JSON mode is enabled
so we can rely on a structured response."""

from __future__ import annotations

import json
import os
from typing import TypedDict, List

import httpx


class PolishResult(TypedDict):
    polished: str
    issues: List[str]


_API_URL = "https://api.deepseek.com/chat/completions"
_MODEL = "deepseek-chat"
_TIMEOUT_S = 30.0
_MAX_RETRIES = 2

_SYSTEM_PROMPT = (
    "你是一位严谨的中文文字编辑，专门润色 AI 起草的中文段落。规则：\n"
    "1) 修正不通顺的句子和不准确的表述；\n"
    "2) 严格保持原意、写作风格、语气、人称不变；\n"
    "3) 完整保留所有 Markdown 标记，包括 **粗体**、*斜体*、[链接](url)、`代码`、"
    "脚注引用 [^1]、行首的 > 引用标记和列表标记 - / 1. 等；\n"
    "4) 不要扩写或缩写，长度尽量接近原文；\n"
    "5) 不要给段落加标题，不要输出任何解释性文字到 polished 字段里；\n"
    "6) 如果原文已经很好，polished 直接返回原文，issues 返回空数组。\n"
    '只输出 JSON：{"polished": "<润色后正文>", "issues": ["改了 X 因为 Y", ...]}'
)


class DeepSeekError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise DeepSeekError(
            "DEEPSEEK_API_KEY 未设置。复制 .env.example 为 .env 并填入 key。"
        )
    return key


async def polish_paragraph(text: str) -> PolishResult:
    """Send one paragraph to DeepSeek and return the polished version."""
    payload = {
        "model": _MODEL,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f'原文：\n"""\n{text}\n"""'},
        ],
    }
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }

    last_err: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
                resp = await client.post(_API_URL, json=payload, headers=headers)
            if resp.status_code == 401:
                raise DeepSeekError("DeepSeek 认证失败：请检查 DEEPSEEK_API_KEY 是否正确。")
            if resp.status_code >= 500 and attempt < _MAX_RETRIES:
                last_err = DeepSeekError(f"DeepSeek 服务端错误 {resp.status_code}")
                continue
            if resp.status_code >= 400:
                raise DeepSeekError(
                    f"DeepSeek 请求失败 ({resp.status_code}): {resp.text[:300]}"
                )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return {
                "polished": str(parsed.get("polished", text)),
                "issues": list(parsed.get("issues", [])),
            }
        except httpx.RequestError as e:
            last_err = e
            if attempt >= _MAX_RETRIES:
                break
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            raise DeepSeekError(f"DeepSeek 返回格式异常：{e}") from e

    raise DeepSeekError(f"DeepSeek 多次重试仍失败：{last_err}")
