"""Resumo do dia falado quando o Kaio diz só "Hey Jarvis": texto fixo, sem o modelo.

Clima do Open-Meteo (sem chave; só latitude e longitude saem do Mac), agenda e faturas do
`painel` do núcleo e pedidos de permissão de terminal esperando resposta.
"""

from __future__ import annotations

import logging
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
        f"Agora fazem {round(w.now)} graus em {city}, "
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
    if pending_permissions == 1:
        parts.append("Tem um pedido de permissão esperando no terminal.")
    elif pending_permissions > 1:
        parts.append(f"Tem {pending_permissions} pedidos de permissão esperando nos terminais.")
    return " ".join(parts)
