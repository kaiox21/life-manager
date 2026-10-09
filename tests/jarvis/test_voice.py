"""Modo voz do agente e protocolo de voz do servidor, sem áudio real."""

import asyncio
import json

import numpy as np
from websockets.asyncio.client import connect

from jarvis import events
from jarvis.agent import FILLERS, JarvisBrain
from jarvis.audio import Speech
from jarvis.local_tools import LocalTools
from jarvis.mcp_client import ToolResult
from jarvis.server import JarvisServer
from tests.fakes import StreamingScriptedLLM, call, reply
from tests.jarvis.test_agent import FakeCore, Runner


class FakeSpeaker:
    def __init__(self):
        self.said: list[str] = []
        self.stopped = 0

    def say(self, text):
        self.said.append(text)

    def stop(self):
        self.stopped += 1

    @property
    def speaking(self):
        return False


class FakeVad:
    def __init__(self, speech: bool):
        self.speech = speech

    def trim(self, audio):
        return Speech(audio, 1.0) if self.speech else None


class FakeTranscriber:
    ready = True

    def __init__(self, text):
        self.text = text
        self.audios = []

    async def transcribe(self, audio):
        self.audios.append(audio)
        return self.text, 12


def brain(llm, core, **kw):
    b = JarvisBrain(
        llm,
        core,
        LocalTools(runner=Runner(), config={}),
        primary="fake/p",
        escalation="fake/e",
        **kw,
    )
    return b


async def _ask(b, text, mode="texto"):
    got = []

    async def emit(ev):
        got.append(ev)

    await b.ask("r1", text, emit, mode=mode)
    return got


async def test_voz_fala_as_frases_conforme_chegam_e_limita_a_duas():
    agenda = {
        "eventos": [{"titulo": "Dentista", "data": "sexta 09/10/2026", "hora": "14:00"}],
        "total": 1,
        "omitidos": 0,
    }
    core = FakeCore({"buscar_eventos": ToolResult(True, agenda)})
    llm = StreamingScriptedLLM(
        call("buscar_eventos", {"de": "2026-10-09", "ate": "2026-10-09"}),
        reply("Amanhã você tem dentista às duas da tarde. É o único compromisso. Mais nada."),
    )
    speaker = FakeSpeaker()
    evs = await _ask(
        brain(llm, core, speaker=speaker, filler=False), "o que eu tenho amanhã?", "voz"
    )
    assert speaker.said == ["Amanhã você tem dentista às duas da tarde.", "É o único compromisso."]
    tokens = "".join(e.text for e in evs if e.type == "token")
    assert tokens.startswith("Amanhã você tem dentista")
    assert evs[-1].type == "done" and evs[-1].text.endswith("Mais nada.")
    system = llm.calls[0]["messages"][0]["content"]
    assert "Modo voz" in system and "por extenso" in system


async def test_modo_texto_nao_fala_mas_recebe_tokens():
    speaker = FakeSpeaker()
    llm = StreamingScriptedLLM(reply("Oi, Kaio. Tudo certo."))
    evs = await _ask(brain(llm, FakeCore(), speaker=speaker), "oi", "texto")
    assert speaker.said == []
    assert any(e.type == "token" for e in evs)
    assert "Modo voz" not in llm.calls[0]["messages"][0]["content"]


async def test_filler_ao_chamar_ferramenta_em_voz():
    core = FakeCore(
        {"buscar_eventos": ToolResult(True, {"eventos": [], "total": 0, "omitidos": 0})}
    )
    llm = StreamingScriptedLLM(call("buscar_eventos", {}), reply("Nada amanhã."))
    speaker = FakeSpeaker()
    await _ask(brain(llm, core, speaker=speaker, filler=True), "o que eu tenho amanhã?", "voz")
    assert speaker.said[0] in FILLERS and speaker.said[1:] == ["Nada amanhã."]


async def test_voice_transcreve_e_responde():
    core = FakeCore()
    llm = StreamingScriptedLLM(reply("Hoje é quinta-feira."))
    speaker, tr = FakeSpeaker(), FakeTranscriber("que dia é hoje?")
    b = brain(llm, core, speaker=speaker, transcriber=tr, vad=FakeVad(True))
    got = []

    async def emit(ev):
        got.append(ev)

    pcm = np.zeros(16000, dtype=np.int16).tobytes()
    await b.voice("v1", pcm, 16000, emit)
    assert [e.type for e in got][:2] == ["heard", "step"]
    assert got[0].text == "que dia é hoje?"
    assert speaker.said == ["Hoje é quinta-feira."]
    assert llm.calls[0]["messages"][-1] == {"role": "user", "content": "que dia é hoje?"}


async def test_sem_fala_vira_no_speech_sem_chamar_o_modelo():
    llm = StreamingScriptedLLM()
    b = brain(
        llm, FakeCore(), speaker=FakeSpeaker(), transcriber=FakeTranscriber("x"), vad=FakeVad(False)
    )
    got = []

    async def emit(ev):
        got.append(ev)

    await b.voice("v2", b"\x00\x00" * 8000, 16000, emit)
    assert [e.type for e in got] == ["no_speech"] and llm.calls == []


async def test_interrupt_para_a_fala():
    speaker = FakeSpeaker()
    b = brain(StreamingScriptedLLM(), FakeCore(), speaker=speaker)
    b.interrupt()
    assert speaker.stopped == 1


# --- servidor


class VoiceBrain:
    def __init__(self):
        self.voices = []
        self.interrupted = 0

    async def ask(self, rid, text, emit, mode="texto"):
        await emit(events.done(rid, f"{mode}: {text}"))

    async def voice(self, rid, pcm, sample_rate, emit):
        self.voices.append((rid, pcm, sample_rate))
        await emit(events.heard(rid, "ouvi"))
        await emit(events.done(rid, "ok"))

    async def resolve_confirmation(self, confirm_id, accepted):
        pass

    def interrupt(self):
        self.interrupted += 1


async def _recv_until(ws, kind):
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), 5))
        if m["type"] in (kind, "error"):
            return m


async def test_quadros_binarios_entre_voice_start_e_voice_end():
    b = VoiceBrain()
    async with (
        JarvisServer(b, token="tk").run(session_file=None) as port,
        connect(f"ws://127.0.0.1:{port}/?token=tk") as ws,
    ):
        await ws.send(b"\x01\x02")  # fora de uma gravação: ignorado
        await ws.send(json.dumps({"type": "voice_start", "id": "v1", "sampleRate": 48000}))
        await ws.send(b"\x01\x02")
        await ws.send(b"\x03\x04")
        await ws.send(json.dumps({"type": "voice_end", "id": "v1"}))
        assert (await _recv_until(ws, "done"))["text"] == "ok"
        await ws.send(json.dumps({"type": "ask", "id": "a1", "text": "oi", "mode": "voz"}))
        assert (await _recv_until(ws, "done"))["text"] == "voz: oi"
        await ws.send(json.dumps({"type": "interrupt"}))
        await asyncio.sleep(0.05)
    assert b.voices == [("v1", b"\x01\x02\x03\x04", 48000)]
    assert b.interrupted == 1
