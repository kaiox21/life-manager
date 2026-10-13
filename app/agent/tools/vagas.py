"""Vagas do radar (change radar-vagas): listar as recentes e dispensar uma, pelo código (V12) ou
pelo título. O código é o mesmo da mensagem do WhatsApp e do painel."""

from datetime import timedelta
from typing import Any

from pydantic import Field
from sqlalchemy import func, select

from app.agent.tools.base import Tool, ToolArgs, ToolContext, ToolError, br_date
from app.agent.tools.resolve import normalize
from app.db.models import JobLead
from app.vagas.templates import TIPOS, ordered

RECENT_DAYS = 14


def describe(v: JobLead) -> dict[str, Any]:
    return {
        "codigo": v.codigo,
        "titulo": v.titulo,
        "organizacao": v.organizacao,
        "tipo": TIPOS.get(v.tipo, v.tipo),
        "local": v.local,
        "prazo": br_date(v.prazo) if v.prazo else "sem prazo informado",
        "link": v.url,
        "resumo": v.resumo,
    }


async def recent(ctx: ToolContext, limit: int | None = None) -> list[JobLead]:
    since = ctx.clock() - timedelta(days=RECENT_DAYS)
    rows = (
        await ctx.session.scalars(
            select(JobLead).where(JobLead.found_at >= since, JobLead.dismissed_at.is_(None))
        )
    ).all()
    today = ctx.clock().date()
    live = [v for v in rows if v.prazo is None or v.prazo >= today]
    return ordered(live)[:limit] if limit else ordered(live)


class ListarVagasArgs(ToolArgs):
    pass


async def listar_vagas(ctx: ToolContext, _args: ListarVagasArgs) -> dict[str, Any]:
    vagas = await recent(ctx)
    return {"vagas": [describe(v) for v in vagas], "total": len(vagas), "dias": RECENT_DAYS}


class DispensarVagaArgs(ToolArgs):
    vaga: str = Field(
        min_length=2,
        max_length=120,
        description="Código da vaga (ex.: 'V12') ou parte do título/organização",
    )


async def dispensar_vaga(ctx: ToolContext, args: DispensarVagaArgs) -> dict[str, Any]:
    q = args.vaga.strip()
    code = q.upper().replace(" ", "")
    found = await ctx.session.scalar(select(JobLead).where(func.upper(JobLead.codigo) == code))
    if found is None:
        needle = normalize(q)
        matches = [
            v for v in await recent(ctx) if needle in normalize(f"{v.titulo} {v.organizacao}")
        ]
        if len(matches) > 1:
            raise ToolError(
                "Mais de uma vaga combina com isso.",
                opcoes=[f"{v.codigo} · {v.titulo} — {v.organizacao}" for v in matches],
            )
        found = matches[0] if matches else None
    if found is None:
        raise ToolError(f"Não achei a vaga {q!r} entre as recentes.")
    if found.dismissed_at is None:
        found.dismissed_at = ctx.clock()
    return {"status": "dispensada", "vaga": describe(found)}


TOOLS = [
    Tool(
        "listar_vagas",
        ("vagas",),
        "Lista as vagas achadas pelo radar nos últimos 14 dias (estágio, bolsa, monitoria, "
        "júnior), com o código (V12), título, onde, prazo e link. Ex.: 'quais vagas novas?'.",
        ListarVagasArgs,
        listar_vagas,
    ),
    Tool(
        "dispensar_vaga",
        ("vagas",),
        "Esconde uma vaga que não interessa (some da lista e do painel, não volta). "
        "Ex.: 'não tenho interesse na V12' -> vaga='V12'.",
        DispensarVagaArgs,
        dispensar_vaga,
    ),
]
