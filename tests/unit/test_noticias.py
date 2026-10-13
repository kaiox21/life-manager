import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace as NS

from sqlalchemy import func, select

from app.agent.llm import Completion, ToolCall
from app.clock import TZ, fixed_clock
from app.db.models import AgentRun, NewsItem, SentReminder
from app.noticias.boletim import Profile, run_boletim, similar, source_name
from app.noticias.job import boletim_cycle, due
from app.noticias.templates import bulletin_message
from app.web.links import page_age, search_results
from tests.conftest import OWNER, FakeSender

NOW = datetime(2026, 10, 13, 7, 30, tzinfo=TZ)
FONTES = {
    "g1.globo.com": "G1",
    "ge.globo.com": "ge",
    "globo.com": "Globo",
    "bbc.com": "BBC",
    "folha.uol.com.br": "Folha",
    "uol.com.br": "UOL",
    "jota.info": "JOTA",
}
PROFILE = Profile(
    temas=[
        {"chave": "tecnologia", "nome": "Tecnologia e IA"},
        {"chave": "direito", "nome": "Direito e Judiciário"},
        {"chave": "brasil", "nome": "Brasil e política"},
        {"chave": "mundo", "nome": "Mundo"},
    ],
    gerais=2,
    futebol=1,
    times=["Flamengo", "Barcelona"],
    fontes=FONTES,
)
RESULTS = [
    ("https://g1.globo.com/tecnologia/noticia/ia-nova.ghtml?utm_source=x", "2 hours ago"),
    ("https://www.bbc.com/news/articles/abc", "October 13, 2026"),
    ("https://jota.info/stf/julgamento", None),
    ("https://ge.globo.com/futebol/times/flamengo/vence.ghtml", "3 hours ago"),
    ("https://ge.globo.com/futebol/barcelona/empata.ghtml", None),
    ("https://folha.uol.com.br/velha", "October 1, 2026"),
    ("https://naoesta.com/noticia", None),
]


