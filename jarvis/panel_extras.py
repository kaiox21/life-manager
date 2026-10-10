"""Dados locais do painel HUD, sem o modelo: clima, Mac, música, projetos e dias até a fatura
fechar. Cada parte que falha vira None (o cartão diz "indisponível"); nada aqui soma valores.
"""

from __future__ import annotations

import asyncio
import calendar
import logging
import re
import time
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jarvis.briefing import Weather, fetch_weather
from jarvis.sessions import Folders

log = logging.getLogger(__name__)

WEATHER_TTL = 600.0
MAX_PROJECTS = 6
TIMEOUT = 2.0

Run = Callable[[list[str], bytes | None], Awaitable[Any]]

_SPOTIFY_NOW = [
    "osascript",
    "-e",
    'if application "Spotify" is running then',
    "-e",
    'tell application "Spotify" to if player state is not stopped then '
    "return (name of current track) & tab & (artist of current track) & tab & "
    "(player state as string)",
    "-e",
    "end if",
    "-e",
    'return ""',
]


def parse_swap(text: str) -> float | None:
    """`vm.swapusage` ("total = 2048.00M  used = 812.25M  free = …") → GB usados."""
    m = re.search(r"used\s*=\s*([\d.]+)([MG])", text)
    if not m:
        return None
    value = float(m.group(1))
    return round(value / 1024 if m.group(2) == "M" else value, 1)


def parse_battery(text: str) -> dict[str, Any] | None:
    """`pmset -g batt` → {"pct", "carregando"}; None num Mac sem bateria."""
    m = re.search(r"(\d+)%;\s*([\w ]+?);", text)
    if not m:
        return None
    state = m.group(2).strip().lower()
    return {
        "pct": int(m.group(1)),
        "carregando": state in ("charging", "charged", "finishing charge"),
    }


def _br_date(text: Any) -> date | None:
    try:
        return datetime.strptime(str(text), "%d/%m/%Y").date()
    except ValueError:
        return None


def _prev_month(d: date) -> date:
    y, m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def bill_days(faturas: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    """Cada fatura com `dias_para_fechar` e `fracao_ciclo` (0–1), a partir do fechamento que já
    vem pronto do núcleo; a que fecha primeiro vem primeiro."""
    out = []
    for f in faturas:
        closes = _br_date(f.get("fechamento"))
        if closes is None:
            out.append(dict(f))
            continue
        start = _prev_month(closes)  # o fechamento anterior (mesmo dia, mês passado)
        cycle = max(1, (closes - start).days)
        out.append(
            {
                **f,
                "dias_para_fechar": (closes - today).days,
                "fracao_ciclo": round(min(1.0, max(0.0, (today - start).days / cycle)), 2),
            }
        )
    return sorted(out, key=lambda f: f.get("dias_para_fechar", 10_000))


class PanelExtras:
    def __init__(
        self,
        run: Run,
        folders: Folders,
        config: Callable[[], dict[str, Any]],
        weather_place: Callable[[], tuple[float, float, str]],
        fetch: Callable[[float, float], Awaitable[Weather | None]] = fetch_weather,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._run = run
        self._folders = folders
        self._config = config
        self._place = weather_place
        self._fetch = fetch
        self._clock = clock
        self._today = today
        self._weather: tuple[float, dict[str, Any] | None] | None = None

    async def __call__(self, faturas: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        clima, mac, musica = await asyncio.gather(
            self._safe(self.weather()), self._safe(self.mac()), self._safe(self.music())
        )
        out: dict[str, Any] = {
            "clima": clima,
            "mac": mac,
            "musica": musica,
            "projetos": self.projects(),
        }
        if faturas is not None:
            out["faturas"] = bill_days(faturas, self._today())
        return out

    @staticmethod
    async def _safe(coro: Awaitable[Any]) -> Any:
        try:
            return await coro
        except Exception:  # noqa: BLE001 (um cartão indisponível não derruba o painel)
            log.info("painel: dado local indisponível", exc_info=True)
            return None

    async def weather(self) -> dict[str, Any] | None:
        if self._weather and self._clock() - self._weather[0] < WEATHER_TTL:
            return self._weather[1]
        lat, lon, city = self._place()
        w = await self._fetch(lat, lon)
        data = (
            None
            if w is None
            else {"agora": w.now, "max": w.high, "min": w.low, "chuva": w.rain, "cidade": city}
        )
        self._weather = (self._clock(), data)
        return data

    async def _out(self, argv: list[str]) -> str | None:
        r = await asyncio.wait_for(self._run(argv, None), TIMEOUT)
        return r.stdout if r.returncode == 0 else None

    async def mac(self) -> dict[str, Any] | None:
        mem, swap, batt = await asyncio.gather(
            self._out(["/usr/sbin/sysctl", "-n", "kern.memorystatus_level"]),
            self._out(["/usr/sbin/sysctl", "-n", "vm.swapusage"]),
            self._out(["/usr/bin/pmset", "-g", "batt"]),
            return_exceptions=True,
        )
        free = int(mem.strip()) if isinstance(mem, str) and mem.strip().isdigit() else None
        return {
            "memoria_livre": free,
            "swap_gb": parse_swap(swap) if isinstance(swap, str) else None,
            "bateria": parse_battery(batt) if isinstance(batt, str) else None,
        }

    async def music(self) -> dict[str, Any] | None:
        out = await self._out(_SPOTIFY_NOW)
        parts = (out or "").strip().split("\t")
        if len(parts) != 3:
            return None  # Spotify fechado ou parado
        return {"faixa": parts[0], "artista": parts[1], "tocando": parts[2] == "playing"}

    def projects(self) -> list[dict[str, str]]:
        chosen = self._config().get("projetos")
        paths: list[Path] = []
        if isinstance(chosen, list) and chosen:
            for item in chosen:
                found = self._folders.resolve(str(item))
                if "pasta" in found:
                    paths.append(found["pasta"])
        else:
            subdirs: list[Path] = []
            for root in self._folders.roots:
                try:
                    subdirs += [
                        c for c in root.iterdir() if c.is_dir() and not c.name.startswith(".")
                    ]
                except OSError:
                    continue
            subdirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            paths = subdirs
        out, seen = [], set()
        for p in paths:
            if p in seen or not self._folders.allowed(p):
                continue
            seen.add(p)
            out.append({"nome": p.name, "caminho": str(p)})
            if len(out) == MAX_PROJECTS:
                break
        return out
