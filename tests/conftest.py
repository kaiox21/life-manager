import json
import os
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.agent.tools.base import ToolContext
from app.clock import TZ, fixed_clock
from app.config import Settings
from app.db import models  # noqa: F401  (registra as tabelas)
from app.db.base import Base
from app.db.models import Person
from app.db.seed import seed_categories, seed_payment_methods
from app.types import Media, OutgoingMessage

FIXTURES = Path(__file__).parent / "fixtures"
OWNER = "5561999998888"
SECRET = "segredo-de-teste"
DEFAULT_TEST_DB = "postgresql+psycopg://test:test@localhost:5433/assistente_test"


def load_payload(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / "evolution" / name).read_text())


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        owner_phone=OWNER,
        webhook_secret=SecretStr(SECRET),
        evolution_api_url="http://evolution.test:8080",
        evolution_api_key=SecretStr("chave-de-teste"),
        evolution_instance="assistente",
        database_url="postgresql+psycopg://nao-usar/nao_usar",
    )


class FakeSender:
    def __init__(self, media_b64: str | None = None) -> None:
        self.sent: list[OutgoingMessage] = []
        self.media_b64 = media_b64
        self.fetched: list[Media] = []

    async def send_text(self, out: OutgoingMessage) -> str | None:
        self.sent.append(out)
        return f"BOT{len(self.sent):04d}"

    async def fetch_media(self, media: Media) -> str | None:
        self.fetched.append(media)
        return self.media_b64


@pytest.fixture
def sender() -> FakeSender:
    return FakeSender()


def _test_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB)
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        pytest.exit(f"TEST_DATABASE_URL precisa apontar para um banco *_test (veio '{name}')")
    return url


@pytest.fixture(scope="session")
def migrated_db() -> str:
    from alembic import command
    from alembic.config import Config

    url = _test_db_url()
    cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    cfg.attributes["url"] = url
    try:
        command.upgrade(cfg, "head")
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            "Postgres de teste indisponível. Suba com: "
            f"docker compose --profile test up -d postgres-test ({exc.__class__.__name__})"
        )
    return url


@pytest.fixture
async def sessions(migrated_db: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db, poolclass=NullPool)
    async with engine.begin() as conn:
        tables = ", ".join(Base.metadata.tables)
        await conn.execute(text(f"truncate {tables} cascade"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


TEST_METHODS = [
    {"name": "Nubank", "kind": "credito", "closing_day": 31, "due_day": 8},
    {"name": "Itaú Crédito", "kind": "credito", "closing_day": 25, "due_day": 5},
    {"name": "Itaú Débito", "kind": "debito"},
    {"name": "Pix", "kind": "pix"},
]
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=TZ)


@pytest.fixture
async def seeded(sessions: async_sessionmaker[AsyncSession]) -> async_sessionmaker[AsyncSession]:
    async with sessions.begin() as s:
        await seed_categories(s)
        await seed_payment_methods(s, TEST_METHODS)
        s.add_all(
            [Person(name="Mariana", relation="irmã"), Person(name="Carlos", relation="chefe")]
        )
    return sessions


@pytest.fixture
async def ctx(seeded: async_sessionmaker[AsyncSession]) -> AsyncIterator[ToolContext]:
    async with seeded.begin() as s:
        yield ToolContext(session=s, clock=fixed_clock(NOW))
