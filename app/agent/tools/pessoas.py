"""Pessoas citadas ("minha irmã", "meu chefe") e a ferramenta gerenciar_pessoa."""

from typing import Any

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.base import Tool, ToolArgs, ToolContext, ToolError
from app.agent.tools.resolve import normalize
from app.db.models import Person

_POSSESSIVES = ("minha ", "meu ", "da minha ", "do meu ", "a minha ", "o meu ", "da ", "do ")


def _strip_possessive(text: str) -> str:
    t = normalize(text)
    for prefix in sorted(_POSSESSIVES, key=len, reverse=True):
        if t.startswith(prefix):
            return t[len(prefix) :].strip()
    return t


def match_people(people: list[Person], text: str) -> list[Person]:
    wanted = _strip_possessive(text)
    by_name = [
        p
        for p in people
        if wanted == normalize(p.name) or wanted in {normalize(a) for a in p.aliases or []}
    ]
    if by_name:
        return by_name
    return [p for p in people if p.relation and wanted == normalize(p.relation)]


async def resolve_person(session: AsyncSession, text: str) -> Person:
    people = list((await session.scalars(select(Person))).all())
    found = match_people(people, text)
    if len(found) == 1:
        return found[0]
    if not found:
        raise ToolError(
            f"Pessoa '{text}' não cadastrada. Pergunte o nome e cadastre com gerenciar_pessoa.",
            cadastradas=[_label(p) for p in people],
        )
    raise ToolError(f"'{text}' é ambíguo; pergunte qual.", opcoes=[_label(p) for p in found])


def _label(p: Person) -> str:
    return f"{p.name} ({p.relation})" if p.relation else p.name


class GerenciarPessoaArgs(ToolArgs):
    name: str = Field(min_length=1, description="Nome da pessoa. Ex.: 'Ana'")
    relation: str | None = Field(default=None, description="Relação. Ex.: 'mãe', 'chefe'")
    aliases: list[str] | None = Field(default=None, description="Apelidos")


async def gerenciar_pessoa(ctx: ToolContext, args: GerenciarPessoaArgs) -> dict[str, Any]:
    people = list((await ctx.session.scalars(select(Person))).all())
    existing = next((p for p in people if normalize(p.name) == normalize(args.name)), None)
    if existing is None:
        existing = Person(
            name=args.name.strip(), relation=args.relation, aliases=args.aliases or []
        )
        ctx.session.add(existing)
        status = "criada"
    else:
        if args.relation:
            existing.relation = args.relation
        if args.aliases:
            existing.aliases = sorted(set(existing.aliases or []) | set(args.aliases))
        status = "atualizada" if (args.relation or args.aliases) else "encontrada"
    await ctx.session.flush()
    return {"status": status, "pessoa": _label(existing)}


TOOLS = [
    Tool(
        "gerenciar_pessoa",
        ("pessoa", "agenda"),
        "Cadastra ou atualiza uma pessoa. Ex.: 'minha mãe se chama Ana' -> name='Ana', "
        "relation='mãe'. Use antes de criar evento de alguém ainda não cadastrado.",
        GerenciarPessoaArgs,
        gerenciar_pessoa,
    ),
]
