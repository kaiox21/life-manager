"""LLM falso para testes unitários: nenhum teste sem marcador eval chama a rede."""

import json
from decimal import Decimal
from typing import Any

from app.agent.llm import Completion, ToolCall


def reply(text: str, model: str = "fake/model") -> Completion:
    return Completion(
        model=model, content=text, input_tokens=10, output_tokens=5, cost_usd=Decimal("0.0001")
    )


def call(
    name: str, args: dict[str, Any] | str, model: str = "fake/model", n: int = 1
) -> Completion:
    raw = args if isinstance(args, str) else json.dumps(args)
    return Completion(
        model=model,
        content=None,
        tool_calls=[ToolCall(id=f"call_{name}_{n}", name=name, arguments=raw)],
        input_tokens=20,
        output_tokens=8,
        cost_usd=Decimal("0.0002"),
    )


class ScriptedLLM:
    """Devolve as respostas na ordem. Sem roteiro: classifica como fora_do_escopo e diz "Oi!"."""

    def __init__(self, *script: Completion) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        tool_choice: Any = None,
    ) -> Completion:
        self.calls.append({"model": model, "messages": list(messages), "tools": tools})
        if self.script:
            c = self.script.pop(0)
            c.model = model
            return c
        is_classifier = "Classifique" in messages[0]["content"]
        if is_classifier:
            return call("classificar", {"intencao": "fora_do_escopo"}, model)
        return reply("Oi!", model)


class StreamingScriptedLLM(ScriptedLLM):
    """Como o ScriptedLLM, mas entrega o texto em pedaços e, por último, o Completion."""

    async def stream(self, model, messages, tools=None, max_tokens=None, tool_choice=None):
        completion = await self.chat(model, messages, tools, max_tokens, tool_choice)
        if completion.content and not completion.tool_calls:
            words = completion.content.split(" ")
            for i, w in enumerate(words):
                yield w if i == len(words) - 1 else w + " "
        yield completion
