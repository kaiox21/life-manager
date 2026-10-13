"""Links que vieram da busca na internet: normalização e verificação. Usado pelo radar de vagas
e pelo boletim de notícias: só entra o que tem link copiado de um resultado da própria busca.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.agent.tools.resolve import normalize

TRACKING = re.compile(r"^(utm_.*|gclid|fbclid|ref|trk|trackingid|src|source|origin)$", re.I)


def normalize_url(url: str) -> str:
    """Domínio em minúsculas sem www, sem fragmento, sem parâmetros de rastreio, sem barra final."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not TRACKING.match(k)])
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower() or "https", host, path, query, ""))


def host(url: str) -> str:
    return urlsplit(normalize_url(url)).netloc


@dataclass(frozen=True)
class Hit:
    """Um resultado da busca: título da página e `page_age` (texto, quando veio)."""

    title: str = ""
    page_age: str | None = None


def search_results(completions: list[Any]) -> dict[str, Hit]:
    """URL normalizada → resultado, para cada resultado da busca da rodada."""
    out: dict[str, Hit] = {}
    for c in completions:
        for block in c.raw or []:
            if block.get("type") != "web_search_tool_result":
                continue
            content = block.get("content")
            for item in content if isinstance(content, list) else []:
                if isinstance(item, dict) and item.get("url"):
                    url = normalize_url(item["url"])
                    if url not in out:
                        out[url] = Hit(str(item.get("title") or ""), item.get("page_age") or None)
    return out


def search_urls(completions: list[Any]) -> set[str]:
    """URLs que vieram nos resultados da busca da rodada (as únicas aceitas)."""
    return set(search_results(completions))


def verified(url: str, allowed: set[str] | dict[str, Any]) -> bool:
    return normalize_url(url) in allowed


# --- idade do resultado (`page_age`): "April 30, 2025", "30 de abril de 2025", "3 hours ago"…

# 3 primeiras letras do mês, em inglês e em português ("Oct", "October", "outubro", "out.")
MONTHS = {
    **dict.fromkeys(("jan",), 1),
    **dict.fromkeys(("feb", "fev"), 2),
    **dict.fromkeys(("mar",), 3),
    **dict.fromkeys(("apr", "abr"), 4),
    **dict.fromkeys(("may", "mai"), 5),
    **dict.fromkeys(("jun",), 6),
    **dict.fromkeys(("jul",), 7),
    **dict.fromkeys(("aug", "ago"), 8),
    **dict.fromkeys(("sep", "set"), 9),
    **dict.fromkeys(("oct", "out"), 10),
    **dict.fromkeys(("nov",), 11),
    **dict.fromkeys(("dec", "dez"), 12),
}
AGO = re.compile(r"(\d+)\s*(minute|min|hour|hora|day|dia|week|semana)s?\b", re.I)
UNITS = {"minute": 1 / 60, "min": 1 / 60, "hour": 1, "hora": 1, "day": 24, "dia": 24}
UNITS |= {"week": 168, "semana": 168}


def page_age(text: str | None, now: datetime) -> datetime | None:
    """Data de publicação lida com tolerância; None quando não dá para saber."""
    if not text:
        return None
    raw = text.strip()
    try:
        d = datetime.fromisoformat(raw)
        return d if d.tzinfo else d.replace(tzinfo=now.tzinfo)
    except ValueError:
        pass
    low = normalize(raw)  # minúsculas, sem acento
    m = AGO.search(low)
    if m and re.search(r"\b(ago|atras|ha)\b", low):
        return now - timedelta(hours=int(m.group(1)) * UNITS[m.group(2).lower()])
    words = re.findall(r"[a-z]+|\d+", low)
    month = next((MONTHS[w[:3]] for w in words if len(w) >= 3 and w[:3] in MONTHS), None)
    nums = [int(w) for w in words if w.isdigit()]
    year = next((n for n in nums if n > 1900), None)
    day = next((n for n in nums if 1 <= n <= 31), None)
    if month and year and day:
        try:
            return datetime(year, month, day, 12, tzinfo=now.tzinfo)
        except ValueError:
            return None
    return None
