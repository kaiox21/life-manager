import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.agent.tools.agenda import (
    AtualizarEventoArgs,
    BuscarEventosArgs,
    CriarEventoArgs,
    RemoverEventoArgs,
    atualizar_evento,
    buscar_eventos,
    criar_evento,
    remover_evento,
)
from app.agent.tools.base import ToolError
from app.agent.tools.confirmacao import ConfirmarPendenteArgs, confirmar_pendente
from app.agent.tools.pessoas import GerenciarPessoaArgs, gerenciar_pessoa
from app.clock import TZ
from app.db.models import Event, Person


def evento(**kw) -> CriarEventoArgs:
    base = {"title": "Dentista", "kind": "compromisso", "starts_at": "2026-10-09T14:00:00-03:00"}
    return CriarEventoArgs(**(base | kw))


async def _events(ctx) -> list[Event]:
    return list((await ctx.session.scalars(select(Event).where(Event.deleted_at.is_(None)))).all())


async def test_cria_compromisso_com_hora(ctx):
    out = await criar_evento(ctx, evento())
    assert out["status"] == "criado"
    assert out["resumo"] == "Dentista — sexta 09/10/2026, 14:00"
    (ev,) = await _events(ctx)
    assert ev.starts_at == datetime(2026, 10, 9, 14, tzinfo=TZ)
    assert ev.gcal_synced_at is None  # pendente de sync
    assert ev.remind_minutes == [1440]


def test_hora_sem_fuso_e_sao_paulo():
    args = evento(starts_at="2026-10-09T14:00:00")
    assert args.starts_at == datetime(2026, 10, 9, 14, tzinfo=TZ)


async def test_aniversario_da_irma_resolve_pessoa_e_vira_anual(ctx):
    out = await criar_evento(
        ctx,
        evento(
            title="Aniversário da Mariana",
            kind="aniversario",
            starts_at="2026-03-14T00:00:00-03:00",
            person="minha irmã",
        ),
    )
    assert out["evento"]["pessoa"] == "Mariana"
    assert out["evento"]["recorrencia"] == "todo ano"
    (ev,) = await _events(ctx)
    assert ev.all_day and ev.rrule == "FREQ=YEARLY"


def test_dia_inteiro_normaliza_para_meia_noite():
    args = evento(kind="prazo", all_day=True, starts_at="2026-10-31T15:00:00-03:00")
    assert args.starts_at == datetime(2026, 10, 31, 0, tzinfo=TZ)


async def test_pessoa_nao_cadastrada_pede_nome(ctx):
    with pytest.raises(ToolError) as err:
        await criar_evento(ctx, evento(kind="aniversario", person="minha mãe"))
    assert "não cadastrada" in err.value.payload["erro"]


def test_validacoes():
    with pytest.raises(ValidationError):
        evento(kind="festa")
    with pytest.raises(ValidationError):
        evento(rrule="FREQ=NUNCA")
    with pytest.raises(ValidationError):
        evento(ends_at="2026-10-09T13:00:00-03:00")


async def test_busca_aniversario_pela_pessoa_traz_proxima_data(ctx):
    await criar_evento(
        ctx,
        evento(
            title="Aniversário da Mariana",
            kind="aniversario",
            starts_at="2026-03-14T00:00:00-03:00",
            person="Mariana",
        ),
    )
    out = await buscar_eventos(ctx, BuscarEventosArgs(kind="aniversario", person="minha irmã"))
    (item,) = out["eventos"]
    assert item["data"] == "domingo 14/03/2027"
    assert item["hora"] == "dia inteiro"


async def test_busca_por_periodo_e_texto(ctx):
    await criar_evento(ctx, evento())
    await criar_evento(
        ctx,
        evento(
            title="Prova de Direito Administrativo",
            kind="prova",
            starts_at="2026-10-20T19:00:00-03:00",
        ),
    )
    out = await buscar_eventos(ctx, BuscarEventosArgs(de="2026-10-09", ate="2026-10-09"))
    assert [e["titulo"] for e in out["eventos"]] == ["Dentista"]
    out = await buscar_eventos(ctx, BuscarEventosArgs(query="direito administrativo"))
    assert out["eventos"][0]["data"] == "terça 20/10/2026"
    out = await buscar_eventos(ctx, BuscarEventosArgs(query="dentísta"))
    assert out["total"] == 1


async def test_busca_sem_periodo_poe_passados_depois(ctx):
    await criar_evento(ctx, evento(title="Antigo", starts_at="2026-09-01T10:00:00-03:00"))
    await criar_evento(ctx, evento(title="Futuro"))
    out = await buscar_eventos(ctx, BuscarEventosArgs())
    assert [e["titulo"] for e in out["eventos"]] == ["Futuro", "Antigo"]
    assert out["eventos"][1]["ja_passou"] is True


async def test_atualiza_e_marca_para_sync(ctx):
    created = await criar_evento(ctx, evento())
    ev_id = uuid.UUID(created["evento"]["id"])
    (ev,) = await _events(ctx)
    ev.gcal_synced_at = ev.updated_at  # como se já tivesse ido ao Calendar
    out = await atualizar_evento(
        ctx, AtualizarEventoArgs(event_id=ev_id, campos={"starts_at": "2026-10-09T16:00:00-03:00"})
    )
    assert out["resumo"] == "Dentista — sexta 09/10/2026, 16:00"
    await ctx.session.refresh(ev)
    assert ev.updated_at >= ev.gcal_synced_at


async def test_atualizar_evento_inexistente(ctx):
    with pytest.raises(ToolError):
        await atualizar_evento(
            ctx, AtualizarEventoArgs(event_id=uuid.uuid4(), campos={"title": "x"})
        )


async def test_remover_sempre_pede_confirmacao(ctx):
    created = await criar_evento(ctx, evento(person="Carlos", title="Reunião com o Carlos"))
    ev_id = uuid.UUID(created["evento"]["id"])
    out = await remover_evento(ctx, RemoverEventoArgs(event_id=ev_id))
    assert out["status"] == "aguardando_confirmacao"
    assert len(await _events(ctx)) == 1
    done = await confirmar_pendente(ctx, ConfirmarPendenteArgs(decisao="sim"))
    assert done["status"] == "removido"
    assert await _events(ctx) == []
    ev = await ctx.session.get(Event, ev_id)
    assert ev.deleted_at is not None  # exclusão lógica


async def test_gerenciar_pessoa(ctx):
    out = await gerenciar_pessoa(ctx, GerenciarPessoaArgs(name="Ana", relation="mãe"))
    assert out == {"status": "criada", "pessoa": "Ana (mãe)"}
    out = await gerenciar_pessoa(ctx, GerenciarPessoaArgs(name="ana", aliases=["mãe"]))
    assert out["status"] == "atualizada"
    out = await criar_evento(
        ctx, evento(kind="aniversario", person="minha mãe", starts_at="2026-05-02T00:00:00-03:00")
    )
    assert out["evento"]["pessoa"] == "Ana"
    assert await ctx.session.scalar(select(Person).where(Person.name == "Ana"))
