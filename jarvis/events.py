"""Protocolo entre o cérebro e a interface (WebSocket local). Também servirá à voz.

Interface -> cérebro:
  {"type": "ask", "id": "<id>", "text": "...", "mode": "texto"|"voz"}
  {"type": "confirm", "id": "<id>", "confirm_id": "<id>", "accepted": true|false}
  {"type": "interrupt"}                      para de falar e cancela o turno em andamento
  {"type": "voice_start", "id": "<id>", "sampleRate": 16000}, quadros binários PCM Int16 mono,
  {"type": "voice_end", "id": "<id>"} | {"type": "voice_cancel", "id": "<id>"}
  {"type": "panel", "id": "<id>"}           dados do painel (sem o modelo)
Cérebro -> interface:
  step    passo em andamento ("consultando a agenda…")
  token   pedaço do texto da resposta (streaming)
  card    cartão tipado para desenhar
  confirm pedido de confirmação (pendência do núcleo, área de transferência)
  done    fim da resposta, com o texto completo (data.wrote: o turno gravou algo no núcleo)
  error   falha, com mensagem para o usuário
  heard   transcrição da fala (vira a pergunta do turno)
  no_speech  a gravação não tinha fala: a interface vira modo texto
  status  texto curto de estado ("transcrevendo…", "baixando o modelo de voz…")
  speaking  data.on: começou/terminou de falar
  panel   data: saída da ferramenta `painel` + "perguntas" da sessão, ou {"erro": "..."}
  terminals       data.terminais: lista dos terminais do Claude Code (a todas as conexões)
  terminal_alert  data: aviso de um terminal (permissão, espera, fim) com o texto pronto; numa
                  sessão aberta pelo Jarvis, com `pedido` (para os botões Permitir/Negar) e `aba`
  terminal_opened data: resultado de `term_open` (status/numero/sessao/tipo, ou erro/opcoes)
  terminal_resolved  data: {pedido, resultado}: o pedido de permissão foi resolvido
  quadros binários: 0x01 + id da sessão do tmux (8) + saída do terminal (aba anexada)
Interface -> cérebro (terminais compartilhados; `sessao` = session_id do tmux, ex.: "$3"):
  {"type": "term_attach", "sessao": "...", "cols": 120, "rows": 32}   cliente da aba visível
  {"type": "term_detach", "sessao": "..."}
  {"type": "term_input", "sessao": "...", "data": "..."}    teclas do Kaio
  {"type": "term_resize", "sessao": "...", "cols": 120, "rows": 32}
  {"type": "term_pause", "sessao": "...", "on": true|false}  controle de fluxo
  {"type": "term_open", "pasta": "...", "claude": true|false}
  {"type": "term_tab_open"|"term_tab_close", "sessao": "..."}  abrir/fechar a aba (×)
  {"type": "permission_answer", "pedido": "...", "decisao": "permitir"|"negar"}  (só clique)
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EventType = Literal[
    "step",
    "token",
    "card",
    "confirm",
    "done",
    "error",
    "heard",
    "no_speech",
    "status",
    "speaking",
    "panel",
    "terminals",
    "terminal_alert",
    "terminal_opened",
    "terminal_resolved",
]


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


def done(rid: str, text: str, wrote: bool = False) -> Event:
    return Event("done", rid, text=text, data={"wrote": True} if wrote else {})


def terminals(items: list[dict[str, Any]]) -> Event:
    return Event("terminals", "terminais", data={"terminais": items})


def terminal_alert(alert: dict[str, Any]) -> Event:
    return Event("terminal_alert", "terminais", data=alert)


def terminal_opened(result: dict[str, Any]) -> Event:
    return Event("terminal_opened", "terminais", data=result)


def terminal_resolved(pedido: str, resultado: str) -> Event:
    return Event("terminal_resolved", "terminais", data={"pedido": pedido, "resultado": resultado})


def panel(rid: str, data: dict[str, Any]) -> Event:
    return Event("panel", rid, data=data)


def error(rid: str, text: str) -> Event:
    return Event("error", rid, text=text)


def heard(rid: str, text: str) -> Event:
    return Event("heard", rid, text=text)


def no_speech(rid: str) -> Event:
    return Event("no_speech", rid)


def status(rid: str, text: str) -> Event:
    return Event("status", rid, text=text)


def speaking(rid: str, on: bool) -> Event:
    return Event("speaking", rid, data={"on": on})
