"""Único módulo que conhece a Evolution API (v2, integração Baileys)."""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import Settings
from app.security import is_owner, normalize_phone
from app.types import IncomingMessage, Media, MessageType, OutgoingMessage

log = logging.getLogger(__name__)

UPSERT_EVENT = "messages.upsert"
CONNECTION_EVENT = "connection.update"


class ForbiddenDestinationError(Exception):
    """Tentativa de enviar mensagem para alguém que não é o dono."""


def _jid_user(jid: str) -> str:
    return normalize_phone(jid.split("@", 1)[0].split(":", 1)[0])


def _extract_text(message: dict[str, Any]) -> tuple[MessageType, str | None]:
    if text := message.get("conversation"):
        return "text", text
    if text := (message.get("extendedTextMessage") or {}).get("text"):
        return "text", text
    if "audioMessage" in message:
        return "audio", None
    if "imageMessage" in message:
        return "image", (message["imageMessage"] or {}).get("caption")
    return "other", None


def _extract_media(key: dict[str, Any], message: dict[str, Any]) -> Media | None:
    for field_name, default_mime in (("audioMessage", "audio/ogg"), ("imageMessage", "image/jpeg")):
        if field_name not in message:
            continue
        info = message[field_name] or {}
        try:
            seconds = int(info.get("seconds"))
        except (TypeError, ValueError):
            seconds = None
        return Media(
            mimetype=(info.get("mimetype") or default_mime).split(";")[0].strip(),
            data_b64=message.get("base64") or None,
            seconds=seconds,
            ref={"key": key, "message": {k: v for k, v in message.items() if k != "base64"}},
        )
    return None


def _parse_timestamp(raw: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(raw), tz=UTC)
    except (TypeError, ValueError):
        return None


def parse_connection_update(payload: dict[str, Any]) -> str | None:
    """Estado da instância num evento CONNECTION_UPDATE ('open', 'connecting', 'close')."""
    if str(payload.get("event", "")).lower().replace("_", ".") != CONNECTION_EVENT:
        return None
    data = payload.get("data")
    state = data.get("state") if isinstance(data, dict) else None
    return str(state) if state else None


def parse_webhook(payload: dict[str, Any]) -> IncomingMessage | None:
    """Converte um evento MESSAGES_UPSERT em IncomingMessage. Outros eventos devolvem None."""
    if str(payload.get("event", "")).lower().replace("_", ".") != UPSERT_EVENT:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    key = data.get("key") or {}
    wa_id = key.get("id")
    chat_jid = key.get("remoteJid") or ""
    if not wa_id or not chat_jid:
        return None

    # Com endereçamento LID o número real vem em remoteJidAlt.
    if chat_jid.endswith("@lid") and key.get("remoteJidAlt"):
        chat_jid = key["remoteJidAlt"]

    is_group = chat_jid.endswith("@g.us")
    is_broadcast = chat_jid.endswith(("@broadcast", "@newsletter")) or chat_jid.startswith(
        "status@"
    )
    sender_jid = (key.get("participant") or chat_jid) if is_group else chat_jid
    message = data.get("message") or {}
    msg_type, text = _extract_text(message)

    return IncomingMessage(
        wa_message_id=wa_id,
        sender=_jid_user(sender_jid),
        chat_jid=chat_jid,
        from_me=bool(key.get("fromMe")),
        is_group=is_group,
        is_broadcast=is_broadcast,
        type=msg_type,
        text=text,
        sent_at=_parse_timestamp(data.get("messageTimestamp")),
        media=_extract_media(key, message) if msg_type in ("audio", "image") else None,
    )


class EvolutionClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http = http or httpx.AsyncClient(timeout=30)

    def _headers(self) -> dict[str, str]:
        return {"apikey": self._settings.evolution_api_key.get_secret_value()}

    def _url(self, path: str) -> str:
        return f"{self._settings.evolution_api_url.rstrip('/')}{path}"

    async def send_text(self, out: OutgoingMessage) -> str | None:
        """Envia texto ao dono. Devolve o id da mensagem no WhatsApp."""
        if not is_owner(out.to, self._settings.owner_phone):
            raise ForbiddenDestinationError("envio permitido só para OWNER_PHONE")
        resp = await self._http.post(
            self._url(f"/message/sendText/{self._settings.evolution_instance}"),
            headers=self._headers(),
            json={"number": normalize_phone(self._settings.owner_phone), "text": out.text},
        )
        resp.raise_for_status()
        return (resp.json().get("key") or {}).get("id")

    async def fetch_media(self, media: Media) -> str | None:
        """Baixa de novo o arquivo de uma mensagem (quando o webhook veio sem base64)."""
        if not media.ref:
            return None
        resp = await self._http.post(
            self._url(f"/chat/getBase64FromMediaMessage/{self._settings.evolution_instance}"),
            headers=self._headers(),
            json={"message": media.ref, "convertToMp4": False},
        )
        resp.raise_for_status()
        return resp.json().get("base64") or None

    async def create_instance(self) -> dict[str, Any]:
        s = self._settings
        resp = await self._http.post(
            self._url("/instance/create"),
            headers=self._headers(),
            json={
                "instanceName": s.evolution_instance,
                "integration": "WHATSAPP-BAILEYS",
                "qrcode": True,
                "groupsIgnore": True,
                "alwaysOnline": False,
                "readMessages": False,
                "webhook": {
                    "enabled": True,
                    "url": s.app_webhook_url,
                    "headers": {"X-Webhook-Secret": s.webhook_secret.get_secret_value()},
                    "byEvents": False,
                    "base64": True,
                    "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE"],
                },
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def connect(self) -> dict[str, Any]:
        resp = await self._http.get(
            self._url(f"/instance/connect/{self._settings.evolution_instance}"),
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def connection_state(self) -> str | None:
        resp = await self._http.get(
            self._url(f"/instance/connectionState/{self._settings.evolution_instance}"),
            headers=self._headers(),
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return (resp.json().get("instance") or {}).get("state")

    async def aclose(self) -> None:
        await self._http.aclose()
