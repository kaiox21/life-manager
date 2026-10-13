"""Boletim de notícias (change boletim-noticias): pesquisa na internet as notícias do dia nos
temas do Kaio e no futebol, e guarda só o que tem link verificado, é recente e é novo.

Como o radar de vagas, uma rodada é uma conversa com `web_search` (restrita às fontes do perfil)
e uma ferramenta local, `registrar_noticias`. O nome da fonte sai do domínio do link, pela
tabela do perfil; o que o modelo escreve como fonte não é usado.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import LLM, Completion, server_tool
from app.agent.tools.resolve import normalize
from app.clock import TZ
from app.db.models import AgentRun, NewsItem
from app.web.links import normalize_url, page_age, search_results

log = logging.getLogger(__name__)

CHANNEL = "noticias"
MAX_ROUNDS = 3  # pesquisar → registrar; um lembrete se faltar
MAX_AGE = timedelta(hours=36)
HISTORY_DAYS = 3  # título parecido com um destes dias não volta
SIMILAR = 0.6  # Jaccard entre os conjuntos de palavras dos títulos
# palavras que não contam na comparação de títulos (já sem acento)
TITLE_STOPWORDS = {
    *("a", "o", "as", "os", "um", "uma", "de", "da", "do", "das", "dos", "e", "em", "no", "na"),
    *("nos", "nas", "por", "para", "com", "sem", "que", "se", "ao", "aos"),
    *("the", "of", "to", "in", "on", "for", "and", "is", "are"),
}
Tema = Literal["tecnologia", "direito", "brasil", "mundo", "futebol"]


# --- perfil (config/noticias.yaml, fora do git)


class TemaPerfil(BaseModel):
    chave: Tema
    nome: str
    descricao: str = ""


class Profile(BaseModel):
    temas: list[TemaPerfil]
    gerais: int = 5
    futebol: int = 3
    times: list[str] = []
    fontes: dict[str, str]  # domínio (ou domínio/caminho) → nome mostrado

    def domains(self) -> list[str]:
        """Para o `allowed_domains` da busca: só o domínio, sem repetir."""
        return sorted({k.split("/", 1)[0].lower().removeprefix("www.") for k in self.fontes})


def load_profile(path: str | Path) -> Profile | None:
    try:
        return Profile.model_validate(yaml.safe_load(Path(path).read_text()))
    except FileNotFoundError:
        log.warning("boletim: sem o perfil em %s (copie config/noticias.example.yaml)", path)
    except (ValidationError, yaml.YAMLError, OSError) as e:
        log.warning("boletim: perfil inválido em %s: %s", path, e)
    return None


def source_name(url: str, fontes: dict[str, str]) -> str | None:
    """Nome da fonte pelo link: a entrada mais específica da tabela que casa com o domínio (e o
    caminho, se a entrada tiver); None quando o domínio não está na lista."""
    parts = urlsplit(normalize_url(url))
    host, path = parts.netloc, parts.path
    best: tuple[int, str] | None = None
    for key, name in fontes.items():
        k_host, _, k_path = key.lower().removeprefix("www.").partition("/")
        if not (host == k_host or host.endswith("." + k_host)):
            continue
        if k_path and not path.lstrip("/").startswith(k_path):
            continue
        if best is None or len(key) > best[0]:
            best = (len(key), name)
    return best[1] if best else None


# --- o que o modelo devolve


class NoticiaIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    titulo: str = Field(min_length=3, max_length=200, description="Em português")
    resumo: str = Field(default="", max_length=240, description="Uma linha, em português")
    url: str = Field(description="Link copiado de um resultado da busca")
    tema: Tema
    publicada: str | None = Field(
        default=None, description="Data e hora de publicação, se aparecer (ISO, AAAA-MM-DD…)"
    )


class RegistrarNoticiasArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gerais: list[NoticiaIn] = Field(description="Até 8 notícias dos temas, da mais relevante")
    futebol: list[NoticiaIn] = Field(
        default=[], description="Até 5 de futebol, times do Kaio primeiro"
    )


REGISTRAR = {
    "type": "function",
    "function": {
        "name": "registrar_noticias",
        "description": (
            "Registra as notícias do boletim. Chame UMA vez, no fim, depois das buscas. Título "
            "e resumo em português; link exato de um resultado da busca."
        ),
        "parameters": RegistrarNoticiasArgs.model_json_schema(),
    },
}


# --- deduplicação por título


def title_words(title: str) -> set[str]:
    return {w for w in re.findall(r"\w+", normalize(title)) if w not in TITLE_STOPWORDS}


def similar(a: str, b: str) -> bool:
    wa, wb = title_words(a), title_words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= SIMILAR


# --- a rodada


def edition_of(now: datetime) -> date:
    """Dia do boletim, no fuso de Brasília."""
    return now.astimezone(TZ).date()


@dataclass
class BoletimResult:
    run: AgentRun
    new: list[NewsItem] = field(default_factory=list)
    discarded: dict[str, int] = field(default_factory=dict)


def _prompt(profile: Profile, now: datetime, max_searches: int) -> str:
    temas = "\n".join(f"- {t.chave}: {t.nome} ({t.descricao})" for t in profile.temas)
    times = " e ".join(profile.times) or "os principais times brasileiros"
    agora = f"{now.astimezone(TZ):%Y-%m-%d %H:%M}"
    return f"""Agora é {agora} (Brasília). Monte o boletim de notícias de hoje.

Temas das notícias gerais:
{temas}

