"""Orquestra uma mensagem: pendência direta, classificação, agente e registro em agent_runs."""

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.intent import Classification, classify
from app.agent.llm import LLM
from app.agent.loop import AgentOutcome, run_agent
from app.agent.prompt import MethodInfo, build_system_prompt
from app.agent.tools import ToolContext
from app.agent.tools.agenda import BuscarEventosArgs, buscar_eventos
from app.agent.tools.base import Source
from app.agent.tools.confirmacao import ConfirmarPendenteArgs, confirmar_pendente, open_pending
from app.agent.tools.resolve import normalize
from app.clock import Clock, today
from app.db.models import AgentRun, Category, Message, PaymentMethod, Person

log = logging.getLogger(__name__)

HISTORY_SIZE = 10
MEDIA_FOLLOWUP = timedelta(minutes=15)
MEDIA_SOURCE: dict[str, Source] = {"audio": "audio", "image": "foto"}
PHOTO_PLACEHOLDER = "[foto de recibo]"
YES = {"sim", "s", "confirma", "confirmo", "pode", "ok", "isso", "pode gravar", "manda"}
NO = {"nao", "n", "cancela", "cancelar", "nao grava", "deixa"}


@dataclass(frozen=True)
class Models:
    classifier: str
    primary: str
    escalation: str


async def load_history(
    session: AsyncSession, exclude_id: uuid.UUID | None, strip_prefix: str = ""
) -> list[dict[str, Any]]:
    stmt = (
        select(Message)
        .where(
            Message.channel == "whatsapp",
            or_(Message.body.is_not(None), Message.type == "image"),
        )
        .order_by(Message.created_at.desc())
        .limit(HISTORY_SIZE + 1)
    )
    rows = [m for m in (await session.scalars(stmt)).all() if m.id != exclude_id][:HISTORY_SIZE]
    history = []
    for m in reversed(rows):
        body = m.body or ""
        if m.direction == "in" and m.type == "image":
            body = f"{PHOTO_PLACEHOLDER} {body}".strip()
        if m.direction == "out" and strip_prefix:
            body = body.removeprefix(strip_prefix)
        history.append({"role": "assistant" if m.direction == "out" else "user", "content": body})
    return history


async def inherited_source(session: AsyncSession, exclude_id: uuid.UUID | None) -> Source:
    """Resposta a uma pergunta do bot sobre foto/áudio recente herda a origem (confirmação)."""
    filters = [Message.channel == "whatsapp", Message.created_at > func.now() - MEDIA_FOLLOWUP]
    if exclude_id:
        filters.append(Message.id != exclude_id)
    recent = (
        await session.scalars(
            select(Message).where(*filters).order_by(Message.created_at.desc()).limit(2)
        )
    ).all()
    if len(recent) < 2:
        return "texto"
    last_out, previous_in = recent
    if (
        last_out.direction == "out"
        and (last_out.body or "").rstrip().endswith("?")
        and previous_in.direction == "in"
        and previous_in.type in MEDIA_SOURCE
    ):
        return MEDIA_SOURCE[previous_in.type]
    return "texto"


async def build_prompt(
    ctx: ToolContext, pending_summary: str | None, data_only: bool = False
) -> str:
    methods = [
        MethodInfo(pm.name, pm.kind, pm.closing_day, pm.due_day)
        for pm in (
            await ctx.session.scalars(
                select(PaymentMethod)
                .where(PaymentMethod.active.is_(True))
                .order_by(PaymentMethod.name)
            )
        )
    ]
    categories = list(
        (await ctx.session.scalars(select(Category.name).order_by(Category.name))).all()
    )
    people = [
        f"{p.name} ({p.relation})" if p.relation else p.name
        for p in await ctx.session.scalars(select(Person).order_by(Person.name))
    ]
    hoje = today(ctx.clock)
    week = await buscar_eventos(ctx, BuscarEventosArgs(de=hoje, ate=hoje + timedelta(days=7)))
    upcoming = [
        f"{e['data']} {e['hora']}: {e['titulo']}" + (f" ({e['pessoa']})" if "pessoa" in e else "")
        for e in week["eventos"]
    ]
    return build_system_prompt(
        ctx.clock(),
        methods,
        categories,
        pending_summary=pending_summary,
        upcoming=upcoming,
        people=people,
        data_only=data_only,
    )


