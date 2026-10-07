import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.types import OutgoingMessage

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
    def __init__(self) -> None:
        self.sent: list[OutgoingMessage] = []

    async def send_text(self, out: OutgoingMessage) -> str | None:
        self.sent.append(out)
        return f"BOT{len(self.sent):04d}"


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
        await conn.execute(text("truncate messages"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
