"""Protocolo entre o cérebro e a interface (WebSocket local). Também servirá à voz.

Interface -> cérebro:
  {"type": "ask", "id": "<id>", "text": "..."}
  {"type": "confirm", "id": "<id>", "confirm_id": "<id>", "accepted": true|false}
Cérebro -> interface:
  step    passo em andamento ("consultando a agenda…")
  token   pedaço do texto da resposta (streaming)
  card    cartão tipado para desenhar
  confirm pedido de confirmação (pendência do núcleo, área de transferência)
  done    fim da resposta, com o texto completo
  error   falha, com mensagem para o usuário
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EventType = Literal["step", "token", "card", "confirm", "done", "error"]


@dataclass(frozen=True)
class Event:
    type: EventType
    id: str
    text: str = ""
    card: dict[str, Any] | None = None
    confirm_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        payload = {k: v for k, v in asdict(self).items() if v not in (None, "", {})}
        payload["type"], payload["id"] = self.type, self.id
        return json.dumps(payload, ensure_ascii=False, default=str)


def step(rid: str, text: str) -> Event:
    return Event("step", rid, text=text)


def token(rid: str, text: str) -> Event:
    return Event("token", rid, text=text)


def card(rid: str, card: dict[str, Any]) -> Event:
    return Event("card", rid, card=card)


def confirm(rid: str, confirm_id: str, text: str, data: dict[str, Any] | None = None) -> Event:
    return Event("confirm", rid, text=text, confirm_id=confirm_id, data=data or {})


def done(rid: str, text: str) -> Event:
    return Event("done", rid, text=text)


def error(rid: str, text: str) -> Event:
    return Event("error", rid, text=text)
