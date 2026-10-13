"""Modo estudo: Foco do macOS, playlist de estudo e avisos retidos, em blocos com pausa proposta.

Nada aqui chama o modelo. O fim do bloco e da pausa é uma hora marcada (não uma contagem):
o relógio é o laço de 1 s do proativo, então dormir e reiniciar não perdem o modo. O Foco só
liga e desliga por atalhos do app Atalhos cujo nome está configurado E aparece em
`shortcuts list`: `shortcuts run` com um nome inexistente ficou preso sem erro (13/10/2026).
O Jarvis nunca cria nem altera atalhos.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any, Protocol

from jarvis.spotify import SpotifyError

log = logging.getLogger(__name__)

SHORTCUT_TIMEOUT = 10.0
GRACE = timedelta(minutes=10)  # acordou até 10 min depois do fim: ainda pergunta; depois, encerra
ANSWER_TIMEOUT = timedelta(minutes=2)
MAX_MINUTES, MAX_PAUSE = 240, 60
STUDY_USER = "[modo estudo]"  # turno sintético no histórico (a API pede papéis alternados)
END_REPLY = "Perfeito, senhor. Modo estudo encerrado."
NO_FOCUS = "os atalhos do Foco não existem"


class Runner(Protocol):
    async def __call__(self, argv: list[str], stdin: bytes | None) -> Any: ...


class Spotify(Protocol):
    async def search(self, tipo: str, query: str) -> dict[str, Any] | None: ...
    async def play(self, found: dict[str, Any]) -> None: ...


class Brain(Protocol):
    def clock(self) -> datetime: ...
    async def announce(self, rid: str, emit: Any, said: str, text: str) -> None: ...
    async def study_prompt(
        self,
        rid: str,
        emit: Any,
        text: str,
        *,
        yes_reply: str,
        on_yes: Callable[[], Awaitable[None]],
        no_reply: str,
        on_no: Callable[[], Awaitable[None]],
    ) -> None: ...


class Proactive(Protocol):
    def hold(self, reason: str, on: bool) -> None: ...
    def state(self) -> dict[str, Any]: ...
    def save(self, **changes: Any) -> None: ...
    def speak_ok(self) -> bool: ...
    def expect_answer(self, rid: str) -> None: ...

    on_change: Callable[[], None]


def _hhmm(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%H:%M")


class StudyMode:
    def __init__(
        self,
        *,
        brain: Brain,
        proactive: Proactive,
        broadcast_ui: Callable[[Any], Awaitable[None]],
        run: Runner,
        spotify: Spotify | None,
        focus_on: str = "Jarvis Foco",
        focus_off: str = "Jarvis Foco Fim",
        playlist: str = "estudo",
        minutes: int = 50,
        pause: int = 10,
    ) -> None:
        self._brain = brain
        self._proactive = proactive
        self._broadcast_ui = broadcast_ui
        self._run = run
        self._spotify = spotify
        self._focus_on, self._focus_off = focus_on.strip(), focus_off.strip()
        self._playlist = playlist
        self._minutes = max(1, min(MAX_MINUTES, minutes))
        self._pause = max(0, min(MAX_PAUSE, pause))
        self._resumed = False
        self._lock = asyncio.Lock()

    # --- estado (em proativo.json, chave "estudo")

    def _state(self) -> dict[str, Any] | None:
        st = self._proactive.state().get("estudo")
        return st if isinstance(st, dict) and st.get("fase") and st.get("ate") else None

    def _save(self, st: dict[str, Any] | None) -> None:
        self._proactive.save(estudo=st)
        self._proactive.on_change()

    def status(self) -> dict[str, Any] | None:
        """Para o painel e a ferramenta: fase, hora do fim (ISO), minutos e pausa; None parado."""
        st = self._state()
        if st is None:
            return None
        return {k: st[k] for k in ("fase", "ate", "minutos", "pausa")}

    def status_text(self) -> str:
        st = self._state()
        if st is None:
            return "Não há modo estudo ativo."
        left = max(0, round((datetime.fromisoformat(st["ate"]) - self._now()).total_seconds() / 60))
        if st["fase"] == "pausa":
            return f"Na pausa, faltam {left} min."
        if st["fase"] == "pergunta":
            return "O bloco acabou; esperando a resposta sobre a pausa."
        return f"No bloco de estudo, faltam {left} min (até as {_hhmm(st['ate'])})."

    def _now(self) -> datetime:
        return self._brain.clock()

    # --- iniciar, parar

    async def start(self, minutes: int | None = None, pause: int | None = None) -> dict[str, Any]:
        """Liga Foco, playlist e silêncio, nesta ordem, com o que der. Substitui um modo em
        andamento sem perguntar (o Kaio acabou de pedir)."""
        async with self._lock:
            minutes = self._minutes if minutes is None else max(1, min(MAX_MINUTES, minutes))
            pause = self._pause if pause is None else max(0, min(MAX_PAUSE, pause))
            previous = self._state()
            focus_was_on = bool(previous and previous.get("foco_ligado"))
            reason = None if focus_was_on else await self._shortcut(self._focus_on)
            music = await self._play()
            ate = self._now() + timedelta(minutes=minutes)
            self._proactive.hold("estudo", True)
            self._save(
                {
                    "fase": "bloco",
                    "ate": ate.isoformat(),
                    "minutos": minutes,
                    "pausa": pause,
                    "foco_ligado": reason is None,
                }
            )
            log.info(
                "estudo: bloco de %d min até %s (foco: %s)",
                minutes,
                f"{ate:%H:%M}",
                reason or "ligado",
            )
            return {
                "status": "iniciado",
                "fase": "bloco",
                "ate": f"{ate:%H:%M}",
                "minutos": minutes,
                "pausa": pause,
                "foco": "ligado" if reason is None else reason,
                "musica": music,
                "avisos": "em silêncio até o fim do modo",
            }

    def start_text(self, result: dict[str, Any]) -> str:
        """Resposta fixa do botão Estudo (sem o modelo)."""
        parts = [f"Modo estudo até as {result['ate'].replace(':', 'h')}, senhor."]
        parts.append(
            "Foco ligado." if result["foco"] == "ligado" else f"Sem o Foco: {result['foco']}."
        )
        m = result["musica"]
        parts.append(
            "Playlist de estudo tocando." if m.startswith("tocando") else f"Sem música: {m}."
        )
        parts.append("Avisos em silêncio.")
        return " ".join(parts)

    async def stop(self, *, silent: bool = False) -> dict[str, Any]:
        async with self._lock:
            st = self._state()
            if st is None:
                return {"status": "sem_modo", "erro": "Não há modo estudo ativo."}
            self._save(None)
            self._proactive.hold("estudo", False)
            focus = None
            if st.get("foco_ligado"):
                focus = await self._shortcut(self._focus_off)
            log.info("estudo: encerrado%s", " (em silêncio)" if silent else "")
            out: dict[str, Any] = {
                "status": "encerrado",
                "foco": "desligado" if focus is None else focus,
            }
            return out

    async def start_by_button(self) -> None:
        rid = "estudo-" + secrets.token_hex(4)
        result = await self.start()
        await self._brain.announce(rid, self._broadcast_ui, "Estudo", self.start_text(result))

    async def stop_by_button(self) -> None:
        rid = "estudo-" + secrets.token_hex(4)
        result = await self.stop()
        if result["status"] == "encerrado":
            await self._brain.announce(rid, self._broadcast_ui, "Parar o estudo", END_REPLY)

    # --- relógio (chamado a cada segundo pelo proativo)

    async def tick(self) -> None:
        st = self._state()
        if st is None:
            self._resumed = True
            return
        now = self._now()
        ate = datetime.fromisoformat(st["ate"])
        if not self._resumed:
            self._resumed = True
            # subida com um modo gravado: retoma o bloco ou a pausa; uma pergunta pendente ou
            # um fim já passado encerram (Foco desligado)
            if st["fase"] == "pergunta" or now - ate > GRACE:
                await self.stop(silent=True)
                return
            self._proactive.hold("estudo", True)
            log.info("estudo: retomado (%s até %s)", st["fase"], f"{ate:%H:%M}")
        if st["fase"] == "pergunta":
            if now - ate > ANSWER_TIMEOUT:
                await self.stop(silent=True)  # sem resposta: o estado seguro é Foco desligado
            return
        if now < ate:
            return
        if now - ate > GRACE:
            await self.stop(silent=True)  # o Mac dormiu além do fim
            return
        if not self._proactive.speak_ok():
            return  # falando ou atendendo um pedido: tenta no próximo segundo
        await self._ask(st)

    async def _ask(self, st: dict[str, Any]) -> None:
        n, m = int(st["minutos"]), int(st["pausa"])
        if st["fase"] == "bloco" and m > 0:
            text = f"Senhor, acabaram os {n} minutos de estudo. Pausa de {m} minutos?"
            yes_reply, on_yes = f"Pausa de {m} minutos, senhor.", self._start_pause
        elif st["fase"] == "bloco":
            text = f"Senhor, acabaram os {n} minutos de estudo. Mais {n} minutos?"
            yes_reply, on_yes = f"Mais {n} minutos, senhor.", self._next_block
        else:
            text = f"Senhor, a pausa acabou. Mais {n} minutos?"
            yes_reply, on_yes = f"Mais {n} minutos, senhor.", self._next_block
        # a hora da pergunta vai em `ate`: sem resposta em 2 min, o tick encerra
        self._save(st | {"fase": "pergunta", "ate": self._now().isoformat()})
        rid = "estudo-" + secrets.token_hex(4)
        await self._brain.study_prompt(
            rid,
            self._broadcast_ui,
            text,
            yes_reply=yes_reply,
            on_yes=on_yes,
            no_reply=END_REPLY,
            on_no=self._end_by_answer,
        )
        self._proactive.expect_answer(rid)

    async def _start_pause(self) -> None:
        st = self._state()
        if st is None:
            return
        ate = self._now() + timedelta(minutes=int(st["pausa"]))
        self._save(st | {"fase": "pausa", "ate": ate.isoformat()})
        log.info("estudo: pausa até %s", f"{ate:%H:%M}")

    async def _next_block(self) -> None:
        st = self._state()
        if st is None:
            return
        ate = self._now() + timedelta(minutes=int(st["minutos"]))
        self._save(st | {"fase": "bloco", "ate": ate.isoformat()})
        log.info("estudo: novo bloco até %s", f"{ate:%H:%M}")

    async def _end_by_answer(self) -> None:
        await self.stop()

    # --- Foco (atalhos) e música

    async def _shortcut(self, name: str) -> str | None:
        """Roda o atalho; devolve o motivo quando não deu (None = rodou)."""
        if not name:
            return NO_FOCUS
        try:
            listed = await asyncio.wait_for(
                self._run(["shortcuts", "list"], None), SHORTCUT_TIMEOUT
            )
        except (TimeoutError, OSError):
            return "o app Atalhos não respondeu"
        if name not in {line.strip() for line in listed.stdout.splitlines()}:
            return NO_FOCUS
        try:
            r = await asyncio.wait_for(
                self._run(["shortcuts", "run", name], None), SHORTCUT_TIMEOUT
            )
        except (TimeoutError, OSError):
            return "o atalho do Foco não terminou"
        if r.returncode != 0:
            return "o atalho do Foco falhou"
        return None

    async def _play(self) -> str:
        if self._spotify is None:
            return "o Spotify não está configurado"
        try:
            found = await self._spotify.search("minha_playlist", self._playlist)
            if found is None:
                return f"não encontrei a playlist {self._playlist!r}"
            await self._spotify.play(found)
        except SpotifyError as e:
            return "o Spotify não está autorizado" if e.login else str(e)
        except Exception:  # noqa: BLE001 (sem rede, Spotify fechado: o modo segue sem música)
            log.exception("estudo: música falhou")
            return "o Spotify não respondeu"
        return f"tocando {found.get('nome', self._playlist)}"
