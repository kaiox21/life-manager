from datetime import datetime

from sqlalchemy import select

from app.agent.tools.gastos import LancarGastoArgs, SemArgs, desfazer_ultimo, lancar_gasto
from app.clock import TZ, fixed_clock
from app.db.models import Event, Person
from app.reminders.jobs import daily_summary, event_reminders, statement_alerts


def dt(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=TZ)


def _ev(**kw) -> Event:
    base = dict(
        title="Dentista",
        kind="compromisso",
        starts_at=dt(2026, 10, 9, 15, 10),
        all_day=False,
        remind_minutes=[60],
    )
    return Event(**(base | kw))


async def _add(seeded, *events):
    async with seeded.begin() as s:
        s.add_all(events)


async def _run(seeded, job, now):
    async with seeded() as s:
        return await job(s, now)


async def test_lembrete_de_60_min_dispara_na_janela(seeded):
    await _add(seeded, _ev())
    assert await _run(seeded, event_reminders, dt(2026, 10, 9, 14, 5)) == []
    (n,) = await _run(seeded, event_reminders, dt(2026, 10, 9, 14, 10))
    assert n.kind == "evento" and n.minutes_before == 60
    assert n.occurrence_at == dt(2026, 10, 9, 15, 10)
    assert n.text == "⏰ Dentista: hoje às 15:10 — em 1 h."
    # mesmo aviso continua elegível (a deduplicação fica na entrega)
    assert len(await _run(seeded, event_reminders, dt(2026, 10, 9, 14, 15))) == 1


async def test_evento_que_ja_comecou_nao_avisa(seeded):
    await _add(seeded, _ev())
    assert await _run(seeded, event_reminders, dt(2026, 10, 9, 15, 30)) == []


async def test_atraso_recuperado_ate_6h(seeded):
    await _add(seeded, _ev(starts_at=dt(2026, 10, 10, 20, 0), remind_minutes=[1440]))
    # aviso devido em 09/10 20:00; app voltou 5 h depois
    assert len(await _run(seeded, event_reminders, dt(2026, 10, 10, 1, 0))) == 1
    # mais de 6 h de atraso: perdido
    assert await _run(seeded, event_reminders, dt(2026, 10, 10, 2, 30)) == []


async def test_varias_antecedencias(seeded):
    await _add(seeded, _ev(remind_minutes=[1440, 60]))
    (a,) = await _run(seeded, event_reminders, dt(2026, 10, 8, 15, 12))
    assert a.minutes_before == 1440 and a.text == "⏰ Dentista: amanhã às 15:10 — em 1 dia."
    (b,) = await _run(seeded, event_reminders, dt(2026, 10, 9, 14, 12))
    assert b.minutes_before == 60


async def test_aniversario_anual_avisa_na_vespera_as_9h(seeded):
    async with seeded() as s:
        mariana = await s.scalar(select(Person).where(Person.name == "Mariana"))
    await _add(
        seeded,
        _ev(
            title="Aniversário da Mariana",
            kind="aniversario",
            all_day=True,
            rrule="FREQ=YEARLY",
            starts_at=dt(2020, 3, 14),
            remind_minutes=[1440],
            person_id=mariana.id,
        ),
    )
    assert await _run(seeded, event_reminders, dt(2027, 3, 13, 8, 55)) == []
    (n,) = await _run(seeded, event_reminders, dt(2027, 3, 13, 9, 0))
    assert n.occurrence_at == dt(2027, 3, 14)
    assert n.text == "🎂 Amanhã é aniversário: Mariana (14/03)."


async def test_evento_excluido_nao_avisa(seeded):
    await _add(seeded, _ev(deleted_at=dt(2026, 10, 8)))
    assert await _run(seeded, event_reminders, dt(2026, 10, 9, 14, 10)) == []


async def test_resumo_do_dia(seeded):
    await _add(
        seeded,
        _ev(),
        _ev(title="Prova de Direito", kind="prova", starts_at=dt(2026, 10, 10, 19)),
        _ev(
            title="Aniversário do Carlos",
            kind="aniversario",
            all_day=True,
            rrule="FREQ=YEARLY",
            starts_at=dt(2000, 10, 12),
        ),
    )
    (n,) = await _run(seeded, daily_summary, dt(2026, 10, 9, 7, 30))
    assert n.kind == "resumo" and n.occurrence_at == dt(2026, 10, 9)
    assert n.text == (
        "☀️ Bom dia! Sexta, 09/10.\n"
        "Hoje:\n• 15:10 Dentista\n"
        "Amanhã:\n• 19:00 Prova de Direito\n"
        "Aniversários da semana:\n• segunda 12/10: Aniversário do Carlos"
    )


async def test_resumo_vazio_nao_envia(seeded):
    assert await _run(seeded, daily_summary, dt(2026, 10, 9, 7, 30)) == []


async def _gasto(seeded, **kw):
    async with seeded.begin() as s:
        from app.agent.tools.base import ToolContext

        ctx = ToolContext(session=s, clock=fixed_clock(dt(2026, 10, 7, 12)))
        base = {"amount_cents": 4790, "description": "almoço", "payment_method": "nubank"}
        await lancar_gasto(ctx, LancarGastoArgs(**(base | kw)))
        return ctx


async def test_fatura_avisa_2_dias_antes_do_ultimo_dia(seeded):
    await _gasto(seeded)
    await _gasto(seeded, amount_cents=21000, description="mercado")
    assert await _run(seeded, statement_alerts, dt(2026, 10, 28, 9)) == []
    notices = await _run(seeded, statement_alerts, dt(2026, 10, 29, 9))
    (n,) = [x for x in notices if "Nubank" in x.text]
    assert n.text == (
        "💳 A fatura do Nubank fecha em 2 dias (31/10). "
        "Parcial: R$ 257,90 (2 lançamentos). Vence 08/11/2026."
    )
    # novembro tem 30 dias: fecha 30/11, avisa 28/11 (fatura sem gasto vai com zero)
    (nov,) = [
        x for x in await _run(seeded, statement_alerts, dt(2026, 11, 28, 9)) if "Nubank" in x.text
    ]
    assert "R$ 0,00" in nov.text and "(30/11)" in nov.text


async def test_fatura_ignora_desfeitos(seeded):
    await _gasto(seeded)
    async with seeded.begin() as s:
        from app.agent.tools.base import ToolContext

        await desfazer_ultimo(
            ToolContext(session=s, clock=fixed_clock(dt(2026, 10, 7, 13))), SemArgs()
        )
    (n,) = [
        x for x in await _run(seeded, statement_alerts, dt(2026, 10, 29, 9)) if "Nubank" in x.text
    ]
    assert "R$ 0,00 (0 lançamentos)" in n.text


async def test_cartao_que_fecha_dia_25(seeded):
    notices = await _run(seeded, statement_alerts, dt(2026, 10, 23, 9))
    assert [x.text.split(" fecha")[0] for x in notices] == ["💳 A fatura do Itaú Crédito"]
    assert "Vence 05/11/2026" in notices[0].text
