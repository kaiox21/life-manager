"""Laço do agente: tool calling, validação, escalada e desistência (SPEC.md, "Modelo de IA")."""

import json
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.agent.intent import Intent
from app.agent.llm import LLM, Completion, ToolCall
from app.agent.tools import ALL_TOOLS, Tool, ToolContext, ToolError, tools_for

log = logging.getLogger(__name__)

MAX_ITERATIONS = 6
MAX_VALIDATION_FAILURES = 2
GIVE_UP = "Não consegui entender. Pode reformular?"

# Respostas que afirmam ter gravado algo sem ter chamado ferramenta.
_CLAIMS_WRITE = re.compile(r"\b(lancei|lançado|registrei|registrado|anotei|gravei|gravado)\b", re.I)


@dataclass
class FirstCall:
    name: str
    args: dict[str, Any]


@dataclass
class AgentOutcome:
    reply: str
    model: str | None = None
    escalated: bool = False
    tools_called: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    latency_ms: int = 0
    error: str | None = None
    first_call: FirstCall | None = None
    asked_question: bool = False

    def add_usage(self, c: Completion) -> None:
        self.input_tokens += c.input_tokens
        self.output_tokens += c.output_tokens
        self.cost_usd += c.cost_usd
        self.latency_ms += c.latency_ms


class _AttemptFailed(Exception):
    pass


async def run_agent(
    *,
    llm: LLM,
    ctx: ToolContext,
    intent: Intent,
    system_prompt: str,
    history: list[dict[str, Any]],
    text: str,
    primary_model: str,
    escalation_model: str,
    stop_at_first_tool: bool = False,
) -> AgentOutcome:
    """Roda o agente. Com stop_at_first_tool (prova), devolve a 1ª chamada válida sem executá-la."""
    outcome = AgentOutcome(reply=GIVE_UP)
    tools = tools_for(intent) if intent != "fora_do_escopo" else []
    base_messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": text},
    ]
    for model in (primary_model, escalation_model):
        outcome.escalated = model != primary_model
        savepoint = await ctx.session.begin_nested()
        try:
            await _attempt(
                llm, ctx, model, intent, tools, list(base_messages), outcome, stop_at_first_tool
            )
        except _AttemptFailed as exc:
            await savepoint.rollback()
            outcome.error = str(exc)
            outcome.first_call = None
            log.info("tentativa com %s falhou: %s", model, exc)
            continue
        await savepoint.commit()
        outcome.model = model
        outcome.error = None
        return outcome

    outcome.reply = GIVE_UP
    outcome.model = escalation_model
    return outcome


async def _attempt(
    llm: LLM,
    ctx: ToolContext,
    model: str,
    intent: Intent,
    tools: list[Tool],
    messages: list[dict[str, Any]],
    outcome: AgentOutcome,
    stop_at_first_tool: bool,
) -> None:
    schemas = [t.openai_schema() for t in tools] or None
    by_name = {t.name: t for t in tools}
    failures = 0
    executed = 0

    for _ in range(MAX_ITERATIONS):
        completion = await llm.chat(model, messages, tools=schemas)
        outcome.add_usage(completion)

        if not completion.tool_calls:
            reply = (completion.content or "").strip()
            if not reply:
                raise _AttemptFailed("resposta vazia")
            if executed == 0 and _should_have_called_tool(intent, reply):
                raise _AttemptFailed("respondeu sem chamar ferramenta")
            outcome.reply = reply
            outcome.asked_question = executed == 0 and "?" in reply
            return

        messages.append(completion.assistant_message())
        for call in completion.tool_calls:
            result, ok, args = await _run_call(
                ctx, call, by_name, model, outcome, dry_run=stop_at_first_tool
            )
            if ok and stop_at_first_tool:
                outcome.first_call = FirstCall(call.name, args)
                outcome.reply = ""
                return
            if ok:
                executed += 1
            else:
                failures += 1
                if failures >= MAX_VALIDATION_FAILURES:
                    raise _AttemptFailed(f"validação falhou {failures} vezes")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
    raise _AttemptFailed(f"passou de {MAX_ITERATIONS} iterações")


async def _run_call(
    ctx: ToolContext,
    call: ToolCall,
    by_name: dict[str, Tool],
    model: str,
    outcome: AgentOutcome,
    dry_run: bool,
) -> tuple[dict[str, Any], bool, dict[str, Any]]:
    """Valida e executa uma chamada. Devolve (resultado, válida?, argumentos crus)."""
    entry: dict[str, Any] = {"name": call.name, "model": model}
    outcome.tools_called.append(entry)
    try:
        raw_args = json.loads(call.arguments or "{}")
        if not isinstance(raw_args, dict):
            raise ValueError("argumentos precisam ser um objeto JSON")
    except ValueError as exc:
        entry.update(args=call.arguments, ok=False, error=f"JSON inválido: {exc}")
        return {"erro_validacao": f"JSON inválido: {exc}"}, False, {}
    entry["args"] = raw_args

    tool = by_name.get(call.name)
    if tool is None:
        msg = f"ferramenta '{call.name}' não disponível; use: {', '.join(by_name) or 'nenhuma'}"
        if call.name in ALL_TOOLS:
            msg = f"'{call.name}' não serve para este pedido; use: {', '.join(by_name)}"
        entry.update(ok=False, error=msg)
        return {"erro_validacao": msg}, False, raw_args
    try:
        args = tool.args_model.model_validate(raw_args)
    except ValidationError as exc:
        errors = [f"{'.'.join(map(str, e['loc'])) or 'args'}: {e['msg']}" for e in exc.errors()]
        entry.update(ok=False, error="; ".join(errors))
        return {"erro_validacao": errors}, False, raw_args

    entry["ok"] = True
    if dry_run:
        return {}, True, raw_args
    try:
        async with ctx.session.begin_nested():
            result = await tool.fn(ctx, args)
    except ToolError as exc:
        entry["result"] = exc.payload
        return exc.payload, True, raw_args
    except Exception as exc:  # noqa: BLE001 - erro interno vira resposta, não derruba a conversa
        log.exception("ferramenta %s falhou", call.name)
        entry.update(ok=False, error=f"interno: {exc.__class__.__name__}")
        raise _AttemptFailed(f"erro interno em {call.name}") from exc
    entry["result"] = result
    return result, True, raw_args


def _should_have_called_tool(intent: Intent, reply: str) -> bool:
    if intent == "consulta_gasto":
        return "?" not in reply  # responder valores sem consultar = inventar
    if intent in ("confirmacao", "agenda"):
        return "?" not in reply  # agenda: responder sem consultar = dado possivelmente velho
    if intent == "gasto":
        return bool(_CLAIMS_WRITE.search(reply))
    return False
