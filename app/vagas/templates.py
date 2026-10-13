"""Texto fixo da mensagem de vagas novas (sem LLM na redação). Change radar-vagas."""

from datetime import date

from app.db.models import JobLead

MAX_IN_MESSAGE = 8
TIPOS = {
    "estagio": "estágio",
    "bolsa": "bolsa de pesquisa",
    "monitoria": "monitoria",
    "junior": "júnior",
}


def ordered(leads: list[JobLead]) -> list[JobLead]:
    """Áreas de interesse primeiro (pontuação), depois o prazo mais próximo; sem prazo no fim."""
    return sorted(leads, key=lambda v: (-v.pontuacao, v.prazo or date.max))


def short_url(url: str) -> str:
    return url.split("://", 1)[-1]


def new_leads_message(leads: list[JobLead]) -> str:
    shown = ordered(leads)[:MAX_IN_MESSAGE]
    head = "🔎 1 vaga nova" if len(leads) == 1 else f"🔎 {len(leads)} vagas novas"
    if len(leads) > len(shown):
        head += f" (as {len(shown)} mais próximas do seu perfil)"
    lines = [head, ""]
    for v in shown:
        prazo = f"prazo {v.prazo:%d/%m}" if v.prazo else "sem prazo informado"
        lines.append(f"{v.codigo} · {v.titulo} — {v.organizacao} ({v.local})")
        lines.append(f"   {TIPOS.get(v.tipo, v.tipo)} · {prazo} · {short_url(v.url)}")
    lines += ["", f'Responda "não tenho interesse na {shown[0].codigo}" para esconder uma vaga.']
    return "\n".join(lines)
