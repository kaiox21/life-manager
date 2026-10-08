import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.llm import LLM, make_llm
from app.agent.service import Models
from app.alerts import ConnectionMonitor, LogNotifier, Notifier, NtfyNotifier
from app.channel.evolution import EvolutionClient, parse_connection_update, parse_webhook
from app.clock import Clock, system_clock
from app.config import Settings, get_settings, provider_list
from app.db.base import make_engine, make_sessionmaker
from app.db.repo import register_incoming
from app.handler import BOT_MARK, Deps, Sender, handle_incoming
from app.integrations.gcal import CalendarClient, calendar_from_settings, sync_pending
from app.integrations.transcribe import FasterWhisper, Transcriber
from app.mcp_server import build_mcp, mcp_http_app
from app.scheduler import build_scheduler
from app.security import is_owner, secret_matches

log = logging.getLogger(__name__)


def _log_task_error(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and task.exception():
        log.error("tarefa em segundo plano falhou: %r", task.exception())


def create_app(
    settings: Settings | None = None,
    sessions: async_sessionmaker[AsyncSession] | None = None,
    sender: Sender | None = None,
    llm: LLM | None = None,
    clock: Clock = system_clock,
    calendar: CalendarClient | None = None,
    transcriber: Transcriber | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = None
        client = None
        gateway = None
        if app.state.sessions is None:
            engine = make_engine(settings.database_url)
            app.state.sessions = make_sessionmaker(engine)
        if app.state.sender is None:
            client = EvolutionClient(settings)
            app.state.sender = client
        if app.state.llm is None:
            gateway = make_llm(settings)
            app.state.llm = gateway
        if app.state.transcriber is None and settings.transcribe_backend == "faster-whisper":
            whisper = FasterWhisper(settings.whisper_model, settings.whisper_cache_dir)
            app.state.transcriber = whisper
            # Carrega o modelo em segundo plano para o 1º áudio não esperar.
            warmup = asyncio.create_task(whisper.warmup())
            warmup.add_done_callback(_log_task_error)
        if app.state.calendar is None:
            app.state.calendar = calendar_from_settings(settings)
        if app.state.calendar is not None:
            log.info("Google Calendar configurado; sincronizando pendências")
            try:
                await sync_pending(app.state.sessions, app.state.calendar)
            except Exception:
                log.exception("sync inicial com o Google Calendar falhou")
        scheduler = None
        if settings.scheduler_enabled:
            scheduler = build_scheduler(
                sessions=app.state.sessions,
                sender=app.state.sender,
                owner_phone=settings.owner_phone,
                clock=clock,
                prefix=BOT_MARK if settings.self_chat_mode else "",
                monitor=app.state.monitor,
                connection_state=getattr(app.state.sender, "connection_state", None),
                healthcheck_url=settings.healthcheck_url,
            )
            scheduler.start()
        async with contextlib.AsyncExitStack() as stack:
            if app.state.mcp is not None:
                await stack.enter_async_context(app.state.mcp.session_manager.run())
            yield
        if scheduler:
            scheduler.shutdown(wait=False)
        if client:
            await client.aclose()
        if gateway:
            await gateway.aclose()
        if engine:
            await engine.dispose()

    mcp = None
    if settings.mcp_token.get_secret_value():

        async def after_write() -> None:
            if app.state.calendar is not None:
                await sync_pending(app.state.sessions, app.state.calendar)

        mcp = build_mcp(
            get_sessions=lambda: app.state.sessions, clock=clock, after_write=after_write
        )

    app = FastAPI(title="life-manager", lifespan=lifespan)
    if mcp is not None:
        app.mount("/mcp", mcp_http_app(mcp, provider_list(settings.mcp_allowed_hosts)))
        mcp_token = settings.mcp_token.get_secret_value()

        @app.middleware("http")
        async def mcp_auth(request: Request, call_next):  # type: ignore[no-untyped-def]
            if request.url.path.startswith("/mcp"):
                auth = request.headers.get("authorization", "")
                if not secret_matches(auth.removeprefix("Bearer ").strip(), mcp_token):
                    return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    app.state.mcp = mcp
    app.state.sessions = sessions
    app.state.sender = sender
    app.state.llm = llm
    app.state.calendar = calendar
    app.state.transcriber = transcriber
    notifier: Notifier = (
        NtfyNotifier(settings.alert_ntfy_url, settings.alert_ntfy_token.get_secret_value())
        if settings.alert_ntfy_url
        else LogNotifier()
    )
    app.state.monitor = ConnectionMonitor(notifier)
    models = Models(
        classifier=settings.model_classifier or settings.model_primary,
        primary=settings.model_primary,
        escalation=settings.model_escalation or settings.model_primary,
    )

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

        state = parse_connection_update(payload)
        if state is not None:
            background.add_task(request.app.state.monitor.observe, state, clock())
            return {"status": "ignored", "reason": "connection_update"}

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
        if msg.type not in ("text", "audio", "image"):
            return {"status": "ignored", "reason": "unsupported_type"}

        sessions: async_sessionmaker[AsyncSession] = request.app.state.sessions
        async with sessions.begin() as session:
            message_id = await register_incoming(session, msg)
        if message_id is None:
            return {"status": "ignored", "reason": "duplicate"}

        deps = Deps(
            owner_phone=settings.owner_phone,
            sender=request.app.state.sender,
            sessions=sessions,
            llm=request.app.state.llm,
            models=models,
            self_chat_mode=settings.self_chat_mode,
            clock=clock,
            calendar=request.app.state.calendar,
            transcriber=request.app.state.transcriber,
        )
        background.add_task(handle_incoming, msg, message_id, deps)
        return {"status": "accepted"}

    return app
