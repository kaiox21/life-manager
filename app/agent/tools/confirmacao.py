"""Ferramenta do grupo "confirmacao" e a resolução de pendências."""

import uuid
from typing import Any, Literal

from pydantic import Field
from sqlalchemy import select

from app.agent.tools.agenda import CriarEventoArgs, delete_event, record_event
from app.agent.tools.base import Tool, ToolArgs, ToolContext
from app.agent.tools.gastos import LancarGastoArgs, record_expense
from app.db.models import PendingAction


async def open_pending(ctx: ToolContext) -> PendingAction | None:
    """Pendência mais recente ainda válida; as vencidas são marcadas como expiradas."""
    rows = (
        await ctx.session.scalars(
            select(PendingAction)
            .where(PendingAction.status == "pending")
            .order_by(PendingAction.created_at.desc())
        )
    ).all()
    now = ctx.clock()
    latest = None
    for row in rows:
        if row.expires_at <= now:
            row.status = "expired"
        elif latest is None:
            latest = row
    return latest


class ConfirmarPendenteArgs(ToolArgs):
    pending_id: str | None = Field(
        default=None, description="id da pendência; omita para a mais recente"
    )
    decisao: Literal["sim", "nao"]


async def confirmar_pendente(ctx: ToolContext, args: ConfirmarPendenteArgs) -> dict[str, Any]:
    pending = await open_pending(ctx)
    if args.pending_id and (pending is None or str(pending.id) != args.pending_id):
        pending = await _by_id(ctx, args.pending_id)
    if pending is None or pending.status != "pending" or pending.expires_at <= ctx.clock():
        return {"status": "sem_pendencia", "resumo": "Não há nada aguardando confirmação."}

    if args.decisao == "nao":
        pending.status = "cancelled"
        return {"status": "cancelado", "resumo": pending.summary.removesuffix(". Confirma?")}

    pending.status = "confirmed"
    return await EXECUTORS[pending.tool_name](ctx, pending.args)


async def _by_id(ctx: ToolContext, raw_id: str) -> PendingAction | None:
    try:
        pending_id = uuid.UUID(raw_id)
    except ValueError:
        return None
    return await ctx.session.get(PendingAction, pending_id)


async def _exec_lancar_gasto(ctx: ToolContext, raw: dict[str, Any]) -> dict[str, Any]:
    return await record_expense(ctx, LancarGastoArgs.model_validate(raw))


async def _exec_criar_evento(ctx: ToolContext, raw: dict[str, Any]) -> dict[str, Any]:
    return await record_event(ctx, CriarEventoArgs.model_validate(raw))


async def _exec_remover_evento(ctx: ToolContext, raw: dict[str, Any]) -> dict[str, Any]:
    return await delete_event(ctx, uuid.UUID(raw["event_id"]))


EXECUTORS = {
    "lancar_gasto": _exec_lancar_gasto,
    "criar_evento": _exec_criar_evento,
    "remover_evento": _exec_remover_evento,
}

TOOLS = [
    Tool(
        "confirmar_pendente",
        ("confirmacao",),
        "Confirma (decisao='sim') ou cancela (decisao='nao') a ação aguardando confirmação.",
        ConfirmarPendenteArgs,
        confirmar_pendente,
    ),
]
