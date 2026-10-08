"""Configura o Google Calendar no .env e testa o acesso, sem a chave passar pela conversa.

Uso:
    uv run python -m app.integrations.gcal_setup CAMINHO_DA_CHAVE.json SEU_EMAIL@gmail.com
O e-mail é o ID do calendário principal. Depois: docker compose up -d app
"""

import asyncio
import base64
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from app.integrations.gcal import GoogleCalendar

ENV = Path(".env")


def _set_env(key: str, value: str) -> None:
    text = ENV.read_text()
    line = f"{key}={value}"
    if re.search(rf"^{key}=.*$", text, flags=re.M):
        text = re.sub(rf"^{key}=.*$", line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    ENV.write_text(text)


async def _probe(info: dict, calendar_id: str) -> None:
    cal = GoogleCalendar(info, calendar_id)
    day = date.today() + timedelta(days=1)
    gid = await cal.insert(
        {
            "summary": "Teste do assistente (pode apagar)",
            "start": {"date": day.isoformat()},
            "end": {"date": (day + timedelta(days=1)).isoformat()},
            "reminders": {"useDefault": False},
        }
    )
    await cal.delete(gid)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    key_path, calendar_id = Path(sys.argv[1]).expanduser(), sys.argv[2].strip()
    info = json.loads(key_path.read_text())
    sa_email = info.get("client_email", "?")
    try:
        asyncio.run(_probe(info, calendar_id))
    except Exception as exc:  # noqa: BLE001
        print(f"Falhou ao criar um evento de teste: {exc.__class__.__name__}: {exc}")
        print(f"Confira se o calendário {calendar_id} está compartilhado com {sa_email}")
        print('com a permissão "Fazer alterações nos eventos".')
        return 1
    _set_env("GOOGLE_SERVICE_ACCOUNT_JSON", base64.b64encode(key_path.read_bytes()).decode())
    _set_env("GOOGLE_CALENDAR_ID", calendar_id)
    print("Acesso ok: evento de teste criado e apagado.")
    print("Chave e calendário gravados no .env. Agora: docker compose up -d app")
    print(f"Pode apagar o arquivo da chave ({key_path}); ela já está no .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