def raw(results=RESULTS):
    return [
        {"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "x"}},
        {
            "type": "web_search_tool_result",
            "tool_use_id": "s1",
            "content": [
                {"type": "web_search_result", "url": u, "title": "t", "page_age": age}
                for u, age in results
            ],
        },
    ]


def nota(url, titulo, tema="tecnologia", **kw):
    return {"titulo": titulo, "resumo": "Uma linha.", "url": url, "tema": tema} | kw


class FakeLLM:
    def __init__(self, gerais, futebol=(), register=True, results=RESULTS):
        self.args = {"gerais": list(gerais), "futebol": list(futebol)}
        self.register, self.results = register, results
        self.calls = []

    async def chat(self, model, messages, tools=None, max_tokens=None, tool_choice=None):
        self.calls.append({"messages": messages, "tools": tools})
        calls = (
            [ToolCall("t1", "registrar_noticias", json.dumps(self.args))]
            if self.register or len(self.calls) > 1
            else []
        )
        return Completion(
            model=model,
            content=None,
            tool_calls=calls,
            input_tokens=15_000,
            output_tokens=600,
            cost_usd=Decimal("0.02"),
            raw=raw(self.results),
            searches=4,
        )


# --- base: links e idade


def test_fonte_pelo_dominio_mais_especifico():
    assert source_name("https://g1.globo.com/x", FONTES) == "G1"
    assert source_name("https://ge.globo.com/futebol/x", FONTES) == "ge"
    assert source_name("https://oglobo.globo.com/x", FONTES) == "Globo"
    assert source_name("https://www.folha.uol.com.br/a", FONTES) == "Folha"
    assert source_name("https://noticias.uol.com.br/a", FONTES) == "UOL"
    assert source_name("https://naoesta.com/a", FONTES) is None
    assert source_name("https://fakebbc.com/a", FONTES) is None  # não é subdomínio
    assert source_name("https://site.com/esporte/x", {"site.com/esporte": "S"}) == "S"
    assert source_name("https://site.com/politica/x", {"site.com/esporte": "S"}) is None


def test_dominios_da_busca_sem_caminho_e_sem_repetir():
    p = PROFILE.model_copy(update={"fontes": {"site.com/esporte": "S", "site.com": "T"}})
    assert p.domains() == ["site.com"]


def test_idade_do_resultado():
    now = NOW
    assert page_age("2 hours ago", now) == now - timedelta(hours=2)
    assert page_age("há 3 dias", now) == now - timedelta(days=3)
    assert page_age("April 30, 2025", now).date() == date(2025, 4, 30)
    assert page_age("30 de abril de 2025", now).date() == date(2025, 4, 30)
    assert page_age("Oct 12, 2026", now).date() == date(2026, 10, 12)
    assert page_age("2026-10-12T22:00:00Z", now).date() == date(2026, 10, 12)
    assert page_age("2026-10-12", now).date() == date(2026, 10, 12)
    assert page_age(None, now) is None and page_age("ontem à tarde", now) is None


def test_resultados_da_busca_com_idade():
    got = search_results([NS(raw=raw())])
    assert got["https://g1.globo.com/tecnologia/noticia/ia-nova.ghtml"] == "2 hours ago"
    assert got["https://jota.info/stf/julgamento"] is None


def test_titulos_parecidos():
    assert similar("STF julga marco temporal nesta quarta", "STF julga o marco temporal na quarta")
    assert not similar("STF julga marco temporal", "Flamengo vence o Palmeiras")


# --- a rodada


async def test_filtros_corte_e_fonte_pelo_dominio(sessions):
    llm = FakeLLM(
        [
            nota("https://naoesta.com/noticia", "Fonte fora da lista"),  # domínio fora
            nota("https://inventada.com/x", "Link inventado"),  # fora da busca
            nota("https://folha.uol.com.br/velha", "Notícia velha de outubro"),  # 12 dias
            nota(
                "https://g1.globo.com/tecnologia/noticia/ia-nova.ghtml",
                "Nova IA lançada",
                fonte="X",
            ),
            nota("https://www.bbc.com/news/articles/abc", "Eleição na França", tema="mundo"),
            nota("https://jota.info/stf/julgamento", "STF julga caso", tema="direito"),  # 3ª: corte
        ],
        futebol=[
            nota("https://ge.globo.com/futebol/times/flamengo/vence.ghtml", "Flamengo vence"),
            nota("https://ge.globo.com/futebol/barcelona/empata.ghtml", "Barcelona empata"),
        ],
    )
    async with sessions.begin() as s:
        result = await run_boletim(s, llm, "haiku", PROFILE, NOW, max_searches=8)
    assert [(n.titulo, n.fonte, n.posicao, n.futebol) for n in result.new] == [
        ("Nova IA lançada", "G1", 1, False),
        ("Eleição na França", "BBC", 2, False),
        ("Flamengo vence", "ge", 3, True),
    ]
    assert result.new[2].tema == "futebol" and result.new[0].edition == NOW.date()
    assert result.discarded == {"fonte_fora_da_lista": 1, "link_fora_da_busca": 1, "antiga": 1}
    search = next(t for t in llm.calls[0]["tools"] if t.get("type") == "anthropic_server")
    assert search["tool"]["max_uses"] == 8
    assert "g1.globo.com" in search["tool"]["allowed_domains"]
    assert "português" in llm.calls[0]["messages"][0]["content"]
    async with sessions() as s:
        run = await s.scalar(select(AgentRun).where(AgentRun.channel == "noticias"))
        assert run.error is None and run.tools_called[0]["buscas"] == 4


async def test_repetida_e_parecida_com_os_dias_anteriores(sessions):
    async with sessions.begin() as s:
        s.add(
            NewsItem(
                url="https://jota.info/stf/julgamento",
                titulo="x",
                fonte="JOTA",
                tema="direito",
                posicao=1,
                edition=NOW.date() - timedelta(days=1),
            )
        )
        s.add(
            NewsItem(
                url="https://g1.globo.com/antiga",
                titulo="STF julga marco temporal nesta quarta",
                fonte="G1",
                tema="direito",
                posicao=2,
                edition=NOW.date() - timedelta(days=2),
            )
        )
    llm = FakeLLM(
        [
            nota("https://jota.info/stf/julgamento", "Outro título"),  # mesma URL
            nota("https://www.bbc.com/news/articles/abc", "STF julga o marco temporal na quarta"),
            nota("https://g1.globo.com/tecnologia/noticia/ia-nova.ghtml", "Nova IA"),
            nota("https://ge.globo.com/futebol/barcelona/empata.ghtml", "A nova IA lançada"),
        ]
    )
    async with sessions.begin() as s:
        result = await run_boletim(s, llm, "haiku", PROFILE.model_copy(update={"gerais": 5}), NOW)
    assert [n.titulo for n in result.new] == ["Nova IA"]
    assert result.discarded == {"repetida": 1, "parecida": 2}


async def test_lembrete_e_falha(sessions):
    llm = FakeLLM([nota("https://www.bbc.com/news/articles/abc", "Eleição")], register=False)
    async with sessions.begin() as s:
        result = await run_boletim(s, llm, "haiku", PROFILE, NOW)
    assert len(result.new) == 1 and len(llm.calls) == 2

    class Down:
        async def chat(self, *a, **k):
            raise RuntimeError("rede fora")

    async with sessions.begin() as s:
        result = await run_boletim(s, Down(), "haiku", PROFILE, NOW)
    assert result.new == [] and "rede fora" in result.run.error


# --- agenda e entrega


async def _add_run(sessions, at, error=None):
    async with sessions.begin() as s:
        s.add(AgentRun(channel="noticias", intent="noticias", error=error, created_at=at))


async def test_quando_rodar(sessions):
    async with sessions() as s:
        assert await due(s, NOW)
        assert not await due(s, NOW.replace(hour=7, minute=0))  # antes das 07:30
        assert not await due(s, NOW.replace(hour=22, minute=10))
    await _add_run(sessions, NOW - timedelta(days=1))  # ontem não conta
    await _add_run(sessions, NOW + timedelta(minutes=5), error="rede fora")
    async with sessions() as s:
        assert await due(s, NOW + timedelta(hours=2))  # Mac acordou: falhou uma, tenta de novo
    await _add_run(sessions, NOW + timedelta(minutes=35), error="rede fora")
    async with sessions() as s:
        assert not await due(s, NOW + timedelta(hours=2))  # 2 tentativas hoje
        assert await due(s, NOW + timedelta(days=1))  # amanhã de novo


async def test_ciclo_entrega_uma_vez_e_so_um_por_dia(sessions, tmp_path):
    from tests.unit.test_reminder_delivery import FlakySender

    perfil = tmp_path / "noticias.yaml"
    perfil.write_text(PROFILE.model_dump_json())  # JSON é YAML
    settings = NS(
        noticias_ativo=True,
        noticias_perfil=str(perfil),
        noticias_modelo="haiku",
        noticias_max_buscas=8,
    )
    sender = FlakySender(fails=1)
    llm = FakeLLM(
        [nota("https://www.bbc.com/news/articles/abc", "Eleição na França", tema="mundo")],
        futebol=[nota("https://ge.globo.com/futebol/times/flamengo/vence.ghtml", "Fla vence")],
    )
    kw = dict(sessions=sessions, llm=llm, settings=settings, sender=sender, owner_phone=OWNER)
    assert await boletim_cycle(clock=fixed_clock(NOW), **kw) == 0  # WhatsApp caiu no envio
    assert await boletim_cycle(clock=fixed_clock(NOW + timedelta(minutes=30)), **kw) == 2
    assert len(llm.calls) == 1 and len(sender.sent) == 1
    text = sender.sent[0].text
    assert text.startswith("📰 Notícias de terça, 13/10")
    assert "1. Eleição na França — Uma linha." in text and "BBC · bbc.com/news/articles/abc" in text
    assert "⚽ Futebol\n• Fla vence" in text
    assert await boletim_cycle(clock=fixed_clock(NOW + timedelta(hours=1)), **kw) == 0
    assert len(sender.sent) == 1 and len(llm.calls) == 1
    async with sessions() as s:
        assert await s.scalar(select(func.count()).select_from(SentReminder)) == 1


async def test_boletim_vazio_nao_manda_e_desligado_nao_roda(sessions, tmp_path):
    perfil = tmp_path / "noticias.yaml"
    perfil.write_text(PROFILE.model_dump_json())
    sender = FakeSender()
    base = dict(sessions=sessions, clock=fixed_clock(NOW), sender=sender, owner_phone=OWNER)
    on = NS(noticias_ativo=True, noticias_perfil=str(perfil), noticias_modelo="h")
    assert await boletim_cycle(llm=FakeLLM([]), settings=on, **base) == 0
    off = NS(noticias_ativo=False, noticias_perfil=str(perfil))
    llm = FakeLLM([nota("https://www.bbc.com/news/articles/abc", "Eleição")])
    assert await boletim_cycle(llm=llm, settings=off, **base) == 0
    assert sender.sent == [] and llm.calls == []


def test_mensagem_sem_futebol():
    item = NewsItem(
        url="https://g1.globo.com/a",
        titulo="Título",
        resumo="",
        fonte="G1",
        tema="brasil",
        futebol=False,
        posicao=1,
    )
    text = bulletin_message([item], date(2026, 10, 12))
    assert text == "📰 Notícias de segunda, 12/10\n\n1. Título\n   G1 · g1.globo.com/a"


async def test_fonte_bloqueada_pela_busca_segue_sem_ela(sessions):
    """1ª rodada real (13/10/2026): a API recusa o pedido inteiro se um domínio bloqueia o robô."""

    class Blocks(FakeLLM):
        async def chat(self, model, messages, tools=None, **kw):
            search = tools[0]["tool"]
            if "bbc.com" in search["allowed_domains"]:
                self.calls.append({"messages": messages, "tools": tools})
                raise RuntimeError(
                    "Error code: 400 - {'message': \"The following domains are not accessible "
                    "to our user agent: ['bbc.com', 'uol.com.br']. Read more: https://x\"}"
                )
            return await super().chat(model, messages, tools=tools, **kw)

    llm = Blocks([nota("https://g1.globo.com/tecnologia/noticia/ia-nova.ghtml", "Nova IA")])
    async with sessions.begin() as s:
        result = await run_boletim(s, llm, "haiku", PROFILE, NOW)
    assert [n.titulo for n in result.new] == ["Nova IA"] and result.run.error is None
    domains = llm.calls[-1]["tools"][0]["tool"]["allowed_domains"]
    assert "bbc.com" not in domains and "uol.com.br" not in domains and "g1.globo.com" in domains
