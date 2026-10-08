"""Jobs agendados (APScheduler no mesmo processo do FastAPI, fuso America/Sao_Paulo)."""

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import TZ, Clock
from app.reminders import jobs
from app.reminders.delivery import SendsText, deliver

log = logging.getLogger(__name__)

Job = Callable[[AsyncSession, datetime], Awaitable[list[jobs.Notice]]]


def build_scheduler(
    *,
    sessions: async_sessionmaker[AsyncSession],
    sender: SendsText,
    owner_phone: str,
    clock: Clock,
    prefix: str = "",
) -> AsyncIOScheduler:
    async def run(job: Job) -> None:
        try:
            async with sessions() as session:
                notices = await job(session, clock())
            sent = await deliver(
                notices, sessions=sessions, sender=sender, owner_phone=owner_phone, prefix=prefix
            )
            if sent:
                log.info("%s: %d aviso(s) enviado(s)", job.__name__, sent)
        except Exception:
            log.exception("job %s falhou", job.__name__)

    scheduler = AsyncIOScheduler(
        timezone=TZ, job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600}
    )
    scheduler.add_job(run, "cron", args=[jobs.daily_summary], hour=7, minute=30, id="resumo")
    scheduler.add_job(
        run,
        "interval",
        args=[jobs.event_reminders],
        minutes=5,
        id="lembretes",
        next_run_time=datetime.now(TZ),  # recupera atrasos logo que o app sobe
    )
    scheduler.add_job(run, "cron", args=[jobs.statement_alerts], hour=9, minute=0, id="fatura")
    return scheduler
