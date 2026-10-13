from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from jarvis.briefing import Weather, compose, fetch_weather

TZ = ZoneInfo("America/Sao_Paulo")
SUN = Weather(now=22.4, high=31.2, low=17.6, rain=10)


def at(h, m=0):
    return datetime(2026, 10, 10, h, m, tzinfo=TZ)


def panel(hoje=(), faturas=()):
    return {"agenda": {"hoje": list(hoje), "proximos": []}, "faturas": list(faturas)}


def ev(titulo, hora):
    return {"titulo": titulo, "hora": hora, "data": "sábado 10/10/2026"}


def test_bom_dia_com_clima_e_compromissos():
    text = compose(at(8), SUN, panel([ev("Reunião", "14:00"), ev("Aula", "19:30")]))
    assert text == (
        "Bom dia, senhor. Agora faz 22 graus em Brasília, máxima de 31 e mínima de 18."
        " Hoje o senhor tem Reunião às 14h e Aula às 19h30."
    )


def test_cumprimento_pela_hora():
    assert compose(at(13), None, panel()).startswith("Boa tarde, senhor.")
    assert compose(at(20), None, panel()).startswith("Boa noite, senhor.")


def test_chuva_so_a_partir_de_30():
    assert "chuva" not in compose(at(8), SUN, panel())
    rain = Weather(now=20, high=25, low=18, rain=70)
    assert "Chance de chuva de 70%." in compose(at(8), rain, panel())


def test_dia_vazio_e_compromissos_que_ja_passaram():
    assert "O senhor não tem compromissos hoje." in compose(at(8), None, panel())
    text = compose(at(20), None, panel([ev("Reunião", "14:00")]))
    assert "O senhor não tem mais compromissos hoje." in text


def test_dia_inteiro_e_limite_de_cinco():
    hoje = [ev("Aniversário da Ana", "dia inteiro")] + [ev(f"E{i}", f"1{i}:00") for i in range(6)]
    text = compose(at(8), None, panel(hoje))
    assert text.endswith(
        "Hoje o senhor tem Aniversário da Ana, E0 às 10h, E1 às 11h, E2 às 12h"
        " e E3 às 13h, e mais 2."
    )


def test_fatura_perto_de_fechar_ou_vencer():
    faturas = [
        {
            "cartao": "Nubank",
            "fechamento": "12/10/2026",
            "vencimento": "19/10/2026",
            "situacao": "aberta",
            "total": "R$ 812,40",
        },
        {
            "cartao": "Inter",
            "fechamento": "01/10/2026",
            "vencimento": "11/10/2026",
            "situacao": "fechada",
            "total": "R$ 300,00",
        },
        {
            "cartao": "Itaú",
            "fechamento": "25/10/2026",
            "vencimento": "02/11/2026",
            "situacao": "aberta",
            "total": "R$ 50,00",
        },
    ]
    text = compose(at(8), None, panel(faturas=faturas))
    assert "A fatura do Nubank fecha em 2 dias, com R$ 812,40." in text
    assert "A fatura do Inter vence amanhã: R$ 300,00." in text
    assert "Itaú" not in text


def test_sem_nucleo_e_permissoes():
    text = compose(at(8), None, None, pending_permissions=2)
    assert "A agenda está indisponível agora." in text
    assert "Tem 2 pedidos de permissão esperando nos terminais." in text
    assert "Tem um pedido" in compose(at(8), None, panel(), pending_permissions=1)


async def test_clima_do_open_meteo_e_sem_rede():
    def ok(request):
        assert request.url.params["latitude"] == "-15.79"
        return httpx.Response(
            200,
            json={
                "current": {"temperature_2m": 32.3},
                "daily": {
                    "temperature_2m_max": [33.6],
                    "temperature_2m_min": [22.0],
                    "precipitation_probability_max": [None],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(ok)) as c:
        assert await fetch_weather(-15.79, -47.88, c) == Weather(32.3, 33.6, 22.0, 0)

    def down(request):
        raise httpx.ConnectError("sem rede")

    async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as c:
        assert await fetch_weather(-15.79, -47.88, c) is None


LONGO = (
    "Governo anuncia pacote de medidas para conter a alta dos alimentos e reduzir tarifas de "
    "importação"
)


def boletim(data="2026-10-10"):
    itens = [
        {"titulo": LONGO, "futebol": False},
        {"titulo": "Flamengo vence o Palmeiras por 2 a 1", "futebol": True},
        {"titulo": "STF julga o marco temporal.", "futebol": False},
        {"titulo": "Nova IA do Google chega ao Brasil", "futebol": False},
        {"titulo": "Quarta geral não entra", "futebol": False},
    ]
    return {"data": data, "itens": itens}


def test_manchetes_do_boletim_de_hoje_depois_da_agenda():
    p = panel([ev("Aula", "19:30")]) | {"noticias": boletim()}
    text = compose(at(8), None, p)
    assert text.endswith(
        "Hoje o senhor tem Aula às 19h30. Nas notícias: Governo anuncia pacote de medidas para"
        " conter a alta dos alimentos. STF julga o marco temporal. Nova IA do Google"
        " chega ao Brasil."
    )
    assert "Flamengo" not in text and "Quarta geral" not in text


def test_boletim_de_ontem_nao_e_falado():
    p = panel() | {"noticias": boletim("2026-10-09")}
    assert "notícias" not in compose(at(1), None, p)
    assert "notícias" not in compose(at(8), None, panel() | {"noticias": None})


def test_resumo_cheio_cabe_em_30_segundos():
    """Manhã cheia: clima com chuva, 3 compromissos, uma fatura e 3 manchetes longas. A voz fala
    ~15 caracteres por segundo; o resumo inteiro fica em ~30 s (aceite do boletim-noticias)."""
    fatura = {
        "cartao": "Nubank",
        "situacao": "aberta",
        "fechamento": "11/10/2026",
        "vencimento": "18/10/2026",
        "total": "R$ 1.234,56",
    }
    itens = [{"titulo": LONGO, "futebol": False}] * 3
    p = panel([ev("Reunião", "10:00"), ev("Almoço", "12:30"), ev("Aula", "19:30")], [fatura])
    text = compose(
        at(7, 45), Weather(22, 31, 18, 60), p | {"noticias": {"data": "2026-10-10", "itens": itens}}
    )
    assert len(text) / 15 <= 32, len(text)
