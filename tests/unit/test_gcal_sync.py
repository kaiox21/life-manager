from datetime import datetime, timedelta

from sqlalchemy import select

from app.clock import TZ
from app.db.models import Event
from app.integrations.gcal import NotFoundError, event_body, sync_pending


class FakeCalendar:
    def __init__(self, fail_times: int = 0) -> None:
        self.events: dict[str, dict] = {}
        self.calls: list[str] = []
        self.fail_times = fail_times

    async def insert(self, body):
        self.calls.append("insert")
        if self.fail_times:
            self.fail_times -= 1
            raise RuntimeError("Calendar fora do ar")
        gid = f"g{len(self.events) + 1}"
        self.events[gid] = body
        return gid

    async def update(self, event_id, body):
        self.calls.append("update")
        if event_id not in self.events:
            raise NotFoundError
        self.events[event_id] = body

    async def delete(self, event_id):
        self.calls.append("delete")
        if event_id not in self.events:
            raise NotFoundError
        del self.events[event_id]


T0 = datetime(2026, 10, 7, 12, tzinfo=TZ)


def _ev(**kw) -> Event:
    base = dict(
        title="Dentista",
        kind="compromisso",
        starts_at=datetime(2026, 10, 9, 14, tzinfo=TZ),
        all_day=False,
        created_at=T0,
        updated_at=T0,
    )
    return Event(**(base | kw))


def test_body_com_hora_tem_fuso_e_1h_padrao():
    body = event_body(_ev())
    assert body["start"] == {
        "dateTime": "2026-10-09T14:00:00-03:00",
        "timeZone": "America/Sao_Paulo",
    }
    assert body["end"]["dateTime"] == "2026-10-09T15:00:00-03:00"
    assert body["reminders"] == {"useDefault": False}
    assert "recurrence" not in body


def test_body_dia_inteiro_anual_com_fim_exclusivo():
    body = event_body(
        _ev(
            title="Aniversário",
            kind="aniversario",
            all_day=True,
            rrule="FREQ=YEARLY",
            starts_at=datetime(2026, 3, 14, tzinfo=TZ),
        )
    )
    assert body["start"] == {"date": "2026-03-14"}
    assert body["end"] == {"date": "2026-03-15"}
    assert body["recurrence"] == ["RRULE:FREQ=YEARLY"]


async def _all(seeded):
    async with seeded() as s:
        return list((await s.scalars(select(Event))).all())


async def test_cria_atualiza_e_apaga(seeded):
    cal = FakeCalendar()
    async with seeded.begin() as s:
        s.add(_ev())
    report = await sync_pending(seeded, cal)
    assert report.created == 1
    (ev,) = await _all(seeded)
    assert ev.gcal_event_id == "g1" and ev.gcal_synced_at == ev.updated_at

    # nada pendente: nenhuma chamada
    cal.calls.clear()
    await sync_pending(seeded, cal)
    assert cal.calls == []

    async with seeded.begin() as s:
        ev = await s.get(Event, ev.id)
        ev.title = "Dentista (remarcado)"
        ev.updated_at = T0 + timedelta(minutes=5)
    assert (await sync_pending(seeded, cal)).updated == 1
    assert cal.events["g1"]["summary"] == "Dentista (remarcado)"

    async with seeded.begin() as s:
        ev = await s.get(Event, ev.id)
        ev.deleted_at = ev.updated_at = T0 + timedelta(minutes=10)
    assert (await sync_pending(seeded, cal)).deleted == 1
    assert cal.events == {}


async def test_falha_do_calendar_nao_perde_o_evento(seeded):
    cal = FakeCalendar(fail_times=1)
    async with seeded.begin() as s:
        s.add(_ev())
    report = await sync_pending(seeded, cal)
    assert report.failed and report.created == 0
    (ev,) = await _all(seeded)
    assert ev.gcal_event_id is None and ev.gcal_synced_at is None
    assert (await sync_pending(seeded, cal)).created == 1


async def test_evento_sumido_do_calendar_e_recriado(seeded):
    cal = FakeCalendar()
    async with seeded.begin() as s:
        s.add(_ev(gcal_event_id="apagado-a-mao"))
    report = await sync_pending(seeded, cal)
    assert report.created == 1
    (ev,) = await _all(seeded)
    assert ev.gcal_event_id == "g1"


async def test_removido_que_nunca_foi_ao_calendar_e_ignorado(seeded):
    cal = FakeCalendar()
    async with seeded.begin() as s:
        s.add(_ev(deleted_at=T0))
    await sync_pending(seeded, cal)
    assert cal.calls == []
