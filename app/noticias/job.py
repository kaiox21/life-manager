"""Quando o boletim roda e a entrega pelo WhatsApp. Change boletim-noticias.

Checagem a cada 30 min das 07:30 às 22:00 (e na subida): roda se hoje ainda não houve rodada sem
erro e houve menos de 2 tentativas. Como no radar de vagas, um cron às 07:30 não bastaria: com
o Mac dormindo, o boletim ficaria para o dia seguinte. O próprio agent_runs diz o que já rodou.
"""

from __future__ import annotations

import logging
from datetime import datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.llm import LLM
from app.clock import TZ, Clock
from app.db.models import AgentRun, NewsItem
from app.noticias.boletim import CHANNEL, edition_of, load_profile, run_boletim
from app.noticias.templates import bulletin_message
from app.reminders.delivery import SendsText, deliver
from app.reminders.jobs import Notice

log = logging.getLogger(__name__)

MAX_ATTEMPTS_PER_DAY = 2
FIRST, LAST = time(7, 30), time(22, 0)


async def due(session: AsyncSession, now: datetime) -> bool:
    local = now.astimezone(TZ)
    if not FIRST <= local.time() < LAST:
        return False
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    today = AgentRun.channel == CHANNEL, AgentRun.created_at >= midnight
    if await session.scalar(select(AgentRun.id).where(*today, AgentRun.error.is_(None)).limit(1)):
        return False  # o boletim de hoje já saiu
    attempts = await session.scalar(select(func.count(AgentRun.id)).where(*today))
    return (attempts or 0) < MAX_ATTEMPTS_PER_DAY


async def deliver_pending(
    *,
    sessions: async_sessionmaker[AsyncSession],
    now: datetime,
    sender: SendsText,
    owner_phone: str,
    prefix: str = "",
) -> int:
    """Manda as notícias de hoje ainda não enviadas (a entrega pode ter falhado: WhatsApp
    reconectando). Roda em toda checagem. Devolve quantas notícias saíram."""
    edition = edition_of(now)
    async with sessions() as session:
        items = list(
            (
                await session.scalars(
                    select(NewsItem).where(NewsItem.edition == edition, NewsItem.sent_at.is_(None))
                )
            ).all()
        )
        if not items:
            return 0
        text = bulletin_message(items, edition)
        ref = items[0].run_id
        ids = [n.id for n in items]
    if ref is None:
        return 0
    midnight = datetime.combine(edition, time(0), tzinfo=TZ)
    notice = Notice(
        kind="noticias", ref_id=ref, occurrence_at=midnight, minutes_before=0, text=text
    )
    sent = await deliver(
        [notice], sessions=sessions, sender=sender, owner_phone=owner_phone, prefix=prefix
    )
    if not sent:
        return 0
    async with sessions.begin() as session:
        for item in await session.scalars(select(NewsItem).where(NewsItem.id.in_(ids))):
            item.sent_at = now
    return len(ids)


async def boletim_cycle(
    *,
    sessions: async_sessionmaker[AsyncSession],
    llm: LLM,
    settings: object,
    clock: Clock,
    sender: SendsText,
    owner_phone: str,
    prefix: str = "",
) -> int:
    """Uma checagem: entrega o que ficou pendente, monta o boletim se for a hora e o entrega.
    Devolve quantas notícias foram de fato entregues."""
    if not getattr(settings, "noticias_ativo", True):
        return 0
    now = clock()
    out = dict(sessions=sessions, now=now, sender=sender, owner_phone=owner_phone, prefix=prefix)
    delivered = await deliver_pending(**out)
    async with sessions() as session:
        if not await due(session, now):
            return delivered
    profile = load_profile(getattr(settings, "noticias_perfil", "config/noticias.yaml"))
    if profile is None:
        return delivered
    model = getattr(settings, "noticias_modelo", "") or getattr(settings, "model_primary", "")
    async with sessions.begin() as session:
        await run_boletim(
            session,
            llm,
            model,
            profile,
            now,
            max_searches=int(getattr(settings, "noticias_max_buscas", 8)),
        )
    return delivered + await deliver_pending(**out)
