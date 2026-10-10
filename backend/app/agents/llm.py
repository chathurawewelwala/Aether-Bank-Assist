"""
LLM client with graceful degradation when API key is absent.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.security.guardrails import BRAND_SYSTEM_ADDENDUM

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self):
        self.settings = get_settings()
        self._client = None
        if self.settings.openai_api_key:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self.settings.openai_api_key)
            except Exception as e:
                logger.warning("Could not init OpenAI client: %s", e)

    @property
    def available(self) -> bool:
        return self._client is not None

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
    ) -> str:
        if not self._client:
            return self._mock_response(messages)

        # Inject brand addendum into system message
        enriched = []
        has_system = False
        for m in messages:
            if m["role"] == "system":
                enriched.append({"role": "system", "content": m["content"] + "\n" + BRAND_SYSTEM_ADDENDUM})
                has_system = True
            else:
                enriched.append(m)
        if not has_system:
            enriched.insert(0, {"role": "system", "content": BRAND_SYSTEM_ADDENDUM})

        try:
            kwargs: Dict[str, Any] = {
                "model": self.settings.openai_model,
                "messages": enriched,
                "temperature": temperature if temperature is not None else self.settings.llm_temperature,
                "max_tokens": max_tokens or self.settings.llm_max_tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format
            resp = await self._client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as e:
            logger.exception("LLM call failed: %s", e)
            return f"[LLM temporarily unavailable: {type(e).__name__}. Using retrieval-only fallback.]"

    def _mock_response(self, messages: List[Dict[str, str]]) -> str:
        """Deterministic offline responses for demo without API key."""
        user_msg = ""
        for m in reversed(messages):
            if m["role"] == "user":
                user_msg = m["content"].lower()
                break

        if "outage" in user_msg or "payment failure" in user_msg or "root cause" in user_msg:
            return (
                "Based on the retrieved incident reports, the recurring root causes for payment-related "
                "outages and failures over the last year are:\n\n"
                "1. **Connection / resource pool exhaustion** after configuration or certificate changes "
                "(INC-2025-0312, INC-2025-0108).\n"
                "2. **Memory leaks / pressure** in the reconciliation service under larger batch sizes "
                "(INC-2025-0108, also contributing to INC-2025-0312).\n"
                "3. **Idempotency key collisions** under high concurrency / campaign traffic "
                "(INC-2024-1122).\n\n"
                "Recommended focus areas from the runbooks and architecture docs include circuit breakers, "
                "memory profiling gates in CI, and pre-flight checks during certificate rotation."
            )
        if "runbook" in user_msg or "how to" in user_msg:
            return (
                "From the Payment Gateway runbook: for connection pool exhaustion, check pool metrics, "
                "temporarily scale PayFlow replicas, restart reconciliation sidecars, and investigate "
                "recent config/cert changes. Always run pre-flight connection tests before certificate rotation."
            )
        if "who" in user_msg or "employee" in user_msg or "oncall" in user_msg:
            return "I can look up the employee directory or service catalog when the appropriate tools are permitted for your role."
        if any(w in user_msg for w in ["todo", "to-do", "task", "to do"]):
            return (
                "I used the to-do tools for your request. "
                "Open items are shown from the tool results. "
                "You can also manage tasks on the To-dos page in the dashboard."
            )
        return (
            "I searched the Aether Bank knowledge base. Please refine your question or ensure relevant "
            "documents are indexed. (Running in offline demo mode – set OPENAI_API_KEY for full LLM responses.)"
        )


_llm: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
