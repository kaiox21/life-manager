import asyncio
import json
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest
from websockets.asyncio.client import connect

from jarvis import events
from jarvis.server import JarvisServer
from jarvis.wake import BLOCK, BUSY, IDLE, WAIT, WakeListener, WakeService, strip_name
from jarvis.wake_model import model_dir, present
from tests.fakes import StreamingScriptedLLM, reply
from tests.jarvis.test_agent import FakeCore
from tests.jarvis.test_voice import FakeTranscriber, FakeVad, brain

# --- nome no começo


@pytest.mark.parametrize(
    ("text", "out"),
    [
        ("Jarvis, que horas são?", "Que horas são?"),
        ("jarvis abre o Spotify", "Abre o Spotify"),
        ("Ô Jarvis, como estão meus terminais?", "Como estão meus terminais?"),
        ("Jarbas, quanto eu gastei?", "Quanto eu gastei?"),
        ("Jarvis.", ""),
        ("Jarvis", ""),
        ("Javier disse que vem amanhã", None),
        ("o jarvis é legal", None),
    ],
)
def test_tira_o_nome_do_comeco(text, out):
    assert strip_name(text) == out


# --- máquina de estados (detector e porteiro falsos: o valor do bloco diz o que ele é)

SIL, VOZ, NOME = 0.0, 0.1, 0.2


class FakeSpotter:
    def __init__(self):
        self.seen: list[float] = []
        self.resets = 0

    def accept(self, block):
        self.seen.append(round(float(block[0]), 2))
        return round(float(block[0]), 2) == NOME

    def reset(self):
        self.resets += 1


class FakeGate:
    def is_speech(self, block):
        return float(block[0]) > 0.05


def blocks(*seq):
    out = b""
    for value, n in seq:
        out += (np.full(BLOCK * n, value * 32767, dtype=np.int16)).tobytes()
    return out


def listener(paused=lambda: False):
    got = {"wake": 0, "request": [], "nothing": 0}
    sp = FakeSpotter()
    li = WakeListener(
        sp,
        FakeGate(),
        on_wake=lambda: got.__setitem__("wake", got["wake"] + 1),
        on_request=lambda a: got["request"].append(a),
        on_nothing=lambda: got.__setitem__("nothing", got["nothing"] + 1),
        paused=paused,
    )
    return li, sp, got


def test_nome_e_pedido_vira_um_pedido_com_o_comeco_da_frase():
    li, sp, got = listener()
    li.feed(blocks((SIL, 20), (VOZ, 2), (NOME, 1), (VOZ, 10), (SIL, 8)))
    assert got["wake"] == 1 and len(got["request"]) == 1
    audio = got["request"][0]
    # começa no buffer circular (1,5 s antes do nome, com a folga) e vai até a pausa de 0,8 s
    assert len(audio) == BLOCK * (15 + 10 + 8)
    assert li.state == BUSY
    li.done()
    assert li.state == IDLE


def test_detector_recebe_a_folga_antes_do_vad():
    li, sp, _ = listener()
    li.feed(blocks((SIL, 10), (VOZ, 1)))
    assert sp.seen == [SIL, SIL, SIL, SIL, SIL, VOZ]  # 0,5 s antes + o bloco com voz


def test_fala_sem_o_nome_nao_ativa_e_o_detector_recomeca_na_pausa():
    li, sp, got = listener()
    li.feed(blocks((VOZ, 30), (SIL, 10), (VOZ, 5)))
    assert got["wake"] == 0 and got["request"] == []
    assert sp.resets >= 1


def test_pausado_nao_ouve():
    li, sp, got = listener(paused=lambda: True)
    li.feed(blocks((VOZ, 2), (NOME, 1), (VOZ, 5), (SIL, 10)))
    assert got == {"wake": 0, "request": [], "nothing": 0} and sp.seen == []


def test_pedido_longo_corta_em_15_s():
    li, _, got = listener()
    li.feed(blocks((NOME, 1), (VOZ, 200)))
    assert len(got["request"]) == 1 and len(got["request"][0]) <= BLOCK * 150


def test_so_o_nome_espera_o_pedido_ou_desiste():
    li, _, got = listener()
    li.feed(blocks((NOME, 1), (SIL, 8)))
    assert len(got["request"]) == 1  # o cérebro transcreve, vê só o nome e pede para esperar
    li.wait_request()
    assert li.state == WAIT
    li.feed(blocks((SIL, 10), (VOZ, 5), (SIL, 8)))
    assert len(got["request"]) == 2 and len(got["request"][1]) == BLOCK * 13
    li.wait_request()
    li.feed(blocks((SIL, 60)))
    assert got["nothing"] == 1


def test_blocos_quebrados_sao_juntados():
    li, sp, _ = listener()
    data = blocks((VOZ, 3))
    for i in range(0, len(data), 1000):  # pedaços que não fecham um bloco
        li.feed(data[i : i + 1000])
    assert len(sp.seen) == 3


# --- modelo real com áudio do say (pulado sem o modelo ou sem o say)


def say(tmp_path: Path, text: str, name: str) -> bytes:
    aiff, wav = tmp_path / f"{name}.aiff", tmp_path / f"{name}.wav"
    subprocess.run(["say", "-v", "Luciana", "-o", str(aiff), text], check=True)
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)], check=True
    )
    with wave.open(str(wav)) as w:
        return w.readframes(w.getnframes())