Futebol: priorize {times} (resultado, próximo jogo, contratações). Sem notícia deles, use o
principal fato do futebol brasileiro.

Faça até {max_searches} buscas na web (a busca já está limitada às fontes aceitas). Depois chame
registrar_noticias UMA vez, com até 8 gerais (da mais para a menos relevante, cobrindo os
temas) e até 5 de futebol. Regras:
- só o que foi publicado nas últimas 24 horas; preencha "publicada" quando o resultado mostrar;
- um fato por notícia: se várias fontes trazem o mesmo fato, escolha uma só;
- título e resumo SEMPRE em português do Brasil, mesmo que a fonte seja estrangeira (traduza);
- resumo de uma linha, só o fato, sem opinião;
- use só links que apareceram nos resultados da busca, copiados exatamente; nunca monte um link;
- a página de UMA notícia, nunca a capa ou uma lista de notícias;
- se nada servir, chame registrar_noticias com as listas vazias."""


async def run_boletim(
    session: AsyncSession,
    llm: LLM,
    model: str,
    profile: Profile,
    now: datetime,
    max_searches: int = 8,
) -> BoletimResult:
    started = time.monotonic()
    edition = edition_of(now)
    run = AgentRun(channel=CHANNEL, intent=CHANNEL, model=model, tools_called=[])
    session.add(run)
    tools = [
        server_tool(
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": max_searches,
                "allowed_domains": profile.domains(),
                "user_location": {
                    "type": "approximate",
                    "city": "Brasília",
                    "country": "BR",
                    "timezone": "America/Sao_Paulo",
                },
            }
        ),
        REGISTRAR,
    ]
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": _prompt(profile, now, max_searches)}
    ]
    completions: list[Completion] = []
    got: RegistrarNoticiasArgs | None = None
    error: str | None = None
    try:
        for _ in range(MAX_ROUNDS):
            c = await llm.chat(model, messages, tools=tools, max_tokens=4096)
            completions.append(c)
            call = next((t for t in c.tool_calls if t.name == "registrar_noticias"), None)
            if call is not None:
                try:
                    got = RegistrarNoticiasArgs.model_validate_json(call.arguments)
                except ValidationError as e:
                    error = f"registrar_noticias inválido: {e.errors()[:2]}"
                break
            messages.append(c.assistant_message())
            messages.append(
                {"role": "user", "content": "Agora chame registrar_noticias com o que achou."}
            )
        else:
            error = "o modelo não chamou registrar_noticias"
    except Exception as e:  # rede, API: a rodada conta como falha e é tentada de novo
        error = f"{type(e).__name__}: {e}"[:500]
        log.exception("boletim: falha na pesquisa")

    result = BoletimResult(run=run)
    results = search_results(completions)
    recent = (
        await session.scalars(
            select(NewsItem.titulo).where(
                NewsItem.edition >= edition - timedelta(days=HISTORY_DAYS)
            )
        )
    ).all()
    accepted: list[tuple[NoticiaIn, bool, str, str]] = []  # (notícia, futebol, url, fonte)
    sections = (
        [(got.gerais, False, profile.gerais), (got.futebol, True, profile.futebol)] if got else []
    )
    for items, futebol, limit in sections:
        kept = 0
        for n in items:
            if kept >= limit:
                break
            reason = None
            url = normalize_url(n.url)
            fonte = source_name(n.url, profile.fontes)
            published = page_age(n.publicada, now) or page_age(results.get(url), now)
            if url not in results:
                reason = "link_fora_da_busca"
            elif fonte is None:
                reason = "fonte_fora_da_lista"
            elif published is not None and now - published > MAX_AGE:
                reason = "antiga"
            elif any(a[2] == url for a in accepted) or await session.scalar(
                select(NewsItem.id).where(NewsItem.url == url)
            ):
                reason = "repetida"
            elif any(similar(n.titulo, t) for t in [*recent, *(a[0].titulo for a in accepted)]):
                reason = "parecida"
            if reason:
                result.discarded[reason] = result.discarded.get(reason, 0) + 1
                continue
            accepted.append((n, futebol, url, fonte or ""))
            kept += 1

    for pos, (n, futebol, url, fonte) in enumerate(accepted, 1):
        result.new.append(
            NewsItem(
                url=url,
                titulo=n.titulo.strip(),
                resumo=n.resumo.strip(),
                fonte=fonte,
                tema="futebol" if futebol else n.tema,
                futebol=futebol,
                posicao=pos,
                edition=edition,
            )
        )

    searches = sum(c.searches for c in completions)
    run.input_tokens = sum(c.input_tokens for c in completions)
    run.output_tokens = sum(c.output_tokens for c in completions)
    run.cost_usd = sum((c.cost_usd for c in completions), Decimal(0))
    run.latency_ms = int((time.monotonic() - started) * 1000)
    run.error = error
    received = (len(got.gerais) + len(got.futebol)) if got else 0
    run.tools_called = [
        {"name": "web_search", "buscas": searches, "resultados": len(results)},
        {
            "name": "registrar_noticias",
            "recebidas": received,
            "novas": len(result.new),
            "descartadas": result.discarded,
        },
    ]
    await session.flush()
    for item in result.new:
        item.run_id = run.id
        session.add(item)
    await session.flush()
    log.info(
        "boletim: %d busca(s), %d resultado(s), %d notícia(s), descartadas %s, US$ %.3f%s",
        searches,
        len(results),
        len(result.new),
        json.dumps(result.discarded),
        float(run.cost_usd or 0),
        f", erro: {error}" if error else "",
    )
    return result
