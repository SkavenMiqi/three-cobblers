"""LLM API 客户端：OpenAI 兼容 /v1/chat/completions，带重试 + 指数退避。

同步实现，适合在 Kivy 里用后台线程调用（见 ai_chat.py 的调用模式）。
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx


class LLMError(RuntimeError):
    """API 不可恢复错误或重试耗尽。"""


_LLM_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_tool.log")


def _llm_tlog(msg: str) -> None:
    try:
        with open(_LLM_LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _build_headers(api_key: str, api_base_url: str) -> dict[str, str]:
    """MiMo 用 api-key 头，其余用 Authorization: Bearer。"""
    if "xiaomimimo" in api_base_url.lower():
        return {"api-key": api_key, "Content-Type": "application/json"}
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


class LLMClient:
    RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: str,
        api_base_url: str,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        max_retries: int = 3,
        retry_base_delay: float = 2.0,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.api_base_url = api_base_url.rstrip("/")
        # 去掉末尾 /v1 —— 请求时统一再加
        if self.api_base_url.endswith("/v1"):
            self.api_base_url = self.api_base_url[:-3]
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """返回 {"text", "input_tokens", "output_tokens"}。"""
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._do_request(messages, max_tokens, temperature, extra)
            except httpx.HTTPStatusError as e:
                last_err = e
                # 记下 400 完整响应
                if e.response.status_code == 400:
                    _llm_tlog(f"400 body: {e.response.text[:500]}")
                if e.response.status_code not in self.RETRYABLE_STATUS:
                    raise LLMError(
                        f"API error {e.response.status_code}: {e.response.text[:200]}"
                    ) from e
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_err = e
            time.sleep(self.retry_base_delay * (2 ** (attempt - 1)))
        raise LLMError(f"重试 {self.max_retries} 次仍失败: {last_err}")

    def chat_text(self, messages: list[dict[str, str]], **kw: Any) -> str:
        return self.chat(messages, **kw)["text"]

    def _do_request(self, messages, max_tokens, temperature, extra):
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
        }
        mt = self.max_tokens if max_tokens is None else max_tokens
        # MiMo 用 max_completion_tokens 而非 max_tokens
        if "xiaomimimo" in self.api_base_url.lower():
            body["max_completion_tokens"] = mt
        else:
            body["max_tokens"] = mt
        body.update(extra)
        headers = _build_headers(self.api_key, self.api_base_url)
        resp = self.client.post(
            f"{self.api_base_url}/v1/chat/completions",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        msg = data["choices"][0]["message"]
        usage = data.get("usage", {})
        return {
            "text": msg.get("content") or "",
            "tool_calls": msg.get("tool_calls"),
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }
