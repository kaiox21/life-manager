"""Casa o que o usuário disse ("nubank", "débito do inter") com registros do banco."""

import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.base import ToolError
from app.db.models import Category, PaymentMethod

STOPWORDS = {"no", "na", "do", "da", "de", "o", "a", "meu", "minha", "cartao", "com", "em", "pelo"}
KIND_WORDS = {"credito": "credito", "debito": "debito", "pix": "pix", "dinheiro": "dinheiro"}


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


def _tokens(text: str) -> set[str]:
    return {t for t in normalize(text).replace("-", " ").split() if t not in STOPWORDS}


def _method_tokens(pm: PaymentMethod) -> set[str]:
    tokens = _tokens(pm.name) | {KIND_WORDS[pm.kind]}
    for alias in pm.aliases or []:
        tokens |= _tokens(alias)
    return tokens


def match_payment_methods(methods: list[PaymentMethod], text: str) -> list[PaymentMethod]:
    wanted = normalize(text)
    exact = [
        pm
        for pm in methods
        if wanted == normalize(pm.name) or wanted in {normalize(a) for a in pm.aliases or []}
    ]
    # Nome exato só decide se não houver outro meio do mesmo banco (ex.: "Itaú" x "Itaú Débito").
    query = _tokens(text)
    partial = [pm for pm in methods if query and query <= _method_tokens(pm)]
    if len(exact) == 1 and len(partial) <= 1:
        return exact
    return partial or exact


async def resolve_payment_method(
    session: AsyncSession, text: str, kinds: set[str] | None = None
) -> PaymentMethod:
    stmt = select(PaymentMethod).where(PaymentMethod.active.is_(True))
    methods = list((await session.scalars(stmt)).all())
    if kinds:
        methods = [pm for pm in methods if pm.kind in kinds]
    found = match_payment_methods(methods, text)
    if len(found) == 1:
        return found[0]
    if not found:
        raise ToolError(
            f"Meio de pagamento '{text}' não cadastrado.",
            opcoes=sorted(pm.name for pm in methods),
        )
    raise ToolError(f"'{text}' é ambíguo; pergunte qual.", opcoes=sorted(pm.name for pm in found))


async def resolve_category(session: AsyncSession, text: str) -> Category:
    categories = list((await session.scalars(select(Category))).all())
    wanted = normalize(text)
    for cat in categories:
        if normalize(cat.name) == wanted:
            return cat
    raise ToolError(f"Categoria '{text}' não existe.", opcoes=sorted(c.name for c in categories))
