"""Acesso aos modelos. Dois adaptadores com o mesmo protocolo `LLM`:

- GatewayLLM: cliente openai apontando para o Vercel AI Gateway.
- AnthropicLLM: SDK oficial da Anthropic (modelos Claude direto).

O agente fala sempre no formato de mensagens da API da OpenAI; o AnthropicLLM traduz.
"""

import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

import httpx
from openai import AsyncOpenAI

log = logging.getLogger(__name__)

# Ferramentas que a Anthropic executa no servidor (busca e leitura de páginas). Entram na lista
# como {"type": SERVER_TOOL, "tool": <definição da API>}; o gateway as ignora.
SERVER_TOOL = "anthropic_server"
SEARCH_PRICE = Decimal("0.01")  # US$ por busca (US$ 10 a cada 1.000); ler páginas é grátis
SERVER_BLOCKS = {"server_tool_use", "web_search_tool_result", "web_fetch_tool_result"}
MAX_PAUSES = 3  # turno pausado pela API numa busca longa: continuar no máximo 3 vezes


def server_tool(spec: dict[str, Any]) -> dict[str, Any]:
    return {"type": SERVER_TOOL, "tool": spec}


@dataclass
class ServerToolUse:
    """Pedaço do stream: o modelo começou a usar uma ferramenta de servidor (passo na tela)."""

    name: str


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
    # Blocos originais da Anthropic quando a resposta usou busca/leitura: precisam voltar intactos
    # (com o conteúdo cifrado) se a conversa continuar no mesmo turno.
    raw: list[dict[str, Any]] | None = None
    sources: list[dict[str, str]] = field(default_factory=list)  # {title, url} citados
    searches: int = 0
    fetches: int = 0

    def assistant_message(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": "assistant", "content": self.content or ""}
        if self.raw:
            msg["_anthropic_content"] = self.raw
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


class StreamingLLM(LLM, Protocol):
    """Adaptadores que também entregam o texto aos pedaços (o Jarvis fala enquanto chega)."""

    def stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> AsyncIterator[str | Completion]:
        """Produz pedaços de texto (str) e, por último, o Completion inteiro."""
        ...


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
        tools = [t for t in tools or [] if t.get("type") != SERVER_TOOL] or None
        messages = [{k: v for k, v in m.items() if k != "_anthropic_content"} for m in messages]
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


def _parse_data_url(url: str) -> tuple[str, str] | None:
    if not url.startswith("data:") or ";base64," not in url:
        return None
    header, data = url[5:].split(";base64,", 1)
    return header, data


def to_anthropic(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Converte mensagens no formato OpenAI para (system, messages) da Anthropic."""
    system_parts: list[str] = []
    out: list[dict[str, Any]] = []

    def push(role: str, blocks: list[dict[str, Any]]) -> None:
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)  # tool_results consecutivos num só turno
        else:
            out.append({"role": role, "content": blocks})

    for m in messages:
        role, content = m["role"], m.get("content")
        if role == "system":
            system_parts.append(str(content or ""))
        elif role == "tool":
            push(
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": m["tool_call_id"],
                        "content": str(content or ""),
                    }
                ],
            )
        elif role == "assistant" and m.get("_anthropic_content"):
            push("assistant", [dict(b) for b in m["_anthropic_content"]])
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            if content:
                blocks.append({"type": "text", "text": str(content)})
            for tc in m.get("tool_calls") or []:
                fn = tc["function"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": fn["name"],
                        "input": args if isinstance(args, dict) else {},
                    }
                )
            if blocks:
                push("assistant", blocks)
        else:  # user
            if isinstance(content, list):
                blocks = []
                for part in content:
                    if part.get("type") == "text":
                        blocks.append({"type": "text", "text": part.get("text") or " "})
                    elif part.get("type") == "image_url":
                        parsed = _parse_data_url(part["image_url"]["url"])
                        if parsed:
                            blocks.append(
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": parsed[0],
                                        "data": parsed[1],
                                    },
                                }
                            )
                push("user", blocks)
            else:
                push("user", [{"type": "text", "text": str(content or " ")}])
    return "\n\n".join(system_parts), out


def to_anthropic_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out = [
        {
            "name": t["function"]["name"],
            "description": t["function"].get("description", ""),
            "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}},
        }
        for t in tools or []
        if t.get("type") != SERVER_TOOL
    ]
    if out:
        # As ferramentas são o prefixo estável do pedido: cache de prompt no fim delas.
        out[-1]["cache_control"] = {"type": "ephemeral"}
    return out + [dict(t["tool"]) for t in tools or [] if t.get("type") == SERVER_TOOL]


def _dump(block: Any) -> dict[str, Any]:
    if isinstance(block, dict):
        return block
    return block.model_dump(exclude_none=True)


def _sources(blocks: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Fontes citadas na resposta (busca) e páginas lidas, sem repetir a URL."""
    found: dict[str, str] = {}
    for b in blocks:
        if b.get("type") == "text":
            for c in b.get("citations") or []:
                if c.get("url"):
                    found.setdefault(c["url"], c.get("title") or c["url"])
        elif b.get("type") == "web_fetch_tool_result":
            res = b.get("content") or {}
            if res.get("type") == "web_fetch_result" and res.get("url"):
                doc = res.get("content") or {}
                found.setdefault(res["url"], doc.get("title") or res["url"])
    return [{"title": t, "url": u} for u, t in found.items()]


def to_anthropic_tool_choice(choice: str | dict[str, Any] | None) -> dict[str, Any] | None:
    if isinstance(choice, dict) and choice.get("type") == "function":
        return {"type": "tool", "name": choice["function"]["name"]}
    if choice == "none":
        return {"type": "none"}
    return None  # auto (padrão)


class AnthropicLLM:
    """Modelos Claude pelo SDK oficial `anthropic`."""

    def __init__(
        self,
        api_key: str,
        prices: dict[str, tuple[float, float]] | None = None,
        reasoning_effort: str = "",
        max_tokens: int = 4096,
        client: Any = None,
    ) -> None:
        if client is None:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=api_key, timeout=60, max_retries=2)
        self._client = client
        self._prices = {
            k: Price(Decimal(str(v[0])) / 1_000_000, Decimal(str(v[1])) / 1_000_000)
            for k, v in (prices or {}).items()
        }
        self._effort = reasoning_effort
        self._max_tokens = max_tokens

    def _request(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int | None,
        tool_choice: str | dict[str, Any] | None,
    ) -> dict[str, Any]:
        system, converted = to_anthropic(messages)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens or self._max_tokens,
            "messages": converted,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = to_anthropic_tools(tools)
            choice = to_anthropic_tool_choice(tool_choice)
            if choice:
                kwargs["tool_choice"] = choice
        if self._effort:
            kwargs["output_config"] = {"effort": self._effort}
        return kwargs

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> Completion:
        kwargs = self._request(model, messages, tools, max_tokens, tool_choice)
        started = time.monotonic()
        responses = [await self._client.messages.create(**kwargs)]
        while (
            getattr(responses[-1], "stop_reason", None) == "pause_turn"
            and len(responses) <= MAX_PAUSES
        ):
            # busca longa: a API pausou o turno; devolve o que veio e ela continua
            kwargs = self._continue(kwargs, responses[-1])
            responses.append(await self._client.messages.create(**kwargs))
        return self._completion(model, responses, started)

    async def stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> AsyncIterator[str | ServerToolUse | Completion]:
        kwargs = self._request(model, messages, tools, max_tokens, tool_choice)
        started = time.monotonic()
        responses: list[Any] = []
        while True:
            async with self._client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    kind = getattr(event, "type", "")
                    if kind == "text" and getattr(event, "text", ""):
                        yield event.text
                    elif kind == "content_block_start":
                        block = getattr(event, "content_block", None)
                        if getattr(block, "type", "") == "server_tool_use":
                            yield ServerToolUse(str(getattr(block, "name", "")))
                responses.append(await stream.get_final_message())
            if (
                getattr(responses[-1], "stop_reason", None) != "pause_turn"
                or len(responses) > MAX_PAUSES
            ):
                break
            kwargs = self._continue(kwargs, responses[-1])
        yield self._completion(model, responses, started)

    @staticmethod
    def _continue(kwargs: dict[str, Any], resp: Any) -> dict[str, Any]:
        paused = {"role": "assistant", "content": [_dump(b) for b in resp.content]}
        return {**kwargs, "messages": [*kwargs["messages"], paused]}

    def _completion(self, model: str, resp: Any, started: float) -> Completion:
        responses = resp if isinstance(resp, list) else [resp]
        latency = int((time.monotonic() - started) * 1000)
        blocks = [b for r in responses for b in r.content]
        text = "".join(b.text for b in blocks if b.type == "text").strip()
        calls = [
            ToolCall(id=b.id, name=b.name, arguments=json.dumps(b.input, ensure_ascii=False))
            for b in blocks
            if b.type == "tool_use"
        ]
        tokens_in = sum(r.usage.input_tokens for r in responses)
        tokens_out = sum(r.usage.output_tokens for r in responses)
        searches = fetches = 0
        for r in responses:
            used = getattr(r.usage, "server_tool_use", None)
            searches += int(getattr(used, "web_search_requests", 0) or 0)
            fetches += int(getattr(used, "web_fetch_requests", 0) or 0)
        cached = sum(getattr(r.usage, "cache_read_input_tokens", None) or 0 for r in responses)
        log.debug("anthropic %s: in=%d cache=%d out=%d", model, tokens_in, cached, tokens_out)
        price = self._prices.get(model)
        cost = (
            price.input_per_token * tokens_in + price.output_per_token * tokens_out
            if price
            else Decimal(0)
        ) + SEARCH_PRICE * searches
        raw = None
        sources: list[dict[str, str]] = []
        if any(b.type in SERVER_BLOCKS for b in blocks):
            raw = [_dump(b) for b in blocks]
            sources = _sources(raw)
        return Completion(
            model=model,
            content=text or None,
            tool_calls=calls,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            cost_usd=cost,
            latency_ms=latency,
            raw=raw,
            sources=sources,
            searches=searches,
            fetches=fetches,
        )

    async def aclose(self) -> None:
        await self._client.close()


def make_llm(settings: Any) -> "GatewayLLM | AnthropicLLM":
    """Escolhe o adaptador pelo LLM_PROVIDER do .env."""
    if settings.llm_provider == "anthropic":
        raw = settings.model_prices.strip()
        prices = {k: (float(v[0]), float(v[1])) for k, v in json.loads(raw).items()} if raw else {}
        return AnthropicLLM(
            api_key=settings.anthropic_api_key.get_secret_value(),
            prices=prices,
            reasoning_effort=settings.reasoning_effort,
        )
    from app.config import provider_list

    return GatewayLLM(
        api_key=settings.ai_gateway_api_key.get_secret_value(),
        base_url=settings.ai_gateway_base_url,
        allowed_providers=provider_list(settings.allowed_providers),
        reasoning_effort=settings.reasoning_effort,
    )
