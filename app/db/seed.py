"""Seeds idempotentes: categorias fixas e meios de pagamento de um YAML local.

Uso: uv run python -m app.db.seed [data/meios_pagamento.yaml]
Os meios reais ficam em data/ (fora do git); o formato está em seeds/meios_pagamento.exemplo.yaml.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.resolve import normalize
from app.db.models import Category, PaymentMethod

CATEGORIES = [
    "Alimentação",
    "Mercado",
    "Transporte",
    "Casa",
    "Saúde",
    "Lazer",
    "Educação",
    "Assinaturas",
    "Outros",
]
DEFAULT_FILE = Path("data/meios_pagamento.yaml")


async def seed_categories(session: AsyncSession, names: list[str] = CATEGORIES) -> None:
    existing = set((await session.scalars(select(Category.name))).all())
    session.add_all(Category(name=n) for n in names if n not in existing)
    await session.flush()


async def seed_payment_methods(session: AsyncSession, methods: list[dict[str, Any]]) -> None:
    current = {normalize(pm.name): pm for pm in (await session.scalars(select(PaymentMethod)))}
    for m in methods:
        pm = current.get(normalize(m["name"]))
        if pm is None:
            pm = PaymentMethod(name=m["name"])
            session.add(pm)
        pm.kind = m["kind"]
        pm.closing_day = m.get("closing_day")
        pm.due_day = m.get("due_day")
        pm.aliases = list(m.get("aliases") or [])
        pm.active = True
    await session.flush()


def load_methods(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text()) or {}
    return list(data.get("meios_pagamento") or [])


async def _main(methods: list[dict[str, Any]]) -> None:
    from app.config import get_settings
    from app.db.base import make_engine, make_sessionmaker

    engine = make_engine(get_settings().database_url)
    async with make_sessionmaker(engine).begin() as session:
        await seed_categories(session)
        await seed_payment_methods(session, methods)
    await engine.dispose()


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FILE
    methods = load_methods(path) if path.exists() else []
    asyncio.run(_main(methods))
    print(f"{len(CATEGORIES)} categorias; {len(methods)} meios de pagamento de {path}")
