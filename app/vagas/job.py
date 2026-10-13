"""Quando o radar roda e a entrega pelo WhatsApp. Change radar-vagas.

Checagem a cada hora das 08:00 às 22:00 (e na subida): roda se a última rodada sem erro foi há
72 h ou mais e se hoje houve menos de 2 tentativas. Um job diário às 08:00 não bastava: o
APScheduler desiste de um job atrasado mais de 1 h, e com o Mac dormindo às 08:00 a rodada
ficaria para o dia seguinte. O próprio agent_runs diz quando foi a última rodada.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.llm import LLM
from app.clock import TZ, Clock
from app.db.models import AgentRun, JobLead
from app.reminders.delivery import SendsText, deliver
from app.reminders.jobs import Notice
from app.vagas.radar import CHANNEL, load_profile, run_radar
from app.vagas.templates import new_leads_message

log = logging.getLogger(__name__)

EVERY = timedelta(hours=72)
MAX_ATTEMPTS_PER_DAY = 2
FIRST_HOUR, LAST_HOUR = 8, 22


async def due(session: AsyncSession, now: datetime) -> bool:
    local = now.astimezone(TZ)
    if not FIRST_HOUR <= local.hour < LAST_HOUR:
        return False
    last_ok = await session.scalar(
        select(func.max(AgentRun.created_at)).where(
            AgentRun.channel == CHANNEL, AgentRun.error.is_(None)
        )
    )
    if last_ok is not None and now - last_ok < EVERY:
        return False
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    attempts = await session.scalar(
        select(func.count(AgentRun.id)).where(
            AgentRun.channel == CHANNEL, AgentRun.created_at >= midnight
        )
    )
    return (attempts or 0) < MAX_ATTEMPTS_PER_DAY


async def radar_cycle(
    *,
    sessions: async_sessionmaker[AsyncSession],
    llm: LLM,
    settings: object,
    clock: Clock,
    sender: SendsText,
    owner_phone: str,
    prefix: str = "",
) -> int:
    """Uma checagem: roda o radar se for a hora e entrega as vagas novas. Devolve quantas."""
    if not getattr(settings, "vagas_ativo", True):
        return 0
    now = clock()
    async with sessions() as session:
        if not await due(session, now):
            return 0
    profile = load_profile(getattr(settings, "vagas_perfil", "config/vagas.yaml"))
    if profile is None:
        return 0
    model = getattr(settings, "vagas_modelo", "") or getattr(settings, "model_primary", "")
    async with sessions.begin() as session:
        result = await run_radar(
            session,
            llm,
            model,
            profile,
            now,
            max_searches=int(getattr(settings, "vagas_max_buscas", 12)),
        )
        run_id = result.run.id
        text = new_leads_message(result.new) if result.new else None
        ids = [v.id for v in result.new]
    if text is None:
        return 0
    notice = Notice(kind="vagas", ref_id=run_id, occurrence_at=now, minutes_before=0, text=text)
    sent = await deliver(
        [notice], sessions=sessions, sender=sender, owner_phone=owner_phone, prefix=prefix
    )
    if sent:
        async with sessions.begin() as session:
            for lead in await session.scalars(select(JobLead).where(JobLead.id.in_(ids))):
                lead.sent_at = now
    return len(ids)