def _direct_reply(result: dict[str, Any]) -> str:
    status = result.get("status")
    if status == "gravado":
        extra = f" Fatura vence {result['fatura_vence']}." if result.get("fatura_vence") else ""
        return f'Gravado: {result["resumo"]}.{extra} Diga "desfazer" para reverter.'
    if status == "cancelado":
        return f"Cancelado: {result['resumo']}."
    return "Não há nada aguardando confirmação."


async def answer(
    *,
    llm: LLM,
    models: Models,
    session: AsyncSession,
    clock: Clock,
    text: str,
    message_id: uuid.UUID | None,
    channel: str = "whatsapp",
    strip_prefix: str = "",
    source: Source = "texto",
    image: tuple[str, str] | None = None,
    pre_steps: list[dict[str, Any]] | None = None,
) -> str:
    """Responde uma mensagem do dono e grava a linha de agent_runs. Commit fica com quem chama.

    source: origem da mensagem (áudio já chega transcrito em `text`).
    image: (mimetype, base64) de uma foto; vai ao modelo como bloco de imagem no grupo gasto.
    """
    if source == "texto":
        source = await inherited_source(session, message_id)
    ctx = ToolContext(session=session, clock=clock, message_id=message_id, source=source)
    run = AgentRun(message_id=message_id, channel=channel, tools_called=list(pre_steps or []))
    session.add(run)

    pending = await open_pending(ctx)
    if image is None and pending and normalize(text).strip(" .!") in YES | NO:
        decision = "sim" if normalize(text).strip(" .!") in YES else "nao"
        result = await confirmar_pendente(ctx, ConfirmarPendenteArgs(decisao=decision))
        run.intent = "confirmacao"
        run.tools_called = [
            *run.tools_called,
            {
                "name": "confirmar_pendente",
                "args": {"decisao": decision},
                "ok": True,
                "direct": True,
            },
        ]
        return _direct_reply(result)

    history = await load_history(session, message_id, strip_prefix)
    pending_summary = pending.summary if pending else None
    outcome = AgentOutcome(reply="")
    try:
        user_content: str | list[dict[str, Any]] | None = None
        if image is not None:
            # Foto é recibo: vai direto ao grupo gasto, sem classificador.
            cls = Classification(
                intent="gasto",
                raw="foto",
                model="",
                input_tokens=0,
                output_tokens=0,
                cost_usd=Decimal(0),
            )
            mimetype, data_b64 = image
            user_content = [
                {"type": "text", "text": text or "Foto de recibo/comprovante."},
                {"type": "image_url", "image_url": {"url": f"data:{mimetype};base64,{data_b64}"}},
            ]
        else:
            cls = await classify(llm, models.classifier, text, history, pending_summary)
        run.intent = cls.intent
        outcome = await run_agent(
            user_content=user_content,
            llm=llm,
            ctx=ctx,
            intent=cls.intent,
            system_prompt=await build_prompt(ctx, pending_summary),
            history=history,
            text=text,
            primary_model=models.primary,
            escalation_model=models.escalation,
        )
        outcome.input_tokens += cls.input_tokens
        outcome.output_tokens += cls.output_tokens
        outcome.cost_usd += cls.cost_usd
    except Exception as exc:  # noqa: BLE001 - falha do modelo não derruba o bot
        log.exception("falha no agente")
        outcome.reply = "Tive um problema para responder agora. Tenta de novo em instantes?"
        outcome.error = f"{exc.__class__.__name__}: {exc}"[:500]

    run.model = outcome.model
    run.escalated = outcome.escalated
    run.tools_called = [*run.tools_called, *outcome.tools_called]
    run.input_tokens = outcome.input_tokens
    run.output_tokens = outcome.output_tokens
    run.cost_usd = outcome.cost_usd
    run.latency_ms = outcome.latency_ms
    run.error = outcome.error
    return outcome.reply
