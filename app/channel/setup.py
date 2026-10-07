"""Cria a instância da Evolution com o webhook e salva o QR code.

Uso (no Mac, com o compose no ar):
    EVOLUTION_API_URL=http://localhost:8080 uv run python -m app.channel.setup
"""

import asyncio
import base64
import sys
from pathlib import Path
from typing import Any

import httpx

from app.channel.evolution import EvolutionClient
from app.config import get_settings

QR_FILE = Path("data/qrcode.png")


async def _fetch_qr() -> dict[str, Any] | None:
    """Devolve o QR para conectar, ou None se a instância já está conectada."""
    settings = get_settings()
    client = EvolutionClient(settings)
    try:
        state = await client.connection_state()
        if state == "open":
            return None
        if state is None:
            await client.create_instance()
            print(f"Instância '{settings.evolution_instance}' criada com webhook interno.")
        return await client.connect()
    finally:
        await client.aclose()


def main() -> int:
    try:
        qr = asyncio.run(_fetch_qr())
    except httpx.HTTPError as exc:
        print(f"Erro falando com a Evolution API: {exc}", file=sys.stderr)
        return 1
    if qr is None:
        print("Instância já está conectada.")
        return 0

    data_url = qr.get("base64") or ""
    if not data_url:
        print("A Evolution não devolveu QR code. Abra http://localhost:8080/manager.")
        return 1
    QR_FILE.parent.mkdir(exist_ok=True)
    QR_FILE.write_bytes(base64.b64decode(data_url.split(",", 1)[-1]))
    print(f"QR code salvo em {QR_FILE}. Escaneie em: WhatsApp Business > Aparelhos conectados")
    print("> Conectar aparelho. O QR expira em ~40 s; rode de novo se expirar.")
    if code := qr.get("pairingCode"):
        print(f"Código de pareamento: {code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
