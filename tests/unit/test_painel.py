from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.agent.tools.agenda import CriarEventoArgs, criar_evento
from app.agent.tools.consultas import TotalFaturaArgs, total_fatura
from app.agent.tools.gastos import LancarGastoArgs, SemArgs, desfazer_ultimo, lancar_gasto
from app.agent.tools.painel import painel
from app.clock import TZ
from app.db.models import Event, Expense, Message


async def _gasto(ctx, **kw) -> None:
    base = {"amount_cents": 4790, "description": "almoço", "payment_method": "nubank"}
    await lancar_gasto(ctx, LancarGastoArgs(**(base | kw)))


async def _carimbar(ctx, minutos_atras: int) -> None:
    """Na mesma transação o now() do Postgres é igual para tudo: fixa a ordem de criação."""
    when = datetime(2026, 10, 7, 12, 0, tzinfo=TZ) - timedelta(minutes=minutos_atras)
    for model in (Expense, Event):
        for row in (await ctx.session.scalars(select(model).where(model.created_at > when))).all():
            row.created_at = when
    await ctx.session.flush()


async def test_fatura_aberta_igual_a_total_fatura(ctx):
    await _gasto(ctx, amount_cents=4790)
    await _gasto(ctx, amount_cents=1000, payment_method="itaú crédito", spent_on="2026-10-01")
    out = await painel(ctx)

    faturas = {f["cartao"]: f for f in out["faturas"]}
    assert set(faturas) == {"Nubank", "Itaú Crédito"}  # débito e Pix não têm fatura
    nubank = faturas["Nubank"]
    assert nubank["mes_vencimento"] == "2026-11"
    conversa = await total_fatura(
        ctx, TotalFaturaArgs(payment_method="Nubank", mes_vencimento="2026-11")
    )
    assert nubank["total_centavos"] == conversa["total_centavos"] == 4790
    assert nubank["vencimento"] == "08/11/2026"
    assert nubank["fechamento"] == "31/10/2026"
    assert "maiores_itens" not in nubank
    assert faturas["Itaú Crédito"]["mes_vencimento"] == "2026-11"  # fecha 25, vence 5
    assert faturas["Itaú Crédito"]["total_centavos"] == 1000


async def test_mes_por_categoria_sem_excluidos(ctx):
    await _gasto(ctx, amount_cents=4790, description="almoço", category="Alimentação")
    await _gasto(ctx, amount_cents=3000, description="uber", category="Transporte")
    await _gasto(ctx, amount_cents=9999, description="engano", category="Lazer")
    await desfazer_ultimo(ctx, SemArgs())
    await _gasto(ctx, amount_cents=500, description="setembro", spent_on="2026-09-30")

    mes = (await painel(ctx))["mes"]
    assert mes["total_centavos"] == 7790
    grupos = {g["grupo"]: g["total_centavos"] for g in mes["grupos"]}
    assert grupos == {"Alimentação": 4790, "Transporte": 3000}


async def test_registro_parcelada_uma_vez_e_origem(ctx):
    msg = Message(channel="whatsapp", direction="in", type="text", body="47 no almoço")
    ctx.session.add(msg)
    await ctx.session.flush()
    await _gasto(ctx, amount_cents=4790)
    await ctx.session.execute(
        Expense.__table__.update().where(Expense.amount_cents == 4790).values(message_id=msg.id)
    )
    await _carimbar(ctx, 30)
    await _gasto(ctx, amount_cents=30000, description="fone", installments=3)
    await _carimbar(ctx, 20)
    await criar_evento(
        ctx,
        CriarEventoArgs(title="Prova de CIC", kind="prova", starts_at="2026-10-09T10:00:00"),
    )
    await _carimbar(ctx, 10)
    await _gasto(ctx, amount_cents=999, description="engano")
    await desfazer_ultimo(ctx, SemArgs())

    registro = (await painel(ctx))["registro"]
    assert [i["tipo"] for i in registro] == ["evento", "gasto", "gasto"]
    evento, fone, almoco = registro
    assert evento["texto"] == "Prova de CIC · sexta 09/10/2026 10:00"
    assert evento["origem"] is None
    assert fone["texto"] == "fone · 3× de R$ 100,00 · Nubank"
    assert fone["origem"] == "mac"
    assert almoco["texto"] == "almoço · R$ 47,90 · Nubank"
    assert almoco["origem"] == "whatsapp"


async def test_agenda_hoje_e_proximos_7_dias_com_recorrencia(ctx):
    await criar_evento(
        ctx, CriarEventoArgs(title="Dentista", kind="compromisso", starts_at="2026-10-07T15:00:00")
    )
    await criar_evento(
        ctx, CriarEventoArgs(title="Prova", kind="prova", starts_at="2026-10-14T19:00:00")
    )
    await criar_evento(
        ctx, CriarEventoArgs(title="Longe", kind="prova", starts_at="2026-10-15T19:00:00")
    )
    await criar_evento(
        ctx,
        CriarEventoArgs(
            title="Aniversário",
            kind="aniversario",
            starts_at="2020-10-10T00:00:00",
            all_day=True,
            rrule="FREQ=YEARLY",
            person="Mariana",
        ),
    )
    agenda = (await painel(ctx))["agenda"]
    assert [e["titulo"] for e in agenda["hoje"]] == ["Dentista"]
    assert [e["titulo"] for e in agenda["proximos"]] == ["Aniversário", "Prova"]


async def test_sem_dados(ctx):
    out = await painel(ctx)
    assert out["agora"].startswith("2026-10-07T12:00")
    assert out["agenda"] == {"hoje": [], "proximos": []}
    assert out["mes"]["total_centavos"] == 0
    assert out["registro"] == []
    assert {f["total_centavos"] for f in out["faturas"]} == {0}
    assert date.fromisoformat(out["agora"][:10]) == date(2026, 10, 7)
