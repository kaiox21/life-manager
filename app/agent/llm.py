"""Acesso aos modelos pelo Vercel AI Gateway. Único lugar que fala com o cliente openai."""

import json
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

import httpx
from openai import AsyncOpenAI

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON cru, como o modelo mandou


@dataclass
class Completion:
    model: str
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    latency_ms: int = 0

    def assistant_message(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in self.tool_calls
            ]
        return msg


class LLM(Protocol):
    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> Completion: ...


@dataclass(frozen=True)
class Price:
    input_per_token: Decimal
    output_per_token: Decimal


class GatewayLLM:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        allowed_providers: list[str] | None = None,
        reasoning_effort: str = "",
        timeout_s: float = 60,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout_s)
        self._base_url = base_url.rstrip("/")
        self._allowed = allowed_providers or []
        self._reasoning_effort = reasoning_effort
        self._prices: dict[str, Price] | None = None

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> Completion:
        # Sem temperature: vários modelos de raciocínio recusam valores diferentes do padrão.
        kwargs: dict[str, Any] = {"model": model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if self._reasoning_effort:
            kwargs["reasoning_effort"] = self._reasoning_effort
        if self._allowed:
            kwargs["extra_body"] = {"providerOptions": {"gateway": {"only": self._allowed}}}

        started = time.monotonic()
        resp = await self._client.chat.completions.create(**kwargs)
        latency = int((time.monotonic() - started) * 1000)

        choice = resp.choices[0].message
        calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments or "{}")
            for tc in (choice.tool_calls or [])
            if tc.type == "function"
        ]
        usage = resp.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0
        return Completion(
            model=model,
            content=choice.content,
            tool_calls=calls,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            cost_usd=await self._cost(model, tokens_in, tokens_out),
            latency_ms=latency,
        )

    async def _cost(self, model: str, tokens_in: int, tokens_out: int) -> Decimal:
        price = (await self._price_table()).get(model)
        if price is None:
            return Decimal(0)
        return price.input_per_token * tokens_in + price.output_per_token * tokens_out

    async def _price_table(self) -> dict[str, Price]:
        """Preços do catálogo do gateway (US$ por token), buscados uma vez."""
        if self._prices is None:
            try:
                async with httpx.AsyncClient(timeout=15) as http:
                    data = (await http.get(f"{self._base_url}/models")).json()["data"]
                self._prices = {
                    m["id"]: Price(
                        Decimal(str(m["pricing"].get("input", 0))),
                        Decimal(str(m["pricing"].get("output", 0))),
                    )
                    for m in data
                    if m.get("pricing")
                }
            except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError):
                log.warning("não consegui ler os preços do gateway; custo fica 0")
                self._prices = {}
        return self._prices

    async def aclose(self) -> None:
        await self._client.close()
