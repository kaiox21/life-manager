"""Radar de vagas (change radar-vagas): pesquisa na internet com o perfil do Kaio e guarda só o
que é novo e tem link verificado.

Uma rodada é uma conversa com o modelo e duas ferramentas: `web_search` (a Anthropic executa) e
`registrar_vagas` (aqui, validada por Pydantic). Só entra vaga cujo link apareceu nos resultados
da própria busca: o modelo não pode inventar oportunidade.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import LLM, Completion, server_tool
from app.agent.tools.resolve import normalize
from app.db.models import AgentRun, JobLead
from app.web.links import normalize_url, search_urls, verified

log = logging.getLogger(__name__)

CHANNEL = "vagas"
MAX_ROUNDS = 3  # conversas com o modelo por rodada (pesquisar → registrar; um lembrete se faltar)
# Páginas de resultado de busca de agregadores: não são vagas (1ª rodada real, 13/10/2026: 3 de 7
# eram buscas do Indeed e do Infojobs).
SEARCH_PAGES = re.compile(
    r"(indeed\.com/(q-|jobs\?|empregos\?|m/jobs)"
    r"|infojobs\.com\.br/(vagas-de-emprego|empregos\.aspx)"
    r"|linkedin\.com/jobs/(search|[a-z-]+-vagas)"
    r"|catho\.com\.br/vagas/?(\?|$)"
    r"|glassdoor\.com(\.br)?/(Vaga|Job)/.+\.htm"
    r"|vagas\.com\.br/vagas-de-"
    r"|google\.com/search)",
    re.I,
)
MAX_AGE_DAYS = 60  # vaga publicada há mais que isso costuma estar encerrada


# --- perfil (config/vagas.yaml, fora do git)


class Area(BaseModel):
    nome: str
    peso: int = 1
    palavras: list[str] = []


class Profile(BaseModel):
    pessoa: str
    tipos: list[Literal["estagio", "bolsa", "monitoria", "junior"]]
    local: dict[str, str]
    areas: list[Area] = []
    restricoes: list[str] = []
    consultas: list[str] = []


def load_profile(path: str | Path) -> Profile | None:
    try:
        return Profile.model_validate(yaml.safe_load(Path(path).read_text()))
    except FileNotFoundError:
        log.warning("radar de vagas: sem o perfil em %s (copie config/vagas.example.yaml)", path)
    except (ValidationError, yaml.YAMLError, OSError) as e:
        log.warning("radar de vagas: perfil inválido em %s: %s", path, e)
    return None


# --- o que o modelo devolve


class VagaIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    titulo: str = Field(min_length=3, max_length=200)
    organizacao: str = Field(min_length=1, max_length=120)
    tipo: Literal["estagio", "bolsa", "monitoria", "junior"]
    local: str = Field(max_length=120, description="Ex.: 'Brasília (híbrido)' ou 'Remoto'")
    prazo: date | None = Field(default=None, description="Data limite de inscrição, AAAA-MM-DD")
    publicada: date | None = Field(
        default=None, description="Data de publicação, se aparecer no resultado (AAAA-MM-DD)"
    )
    url: str = Field(description="Link copiado de um resultado da busca")
    resumo: str = Field(default="", max_length=240, description="Uma linha: o que é e requisitos")


class RegistrarVagasArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vagas: list[VagaIn] = Field(description="Vagas do perfil achadas na busca (pode ser vazia)")


REGISTRAR = {
    "type": "function",
    "function": {
        "name": "registrar_vagas",
        "description": (
            "Registra as vagas encontradas. Chame UMA vez, no fim, depois das buscas. Só vagas "
            "do perfil, com o link exato de um resultado da busca."
        ),
        "parameters": RegistrarVagasArgs.model_json_schema(),
    },
}


# --- pontuação (no código, sem o modelo)


def score(v: VagaIn, profile: Profile, today: date) -> int:
    text = normalize(f"{v.titulo} {v.resumo}")
    points = 0
    for area in profile.areas:
        if any(re.search(rf"\b{re.escape(normalize(w))}\b", text) for w in area.palavras):
            points += area.peso
    if v.prazo is not None and (v.prazo - today).days <= 7:
        points += 1
    return points


# --- a rodada


@dataclass
class RadarResult:
    run: AgentRun
    new: list[JobLead] = field(default_factory=list)
    discarded: dict[str, int] = field(default_factory=dict)


def _prompt(profile: Profile, today: date, max_searches: int) -> str:
    tipos = ", ".join(profile.tipos)
    consultas = "\n".join(f"- {q}" for q in profile.consultas)
    aceita = profile.local.get("aceita", "")
    cidade = "-".join(x for x in (profile.local.get("cidade"), profile.local.get("uf")) if x)
    restricoes = "\n".join(f"- {r}" for r in profile.restricoes)
    return f"""Hoje é {today.isoformat()}. Você procura oportunidades para esta pessoa:
{profile.pessoa}

Tipos aceitos: {tipos} (estagio = estágio; bolsa = bolsa de pesquisa/iniciação
científica; monitoria = monitoria ou ensino; junior = emprego júnior ou trainee).
Local: {aceita} ({cidade}).
Restrições:
{restricoes}

Faça até {max_searches} buscas na web, em português, partindo destas sugestões (adapte se precisar):
{consultas}

