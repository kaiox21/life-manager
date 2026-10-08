import asyncio
from datetime import datetime

from sqlalchemy import func, select

from app.clock import TZ
from app.db.models import Message, SentReminder
from app.reminders.delivery import deliver
from app.reminders.jobs import SUMMARY_REF, Notice
from app.types import OutgoingMessage
from tests.conftest import OWNER, FakeSender

NOTICE = Notice("resumo", SUMMARY_REF, datetime(2026, 10, 9, tzinfo=TZ), 0, "☀️ Bom dia!")


class FlakySender(FakeSender):
    def __init__(self, fails: int) -> None:
        super().__init__()
        self.fails = fails

    async def send_text(self, out: OutgoingMessage) -> str | None:
        if self.fails:
            self.fails -= 1
            raise RuntimeError("Evolution fora do ar")
        return await super().send_text(out)


async def _count(seeded, model):
    async with seeded() as s:
        return await s.scalar(select(func.count()).select_from(model))


async def test_envia_uma_vez_e_registra(seeded):
    sender = FakeSender()
    kw = dict(sessions=seeded, sender=sender, owner_phone=OWNER, prefix="🤖 ")
    assert await deliver([NOTICE], **kw) == 1
    assert await deliver([NOTICE], **kw) == 0
    assert [m.text for m in sender.sent] == ["🤖 ☀️ Bom dia!"]
    assert await _count(seeded, SentReminder) == 1
    assert await _count(seeded, Message) == 1


async def test_falha_no_envio_libera_para_tentar_de_novo(seeded):
    sender = FlakySender(fails=1)
    kw = dict(sessions=seeded, sender=sender, owner_phone=OWNER)
    assert await deliver([NOTICE], **kw) == 0
    assert await _count(seeded, SentReminder) == 0
    assert await deliver([NOTICE], **kw) == 1


async def test_ciclos_simultaneos_mandam_uma_vez(seeded):
    sender = FakeSender()
    kw = dict(sessions=seeded, sender=sender, owner_phone=OWNER)
    results = await asyncio.gather(*[deliver([NOTICE], **kw) for _ in range(5)])
    assert sum(results) == 1
    assert len(sender.sent) == 1
