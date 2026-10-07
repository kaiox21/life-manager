import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.channel.evolution import EvolutionClient, parse_webhook
from app.config import Settings, get_settings
from app.db.base import make_engine, make_sessionmaker
from app.db.repo import register_incoming
from app.handler import BOT_MARK, Sender, handle_incoming
from app.security import is_owner, secret_matches

log = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    sessions: async_sessionmaker[AsyncSession] | None = None,
    sender: Sender | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = None
        client = None
        if app.state.sessions is None:
            engine = make_engine(settings.database_url)
            app.state.sessions = make_sessionmaker(engine)
        if app.state.sender is None:
            client = EvolutionClient(settings)
            app.state.sender = client
        yield
        if client:
            await client.aclose()
        if engine:
            await engine.dispose()

    app = FastAPI(title="life-manager", lifespan=lifespan)
    app.state.sessions = sessions
    app.state.sender = sender

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhook/evolution")
    async def webhook(
        request: Request,
        background: BackgroundTasks,
        x_webhook_secret: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if not secret_matches(x_webhook_secret, settings.webhook_secret.get_secret_value()):
            raise HTTPException(status_code=401)

        try:
            payload = await request.json()
        except ValueError:
            return {"status": "ignored", "reason": "invalid_json"}
        if not isinstance(payload, dict):
            return {"status": "ignored", "reason": "invalid_json"}

        msg = parse_webhook(payload)
        if msg is None:
            return {"status": "ignored", "reason": "not_a_message"}
        if msg.is_group or msg.is_broadcast:
            return {"status": "ignored", "reason": "group_or_broadcast"}
        if msg.from_me:
            # Fora do modo provisório, fromMe são só as respostas do próprio bot.
            if not settings.self_chat_mode:
                return {"status": "ignored", "reason": "from_me"}
            # No modo provisório, sender é o outro lado da conversa: só a conversa consigo mesmo.
            if not is_owner(msg.sender, settings.owner_phone):
                return {"status": "ignored", "reason": "from_me_other_chat"}
            if (msg.text or "").startswith(BOT_MARK):
                return {"status": "ignored", "reason": "bot_reply"}
        elif settings.self_chat_mode:
            # O dono fala consigo mesmo; mensagem recebida de outra pessoa nunca é atendida.
            return {"status": "ignored", "reason": "not_owner"}
        if not is_owner(msg.sender, settings.owner_phone):
            log.info("remetente fora da allowlist ignorado (%s)", msg.wa_message_id)
            return {"status": "ignored", "reason": "not_owner"}
        if msg.type != "text":
            return {"status": "ignored", "reason": "unsupported_type"}

        sessions: async_sessionmaker[AsyncSession] = request.app.state.sessions
        async with sessions.begin() as session:
            message_id = await register_incoming(session, msg)
        if message_id is None:
            return {"status": "ignored", "reason": "duplicate"}

        background.add_task(
            handle_incoming,
            msg,
            owner_phone=settings.owner_phone,
            sender=request.app.state.sender,
            sessions=sessions,
            self_chat_mode=settings.self_chat_mode,
        )
        return {"status": "accepted"}

    return app