Depois, chame registrar_vagas UMA vez com as vagas abertas que servem. Regras:
- use só links que apareceram nos resultados da busca, copiados exatamente;
  nunca monte ou adivinhe um link;
- não inclua vaga encerrada, com prazo já vencido ou fora do local e dos tipos aceitos;
- prazo só se estiver escrito no resultado; senão, deixe vazio;
- só a página de UMA vaga ou de UM edital; nunca página de resultado de busca ou lista de
  agregador (Indeed, Infojobs, LinkedIn, Catho, Glassdoor): procure a vaga dentro dela;
- prefira vagas publicadas nos últimos 30 dias; se o resultado mostrar a data de publicação,
  preencha "publicada"; não inclua anúncio marcado como encerrado ou expirado;
- divida as buscas entre os tipos aceitos: pelo menos 3 para bolsa e monitoria (editais da
  universidade, CNPq, fundação de amparo à pesquisa do estado), o resto para estágio e júnior;
- se nada servir, chame registrar_vagas com a lista vazia."""


async def run_radar(
    session: AsyncSession,
    llm: LLM,
    model: str,
    profile: Profile,
    now: datetime,
    max_searches: int = 12,
) -> RadarResult:
    started = time.monotonic()
    today = now.date()
    run = AgentRun(channel=CHANNEL, intent=CHANNEL, model=model, tools_called=[])
    session.add(run)
    tools = [
        server_tool(
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": max_searches,
                "user_location": {
                    "type": "approximate",
                    "city": profile.local.get("cidade", "Brasília"),
                    "country": "BR",
                    "timezone": "America/Sao_Paulo",
                },
            }
        ),
        REGISTRAR,
    ]
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": _prompt(profile, today, max_searches)}
    ]
    completions: list[Completion] = []
    vagas: list[VagaIn] | None = None
    error: str | None = None
    try:
        for _ in range(MAX_ROUNDS):
            c = await llm.chat(model, messages, tools=tools, max_tokens=4096)
            completions.append(c)
            call = next((t for t in c.tool_calls if t.name == "registrar_vagas"), None)
            if call is not None:
                try:
                    vagas = RegistrarVagasArgs.model_validate_json(call.arguments).vagas
                except ValidationError as e:
                    error = f"registrar_vagas inválido: {e.errors()[:2]}"
                break
            # terminou sem registrar: lembra uma vez (com os blocos da busca intactos)
            messages.append(c.assistant_message())
            messages.append(
                {"role": "user", "content": "Agora chame registrar_vagas com o que achou."}
            )
        else:
            error = "o modelo não chamou registrar_vagas"
    except Exception as e:  # rede, API: a rodada conta como falha e é tentada de novo
        error = f"{type(e).__name__}: {e}"[:500]
        log.exception("radar de vagas: falha na pesquisa")

    result = RadarResult(run=run)
    allowed = search_urls(completions)
    for v in vagas or []:
        reason = None
        if not verified(v.url, allowed):
            reason = "link_fora_da_busca"
        elif SEARCH_PAGES.search(v.url):
            reason = "pagina_de_busca"
        elif v.publicada is not None and (today - v.publicada).days > MAX_AGE_DAYS:
            reason = "antiga"
        elif v.tipo not in profile.tipos:
            reason = "tipo_fora_do_perfil"
        elif v.prazo is not None and v.prazo < today:
            reason = "prazo_vencido"
        else:
            url = normalize_url(v.url)
            known = await session.scalar(select(JobLead.id).where(JobLead.url == url))
            if known is not None or any(lead.url == url for lead in result.new):
                reason = "repetida"
        if reason:
            result.discarded[reason] = result.discarded.get(reason, 0) + 1
            continue
        lead = JobLead(
            url=normalize_url(v.url),
            titulo=v.titulo.strip(),
            organizacao=v.organizacao.strip(),
            tipo=v.tipo,
            local=v.local.strip(),
            prazo=v.prazo,
            resumo=v.resumo.strip(),
            pontuacao=score(v, profile, today),
        )
        result.new.append(lead)

    searches = sum(c.searches for c in completions)
    run.input_tokens = sum(c.input_tokens for c in completions)
    run.output_tokens = sum(c.output_tokens for c in completions)
    run.cost_usd = sum((c.cost_usd for c in completions), Decimal(0))
    run.latency_ms = int((time.monotonic() - started) * 1000)
    run.error = error
    run.tools_called = [
        {"name": "web_search", "buscas": searches, "resultados": len(allowed)},
        {
            "name": "registrar_vagas",
            "recebidas": len(vagas or []),
            "novas": len(result.new),
            "descartadas": result.discarded,
        },
    ]
    await session.flush()  # o id da rodada, para ligar as vagas a ela
    for lead in result.new:
        lead.run_id = run.id
        session.add(lead)
    await session.flush()  # os códigos (V12…) saem da sequência do banco
    for lead in result.new:
        await session.refresh(lead, ["codigo"])
    log.info(
        "radar de vagas: %d busca(s), %d resultado(s), %d nova(s), descartadas %s, US$ %.3f%s",
        searches,
        len(allowed),
        len(result.new),
        json.dumps(result.discarded),
        float(run.cost_usd or 0),
        f", erro: {error}" if error else "",
    )
    return result
