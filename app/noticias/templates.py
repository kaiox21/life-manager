"""Texto fixo da mensagem do boletim (sem LLM na redação). Change boletim-noticias."""

from datetime import date

from app.agent.tools.agenda import WEEKDAYS
from app.db.models import NewsItem
from app.vagas.templates import short_url


def _line(n: NewsItem) -> str:
    return f"{n.titulo} — {n.resumo}" if n.resumo else n.titulo


def bulletin_message(items: list[NewsItem], edition: date) -> str:
    ordered = sorted(items, key=lambda n: n.posicao)
    gerais = [n for n in ordered if not n.futebol]
    futebol = [n for n in ordered if n.futebol]
    lines = [f"📰 Notícias de {WEEKDAYS[edition.weekday()]}, {edition:%d/%m}"]
    for i, n in enumerate(gerais, 1):
        lines += ["", f"{i}. {_line(n)}", f"   {n.fonte} · {short_url(n.url)}"]
    if futebol:
        lines += ["", "⚽ Futebol"]
        for n in futebol:
            lines += [f"• {_line(n)}", f"  {n.fonte} · {short_url(n.url)}"]
    return "\n".join(lines)