@pytest.mark.skipif(
    not present() or shutil.which("say") is None, reason="sem o modelo ou sem o say"
)
def test_modelo_real_acha_jarvis_e_ignora_fala_comum(tmp_path):
    from jarvis.audio import Vad
    from jarvis.wake import SherpaSpotter

    sil = np.zeros(16000, np.int16).tobytes()
    got = {"wake": 0, "request": []}

    def make():
        return WakeListener(
            SherpaSpotter(model_dir()),
            Vad(),
            on_wake=lambda: got.__setitem__("wake", got["wake"] + 1),
            on_request=lambda a: got["request"].append(a),
            on_nothing=lambda: None,
        )

    li = make()
    li.feed(sil + say(tmp_path, "Jarvis, abre o Spotify", "pos") + sil + sil)
    assert got["wake"] == 1 and len(got["request"]) == 1
    got["wake"], got["request"] = 0, []
    li = make()
    li.feed(
        sil
        + say(tmp_path, "Hoje eu vou ao mercado comprar pão e café, depois volto para casa", "neg")
        + sil
    )
    assert got["wake"] == 0


# --- turno do cérebro


async def run_turn(b, audio=None):
    audio = np.zeros(16000, np.float32) if audio is None else audio
    got = []

    async def emit(ev):
        got.append(ev)

    result = await b.wake_turn("wake-1", audio, emit)
    return result, got


async def test_pedido_vira_pergunta_sem_o_nome():
    b = brain(
        StreamingScriptedLLM(reply("São três da tarde, senhor.")),
        FakeCore(),
        transcriber=FakeTranscriber("Jarvis, que horas são?"),
        vad=FakeVad(True),
    )
    result, got = await run_turn(b)
    assert result == "ok"
    heard = [e for e in got if e.type == "heard"]
    assert heard[0].text == "Que horas são?" and got[-1].type == "done"


async def test_so_o_nome_e_depois_o_pedido():
    t = FakeTranscriber("Jarvis.")
    b = brain(StreamingScriptedLLM(reply("Feito.")), FakeCore(), transcriber=t, vad=FakeVad(True))
    result, got = await run_turn(b)
    assert result == "so_nome" and got == []
    t.text = "abre o Spotify"  # o pedido vem sem o nome
    result, got = await run_turn(b)
    assert result == "ok" and [e for e in got if e.type == "heard"][0].text == "abre o Spotify"


async def test_transcricao_sem_o_nome_e_alarme_falso():
    b = brain(
        StreamingScriptedLLM(),
        FakeCore(),
        transcriber=FakeTranscriber("Javier disse que vem"),
        vad=FakeVad(True),
    )
    result, got = await run_turn(b)
    assert result == "falso" and [e.type for e in got] == ["no_speech"]


async def test_sem_fala_e_vazio():
    b = brain(
        StreamingScriptedLLM(), FakeCore(), transcriber=FakeTranscriber(""), vad=FakeVad(False)
    )
    result, got = await run_turn(b)
    assert result == "vazio" and [e.type for e in got] == ["no_speech"]


async def test_pausas_da_escuta():
    b = brain(StreamingScriptedLLM(reply("ok")), FakeCore())
    assert not b.wake_paused()
    b.set_ptt(True)
    assert b.wake_paused()
    b.set_ptt(False)
    b._speaking_state = True
    assert b.wake_paused()
    b._speaking_state = False
    import time

    b._spoke_at = time.monotonic()
    assert b.wake_paused()  # meio segundo depois de falar
    b._spoke_at = 0
    assert not b.wake_paused()


# --- servidor


class FakeWake:
    def __init__(self):
        self.listening: list[bool] = []
        self.fed = b""

    def set_listening(self, on):
        self.listening.append(on)

    def feed(self, pcm):
        self.fed += pcm


class EchoBrain:
    async def ask(self, rid, text, emit, mode="texto"):
        await emit(events.done(rid, "ok"))

    async def resolve_confirmation(self, cid, ok):
        pass

    async def panel(self, rid, emit):
        pass


async def test_conexao_de_escuta_manda_audio_e_nao_recebe_o_turno():
    server = JarvisServer(EchoBrain(), token="tk")
    wake = FakeWake()
    server.wake = wake
    async with server.run(session_file=None) as port:
        async with (
            connect(f"ws://127.0.0.1:{port}/?token=tk") as app,
            connect(f"ws://127.0.0.1:{port}/?token=tk") as hud,
        ):
            await app.send(json.dumps({"type": "wake_listen", "on": True}))
            await app.send(b"\x10" + b"\x01\x00" * 10)
            await hud.send(b"\x10" + b"\x02\x00" * 10)  # quadro da interface: não é escuta
            await asyncio.sleep(0.2)
            assert wake.listening == [True] and wake.fed == b"\x01\x00" * 10
            await server.broadcast_ui(events.heard("wake-1", "que horas são?"))
            await server.broadcast(events.wake("wake-1"))
            assert json.loads(await asyncio.wait_for(hud.recv(), 2))["type"] == "heard"
            assert json.loads(await asyncio.wait_for(hud.recv(), 2))["type"] == "wake"
            assert json.loads(await asyncio.wait_for(app.recv(), 2))["type"] == "wake"  # só o wake
        await asyncio.sleep(0.2)
        assert wake.listening[-1] is False  # a escuta saiu: desliga


async def test_servico_liga_desliga_e_manda_o_wake():
    sent = []

    async def bc(ev):
        sent.append(ev)

    class B:
        def wake_paused(self):
            return False

        async def wake_turn(self, rid, audio, emit):
            return "ok"

    svc = WakeService(B(), FakeSpotter, FakeGate, bc, bc)
    assert not svc.on
    svc.set_listening(True)
    assert svc.on
    svc.feed(blocks((NOME, 1), (VOZ, 3), (SIL, 8)))
    await asyncio.sleep(0.05)
    assert sent and sent[0].type == "wake" and sent[0].id.startswith("wake-")
    svc.set_listening(False)
    assert not svc.on
