"""Resumo do dia falado quando o Kaio diz só "Hey Jarvis": texto fixo, sem o modelo.

Clima do Open-Meteo (sem chave; só latitude e longitude saem do Mac); agenda, faturas e
manchetes do boletim de notícias, do `painel` do núcleo; pedidos de permissão de terminal
esperando resposta.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import httpx

log = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_TIMEOUT = 2.0
MAX_EVENTS = 5
BILL_DAYS = 3  # fatura que fecha ou vence em até 3 dias
RAIN_MIN = 30  # chance de chuva falada a partir de 30%
HEADLINES = 3  # manchetes do boletim de notícias, só os títulos
HEADLINE_CHARS = 70
DANGLING = {"e", "ou", "de", "da", "do", "das", "dos", "a", "o", "as", "os", "em", "no", "na"}
DANGLING |= {"para", "com", "por", "que", "um", "uma", "ao", "à", "sobre", "the", "of", "and"}


@dataclass(frozen=True)
class Weather:
    now: float
    high: float
    low: float
    rain: int  # chance máxima de chuva no dia, %


async def fetch_weather(
    lat: float, lon: float, client: httpx.AsyncClient | None = None
) -> Weather | None:
    """Clima de agora e do dia; None sem internet, com timeout ou resposta estranha."""
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "America/Sao_Paulo",
        "forecast_days": 1,
    }
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=WEATHER_TIMEOUT) as c:
                r = await c.get(FORECAST_URL, params=params)
        else:
            r = await client.get(FORECAST_URL, params=params, timeout=WEATHER_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        daily = data["daily"]
        return Weather(
            now=float(data["current"]["temperature_2m"]),
            high=float(daily["temperature_2m_max"][0]),
            low=float(daily["temperature_2m_min"][0]),
            rain=int(daily["precipitation_probability_max"][0] or 0),
        )
    except Exception as e:  # sem rede, timeout, JSON diferente: o resumo segue sem o clima
        log.info("resumo: clima indisponível (%s)", type(e).__name__)
        return None


def greeting(now: datetime) -> str:
    if now.hour < 12:
        return "Bom dia, senhor."
    if now.hour < 18:
        return "Boa tarde, senhor."
    return "Boa noite, senhor."


def _spoken_time(hhmm: str) -> str:
    h, m = hhmm.split(":")
    return f"{int(h)}h" if m == "00" else f"{int(h)}h{m}"


def _weather_text(w: Weather, city: str) -> str:
    text = (
        f"Agora faz {round(w.now)} graus em {city}, "
        f"máxima de {round(w.high)} e mínima de {round(w.low)}."
    )
    if w.rain >= RAIN_MIN:
        text += f" Chance de chuva de {w.rain}%."
    return text


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " e " + items[-1]


def _agenda_text(events: list[dict[str, Any]], now: datetime) -> str:
    """Compromissos de hoje que ainda não passaram (os de dia inteiro sempre entram)."""
    current = now.strftime("%H:%M")
    left = [e for e in events if e.get("hora") == "dia inteiro" or str(e.get("hora")) >= current]
    if not left:
        return (
            "O senhor não tem mais compromissos hoje."
            if events
            else "O senhor não tem compromissos hoje."
        )
    parts = []
    for e in left[:MAX_EVENTS]:
        title = str(e.get("titulo", "compromisso"))
        hora = e.get("hora")
        parts.append(title if hora == "dia inteiro" else f"{title} às {_spoken_time(str(hora))}")
    text = "Hoje o senhor tem " + _join(parts)
    extra = len(left) - MAX_EVENTS
    if extra > 0:
        text += f", e mais {extra}"
    return text + "."


def _br_date(text: str) -> date | None:
    try:
        return datetime.strptime(text, "%d/%m/%Y").date()
    except (TypeError, ValueError):
        return None


def _when(d: date, today: date) -> str:
    days = (d - today).days
    return {0: "hoje", 1: "amanhã"}.get(days, f"em {days} dias")


def _bills_text(bills: list[dict[str, Any]], today: date) -> str:
    said = []
    limit = today + timedelta(days=BILL_DAYS)
    for b in bills:
        card = b.get("cartao", "cartão")
        closes, due = _br_date(b.get("fechamento", "")), _br_date(b.get("vencimento", ""))
        if b.get("situacao") == "aberta" and closes and today <= closes <= limit:
            said.append(f"A fatura do {card} fecha {_when(closes, today)}, com {b.get('total')}.")
        elif due and today <= due <= limit:
            said.append(f"A fatura do {card} vence {_when(due, today)}: {b.get('total')}.")
    return " ".join(said)


def _cut(title: str, limit: int = HEADLINE_CHARS) -> str:
    """Corta numa fronteira de palavra, sem pontuação pendurada no fim."""
    title = title.strip().rstrip(".")
    if len(title) <= limit:
        return title
    words = title[:limit].rsplit(" ", 1)[0].rstrip(" ,;:—-").split()
    while len(words) > 1 and words[-1].lower() in DANGLING:  # "…dos alimentos e" soa cortado
        words.pop()
    return " ".join(words).rstrip(" ,;:—-")


def _news_text(news: dict[str, Any] | None, today: date) -> str:
    """As primeiras manchetes gerais da edição mais recente; antes do boletim de hoje sair, as de
    ontem (ou do dia), avisando de quando são."""
    if not news:
        return ""
    try:
        edition = date.fromisoformat(str(news.get("data")))
    except ValueError:
        return ""
    titles = [_cut(str(n.get("titulo", ""))) for n in news.get("itens", []) if not n.get("futebol")]
    titles = [t for t in titles if t][:HEADLINES]
    if not titles:
        return ""
    days = (today - edition).days
    when = "" if days <= 0 else " de ontem" if days == 1 else f" do dia {edition:%d/%m}"
    return f"Nas notícias{when}: " + ". ".join(titles) + "."


def compose(
    now: datetime,
    weather: Weather | None,
    panel: dict[str, Any] | None,
    pending_permissions: int = 0,
    city: str = "Brasília",
) -> str:
    """O texto do resumo; partes sem nada ficam de fora."""
    parts = [greeting(now)]
    if weather is not None:
        parts.append(_weather_text(weather, city))
    if panel is None:
        parts.append("A agenda está indisponível agora.")
    else:
        parts.append(_agenda_text(panel.get("agenda", {}).get("hoje", []), now))
        bills = _bills_text(panel.get("faturas", []), now.date())
        if bills:
            parts.append(bills)
        news = _news_text(panel.get("noticias"), now.date())
        if news:
            parts.append(news)
    if pending_permissions == 1:
        parts.append("Tem um pedido de permissão esperando no terminal.")
    elif pending_permissions > 1:
        parts.append(f"Tem {pending_permissions} pedidos de permissão esperando nos terminais.")
    return " ".join(parts)


# --- fechamento do dia ("Jarvis, boa noite") e avisos falados (jarvis-proativo)

EVENING_QUESTION = "O senhor teve algum gasto hoje que ainda não lançou?"
EVENING_EVENTS = 3


def _count(n: int) -> str:
    return "1 gasto" if n == 1 else f"{n} gastos"


def _tomorrow_text(events: list[dict[str, Any]], today: date) -> str:
    tomorrow = today + timedelta(days=1)
    items = [e for e in events if _br_date(str(e.get("data", "")).split(" ")[-1]) == tomorrow]
    if not items:
        return "Amanhã o senhor está livre."
    parts = []
    for e in items[:EVENING_EVENTS]:
        title = str(e.get("titulo", "compromisso"))
        hora = e.get("hora")
        parts.append(title if hora == "dia inteiro" else f"{title} às {_spoken_time(str(hora))}")
    text = "Amanhã o senhor tem " + _join(parts)
    extra = len(items) - EVENING_EVENTS
    return text + (f", e mais {extra}." if extra > 0 else ".")


def evening(now: datetime, panel: dict[str, Any] | None) -> str:
    """O fechamento do dia: gastos de hoje e do mês, a agenda de amanhã e a pergunta."""
    if panel is None:
        return "Boa noite, senhor. Os dados de gastos e agenda estão indisponíveis agora."
    hoje = panel.get("hoje") or {}
    n = int(hoje.get("lancamentos") or 0)
    mes = (panel.get("mes") or {}).get("total", "R$ 0,00")
    spent = (
        f"Hoje foram {_count(n)}, {hoje.get('total')}; no mês, {mes}."
        if n
        else f"Hoje nenhum gasto foi lançado; no mês, {mes}."
    )
    tomorrow = _tomorrow_text(panel.get("agenda", {}).get("proximos", []), now.date())
    return f"Boa noite, senhor. {spent} {tomorrow} {EVENING_QUESTION}"


VAGAS_SPOKEN = "Senhor, o radar encontrou vagas novas; estão no painel."
_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\u2300-\u23ff\u2600-\u27bf\u2b00-\u2bff\ufe0f\u200d]+"
)  # emojis e variações
_PARENS = re.compile(r"\s*\([^)]*\)")
_HHMM = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def spoken_notice(tipo: str, texto: str) -> str | None:
    """O texto falado de um aviso do núcleo; None quando o tipo não é falado (o boletim e o
    resumo das 07:30 o "Hey Jarvis" já fala)."""
    if tipo == "vagas":
        return VAGAS_SPOKEN
    if tipo not in ("evento", "fatura"):
        return None
    text = _EMOJI.sub("", texto)
    text = _PARENS.sub("", text)
    text = text.replace(" — ", ", ").replace("—", ",")
    text = _HHMM.sub(lambda m: _spoken_time(f"{m[1]}:{m[2]}"), text)
    text = " ".join(text.split())
    return text or None
