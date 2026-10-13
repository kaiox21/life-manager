import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace as NS

from sqlalchemy import func, select

from app.agent.llm import Completion, ToolCall
from app.clock import TZ, fixed_clock
from app.db.models import AgentRun, JobLead, SentReminder
from app.vagas.job import due, radar_cycle
from app.vagas.radar import Profile, VagaIn, normalize_url, run_radar, score
from app.vagas.templates import new_leads_message
from tests.conftest import OWNER, FakeSender

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=TZ)
PROFILE = Profile(
    pessoa="Estudante de computação, curso noturno.",
    tipos=["estagio", "bolsa", "monitoria", "junior"],
    local={"cidade": "Brasília", "uf": "DF", "aceita": "Brasília ou remoto"},
    areas=[
        {"nome": "IA e dados", "peso": 3, "palavras": ["inteligência artificial", "dados", "llm"]},
        {"nome": "Web", "peso": 2, "palavras": ["react", "python"]},
    ],
    consultas=["estágio desenvolvimento Brasília"],
)
RESULTS = [
    "https://www.gupy.io/vagas/123?utm_source=google",
    "https://unb.br/editais/pibic-2026/",
    "https://empresa.com/jobs/dev-junior",
]


def search_completion(urls=RESULTS):
    raw = [
        {"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "x"}},
        {
            "type": "web_search_tool_result",
            "tool_use_id": "s1",
            "content": [{"type": "web_search_result", "url": u, "title": "t"} for u in urls],
        },
    ]
    return raw


def vaga(url, **kw):
    base = {
        "titulo": "Estágio em Desenvolvimento",
        "organizacao": "Empresa X",
        "tipo": "estagio",
        "local": "Brasília (híbrido)",
        "prazo": None,
        "url": url,
        "resumo": "Python e React",
    }
    return base | kw


class FakeLLM:
    """1ª chamada: busca e registra as vagas dadas (como a Anthropic com server tools)."""

    def __init__(self, vagas, register=True, urls=RESULTS):
        self.vagas, self.register, self.urls = vagas, register, urls
        self.calls = []

    async def chat(self, model, messages, tools=None, max_tokens=None, tool_choice=None):
        self.calls.append({"messages": messages, "tools": tools})
        calls = (
            [ToolCall("t1", "registrar_vagas", json.dumps({"vagas": self.vagas}))]
            if self.register or len(self.calls) > 1
            else []
        )
        return Completion(
            model=model,
            content=None,
            tool_calls=calls,
            input_tokens=20_000,
            output_tokens=500,
            cost_usd=Decimal("0.03"),
            raw=search_completion(self.urls),
            searches=3,
        )


def test_normaliza_url():
    assert normalize_url("https://www.Gupy.io/vagas/123/?utm_source=x&id=7#topo") == (
        "https://gupy.io/vagas/123?id=7"
    )


def test_pontuacao_por_area_e_prazo():
    v = VagaIn(**vaga("https://x", titulo="Estágio em dados e LLM", resumo=""))
    assert score(v, PROFILE, date(2026, 10, 13)) == 3
    v = VagaIn(**vaga("https://x", prazo="2026-10-15"))  # react/python (+2) e prazo em 2 dias (+1)
    assert score(v, PROFILE, date(2026, 10, 13)) == 3


async def test_so_entra_vaga_com_link_da_busca_nova_e_no_prazo(sessions):
    llm = FakeLLM(
        [
            vaga("https://gupy.io/vagas/123"),  # ok (mesma da busca, sem utm/www)
            vaga("https://inventada.com/vaga"),  # link fora da busca
            vaga("https://unb.br/editais/pibic-2026", tipo="bolsa", prazo="2026-10-01"),  # vencida
            vaga("https://empresa.com/jobs/dev-junior", tipo="junior", titulo="Dev Júnior IA"),
            vaga("https://empresa.com/jobs/dev-junior", tipo="junior"),  # repetida na rodada
        ]
    )
    async with sessions.begin() as s:
        result = await run_radar(s, llm, "haiku", PROFILE, NOW, max_searches=12)
    assert len(result.new) == 2 and all(v.codigo.startswith("V") for v in result.new)
    assert result.discarded == {"link_fora_da_busca": 1, "prazo_vencido": 1, "repetida": 1}
    async with sessions() as s:
        run = await s.scalar(select(AgentRun).where(AgentRun.channel == "vagas"))
        assert run.error is None and run.cost_usd == Decimal("0.03")
        assert run.tools_called[0]["buscas"] == 3
    # a busca foi oferecida com o teto de buscas e local Brasília
    search = next(t for t in llm.calls[0]["tools"] if t.get("type") == "anthropic_server")
    assert search["tool"]["max_uses"] == 12

    # na rodada seguinte, as mesmas não voltam
    async with sessions.begin() as s:
        again = await run_radar(
            s, FakeLLM([vaga("https://gupy.io/vagas/123")]), "haiku", PROFILE, NOW
        )
    assert again.new == [] and again.discarded == {"repetida": 1}


async def test_modelo_esquece_de_registrar_e_recebe_um_lembrete(sessions):
    llm = FakeLLM([vaga("https://gupy.io/vagas/123")], register=False)
    async with sessions.begin() as s:
        result = await run_radar(s, llm, "haiku", PROFILE, NOW)
    assert len(result.new) == 1 and len(llm.calls) == 2
    assert "registrar_vagas" in llm.calls[1]["messages"][-1]["content"]


async def test_falha_da_api_vira_rodada_com_erro(sessions):
    class Down:
        async def chat(self, *a, **k):
            raise RuntimeError("rede fora")

    async with sessions.begin() as s:
        result = await run_radar(s, Down(), "haiku", PROFILE, NOW)
    assert result.new == [] and "rede fora" in result.run.error


async def _add_run(sessions, at, error=None):
    async with sessions.begin() as s:
        s.add(AgentRun(channel="vagas", intent="vagas", error=error, created_at=at))


async def test_quando_rodar(sessions):
    async with sessions() as s:
        assert await due(s, NOW)  # nunca rodou
        assert not await due(s, NOW.replace(hour=23))  # fora das 08–22 h
    await _add_run(sessions, NOW - timedelta(hours=70))
    async with sessions() as s:
        assert not await due(s, NOW)  # rodou há menos de 72 h
        assert await due(s, NOW + timedelta(hours=3))  # Mac acordou mais tarde: já passou de 72 h


async def test_rodada_que_falha_tenta_de_novo_ate_duas_vezes_no_dia(sessions):
    await _add_run(sessions, NOW - timedelta(hours=1), error="rede fora")
    async with sessions() as s:
        assert await due(s, NOW)  # a que falhou não conta
    await _add_run(sessions, NOW - timedelta(minutes=5), error="rede fora")
    async with sessions() as s:
        assert not await due(s, NOW)  # já foram 2 tentativas hoje


async def test_ciclo_entrega_no_whatsapp_uma_vez(sessions, tmp_path):
    profile = tmp_path / "vagas.yaml"
    profile.write_text(
        "pessoa: x\ntipos: [estagio, junior]\nlocal: {cidade: Brasília, uf: DF, aceita: x}\n"
        "consultas: [a]\n"
    )
    settings = NS(
        vagas_ativo=True, vagas_perfil=str(profile), vagas_modelo="haiku", vagas_max_buscas=5
    )
    sender = FakeSender()
    llm = FakeLLM([vaga("https://gupy.io/vagas/123", prazo="2026-10-20")])
    kw = dict(
        sessions=sessions,
        llm=llm,
        settings=settings,
        clock=fixed_clock(NOW),
        sender=sender,
        owner_phone=OWNER,
    )
    assert await radar_cycle(**kw) == 1
    assert len(sender.sent) == 1 and "🔎 1 vaga nova" in sender.sent[0].text
    assert "prazo 20/10" in sender.sent[0].text and "gupy.io/vagas/123" in sender.sent[0].text
    async with sessions() as s:
        assert await s.scalar(select(func.count()).select_from(SentReminder)) == 1
        assert (await s.scalar(select(JobLead))).sent_at is not None
    assert await radar_cycle(**kw) == 0  # rodou agora: só daqui a 72 h
    assert len(sender.sent) == 1


async def test_rodada_sem_nada_novo_nao_manda_mensagem(sessions, tmp_path):
    profile = tmp_path / "vagas.yaml"
    profile.write_text("pessoa: x\ntipos: [estagio]\nlocal: {cidade: Brasília}\n")
    settings = NS(
        vagas_ativo=True, vagas_perfil=str(profile), vagas_modelo="haiku", vagas_max_buscas=5
    )
    sender = FakeSender()
    kw = dict(
        sessions=sessions,
        llm=FakeLLM([]),
        settings=settings,
        clock=fixed_clock(NOW),
        sender=sender,
        owner_phone=OWNER,
    )
    assert await radar_cycle(**kw) == 0 and sender.sent == []


async def test_sem_perfil_ou_desligado_nao_roda(sessions, tmp_path):
    sender = FakeSender()
    llm = FakeLLM([vaga("https://gupy.io/vagas/123")])
    base = dict(
        sessions=sessions, llm=llm, clock=fixed_clock(NOW), sender=sender, owner_phone=OWNER
    )
    off = NS(vagas_ativo=False, vagas_perfil="x", vagas_modelo="", vagas_max_buscas=5)
    missing = NS(
        vagas_ativo=True,
        vagas_perfil=str(tmp_path / "nao.yaml"),
        vagas_modelo="",
        vagas_max_buscas=5,
    )
    assert await radar_cycle(settings=off, **base) == 0
    assert await radar_cycle(settings=missing, **base) == 0
    assert llm.calls == []


def test_mensagem_ordena_por_area_e_prazo():
    def lead(codigo, pontos, prazo):
        return JobLead(
            codigo=codigo,
            url=f"https://x/{codigo}",
            titulo=codigo,
            organizacao="O",
            tipo="estagio",
            local="Remoto",
            prazo=prazo,
            resumo="",
            pontuacao=pontos,
        )

    text = new_leads_message(
        [lead("V1", 0, None), lead("V2", 3, date(2026, 11, 1)), lead("V3", 3, date(2026, 10, 20))]
    )
    order = [line.split(" · ")[0] for line in text.splitlines() if line.startswith("V")]
    assert order == ["V3", "V2", "V1"]
    assert 'Responda "não tenho interesse na V3"' in text


# --- conversa: listar e dispensar (pelo código ou pelo título)


async def _leads(ctx, *items):
    out = []
    for titulo, org, prazo in items:
        lead = JobLead(
            url=f"https://x.com/{titulo}",
            titulo=titulo,
            organizacao=org,
            tipo="estagio",
            local="Remoto",
            prazo=prazo,
            resumo="",
            pontuacao=0,
        )
        ctx.session.add(lead)
        out.append(lead)
    await ctx.session.flush()
    for lead in out:
        await ctx.session.refresh(lead, ["codigo", "found_at"])
    return out


async def test_listar_e_dispensar_pelo_codigo(ctx):
    from app.agent.tools.vagas import (
        DispensarVagaArgs,
        ListarVagasArgs,
        dispensar_vaga,
        listar_vagas,
    )

    a, b = await _leads(ctx, ("Estágio Dev", "Empresa A", None), ("Bolsa PIBIC", "UnB", None))
    got = await listar_vagas(ctx, ListarVagasArgs())
    assert {v["codigo"] for v in got["vagas"]} == {a.codigo, b.codigo}
    out = await dispensar_vaga(ctx, DispensarVagaArgs(vaga=a.codigo.lower()))
    assert out["status"] == "dispensada"
    got = await listar_vagas(ctx, ListarVagasArgs())
    assert [v["codigo"] for v in got["vagas"]] == [b.codigo]


async def test_dispensar_pelo_titulo_e_titulo_ambiguo(ctx):
    import pytest

    from app.agent.tools.base import ToolError
    from app.agent.tools.vagas import DispensarVagaArgs, dispensar_vaga

    await _leads(
        ctx, ("Estágio Dev Web", "Empresa A", None), ("Estágio Dev Dados", "Empresa B", None)
    )
    with pytest.raises(ToolError) as e:
        await dispensar_vaga(ctx, DispensarVagaArgs(vaga="estágio dev"))
    assert len(e.value.payload["opcoes"]) == 2  # não dispensa nada: pergunta
    out = await dispensar_vaga(ctx, DispensarVagaArgs(vaga="Empresa B"))
    assert out["vaga"]["organizacao"] == "Empresa B"


async def test_vaga_vencida_nao_aparece_na_lista(ctx):
    from app.agent.tools.vagas import ListarVagasArgs, listar_vagas

    hoje = ctx.clock().date()
    await _leads(
        ctx, ("Vencida", "A", hoje - timedelta(days=1)), ("Aberta", "B", hoje + timedelta(days=3))
    )
    got = await listar_vagas(ctx, ListarVagasArgs())
    assert [v["titulo"] for v in got["vagas"]] == ["Aberta"]
