"""Alertas fora do WhatsApp (quando o WhatsApp cai, o bot não consegue avisar por ele).

- Notifier: ntfy (POST num tópico secreto) ou só log, se não configurado.
- ConnectionMonitor: avisa quando a instância fica fora do ar por um tempo e quando volta.
  Reconexões rápidas do Baileys (close -> open em segundos) não geram alerta.
- heartbeat: ping periódico a um "dead man's switch" (ex.: healthchecks.io); se o servidor
  inteiro cair, o serviço externo avisa por e-mail.
"""

import logging
from datetime import datetime, timedelta
from typing import Protocol

import httpx

log = logging.getLogger(__name__)

DOWN_GRACE = timedelta(minutes=2)


class Notifier(Protocol):
    async def notify(self, title: str, message: str, urgent: bool = False) -> None: ...


class LogNotifier:
    async def notify(self, title: str, message: str, urgent: bool = False) -> None:
        log.warning("ALERTA (sem canal configurado): %s — %s", title, message)


class NtfyNotifier:
    def __init__(self, topic_url: str, token: str = "", http: httpx.AsyncClient | None = None):
        self._url = topic_url
        self._token = token
        self._http = http or httpx.AsyncClient(timeout=15)

    async def notify(self, title: str, message: str, urgent: bool = False) -> None:
        # Publicação em JSON na raiz do servidor (aceita acentos no título).
        server, _, topic = self._url.rstrip("/").rpartition("/")
        body = {
            "topic": topic,
            "title": title,
            "message": message,
            "tags": ["warning"],
            "priority": 4 if urgent else 3,
        }
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        resp = await self._http.post(server, json=body, headers=headers)
        resp.raise_for_status()


class ConnectionMonitor:
    """Recebe observações do estado da instância (webhook e verificação periódica)."""

    def __init__(self, notifier: Notifier, grace: timedelta = DOWN_GRACE) -> None:
        self._notifier = notifier
        self._grace = grace
        self._down_since: datetime | None = None
        self._alerted = False

    async def observe(self, state: str | None, now: datetime) -> None:
        """state=None significa que nem a Evolution respondeu."""
        if state == "open":
            if self._alerted:
                await self._send("WhatsApp voltou", "A instância está conectada de novo.")
            self._down_since = None
            self._alerted = False
            return
        if self._down_since is None:
            self._down_since = now
        if not self._alerted and now - self._down_since >= self._grace:
            what = "A Evolution API não responde" if state is None else f"Estado: {state}"
            await self._send(
                "WhatsApp fora do ar",
                f"{what} desde {self._down_since:%H:%M}. Pode ser preciso escanear o QR de novo.",
                urgent=True,
            )
            self._alerted = True

    async def _send(self, title: str, message: str, urgent: bool = False) -> None:
        try:
            await self._notifier.notify(title, message, urgent)
        except Exception:
            log.exception("não consegui enviar o alerta: %s", title)


async def heartbeat(url: str, http: httpx.AsyncClient | None = None) -> None:
    if not url:
        return
    client = http or httpx.AsyncClient(timeout=10)
    try:
        (await client.get(url)).raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("heartbeat falhou: %s", exc.__class__.__name__)
    finally:
        if http is None:
            await client.aclose()
