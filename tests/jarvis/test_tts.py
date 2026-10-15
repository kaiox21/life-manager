import asyncio

from jarvis.tts import Speaker, split_sentences


def test_split_sentences():
    assert split_sentences("Você tem dentista às quatorze horas. Depois, nada mais! Certo?") == [
        "Você tem dentista às quatorze horas.",
        "Depois, nada mais!",
        "Certo?",
    ]
    assert split_sentences("R$ 47,90 no almoço, dia 8.") == ["R$ 47,90 no almoço, dia 8."]
    assert split_sentences("   ") == []


class FakeSynth:
    """Backend falso: cada frase começa no pump seguinte e termina 3 pumps depois."""

    def __init__(self, on_event):
        self.on_event = on_event
        self.queue: list[str] = []
        self.current: tuple[str, int] | None = None
        self.log: list[tuple[str, str]] = []

    def speak(self, text):
        self.queue.append(text)

    def stop(self):
        self.log.append(("stop", ""))
        self.queue.clear()
        if self.current:
            self.on_event("cancel", self.current[0])
            self.current = None

    def pump(self):
        if self.current:
            text, left = self.current
            if left == 0:
                self.current = None
                self.on_event("finish", text)
            else:
                self.current = (text, left - 1)
            return
        if self.queue:
            text = self.queue.pop(0)
            self.current = (text, 3)
            self.log.append(("speak", text))
            self.on_event("start", text)


async def _wait(cond, limit=2.0, pump=None):
    """Espera a condição (até `limit` s) em vez de contar voltas do laço: a reprodução passa
    por threads e o tempo varia entre o Mac e o runner da CI."""
    for _ in range(int(limit / 0.01)):
        if pump is not None:
            pump()
        if cond():
            return True
        await asyncio.sleep(0.01)
    return cond()


async def test_fala_em_ordem_e_avisa_inicio_de_cada_frase_e_fim():
    events = []
    holder = {}
    sp = Speaker(
        lambda cb: holder.setdefault("s", FakeSynth(cb)),
        on_event=lambda k, t: events.append((k, t)),
    )
    sp.say("Primeira.")
    sp.say("Segunda.")
    assert await _wait(
        lambda: events == [("start", "Primeira."), ("start", "Segunda."), ("idle", "")]
    )
    assert [t for k, t in holder["s"].log if k == "speak"] == ["Primeira.", "Segunda."]
    assert not sp.speaking
    sp.close()


async def test_stop_corta_e_esvazia():
    events = []
    holder = {}
    sp = Speaker(
        lambda cb: holder.setdefault("s", FakeSynth(cb)), on_event=lambda k, t: events.append(k)
    )
    sp.say("Uma frase bem longa que vai ser cortada.")
    sp.say("Nunca falada.")
    assert await _wait(lambda: events == ["start"])
    sp.stop()
    assert events == ["start", "idle"] and not sp.speaking
    await asyncio.sleep(0.1)
    assert ("speak", "Nunca falada.") not in holder["s"].log
    sp.close()


# --- voz da Fish Audio (rede e saída de áudio falsas)


class FakeOut:
    latency = 0.0

    def __init__(self):
        self.written: list[bytes] = []
        self.aborted = 0

    def write(self, data):
        self.written.append(data)

    def abort(self):
        self.aborted += 1


def _fish(chunks, clock=lambda: 0.0):
    from jarvis.tts import FishSynth

    events: list[tuple[str, str]] = []
    fallback = FakeSynth(lambda k, t: events.append((f"local:{k}", t)))
    out = FakeOut()
    synth = FishSynth(
        lambda k, t: events.append((k, t)),
        fallback,
        "key",
        "voz",
        chunks=chunks,
        out=out,
        clock=clock,
    )
    return synth, fallback, events, out


async def _settle(synth=None, n=30):
    for _ in range(n):
        if synth is not None:
            synth.pump()
        await asyncio.sleep(0)


def _audio(text: str) -> bytes:
    return text.encode().ljust(6000, b"\0")  # > 0,1 s de áudio: passa do pré-buffer


async def test_fish_toca_enquanto_chega_e_na_ordem():
    gates = {"Primeira.": asyncio.Event(), "Segunda.": asyncio.Event()}

    async def chunks(text):
        audio = _audio(text)
        yield audio[:5000]  # já passa do pré-buffer: começa a tocar antes do fim
        await gates[text].wait()
        yield audio[5000:]

    synth, _, events, out = _fish(chunks)
    synth.speak("Primeira.")
    synth.speak("Segunda.")
    # tocou sem a frase ter chegado inteira
    assert await _wait(lambda: events == [("start", "Primeira.")])
    gates["Segunda."].set()
    await _settle()
    assert ("start", "Segunda.") not in events  # espera a primeira acabar
    gates["Primeira."].set()
    expected = [
        ("start", "Primeira."),
        ("finish", "Primeira."),
        ("start", "Segunda."),
        ("finish", "Segunda."),
    ]
    assert await _wait(lambda: [e for e in events if e[0] in ("start", "finish")] == expected)
    assert b"".join(out.written) == _audio("Primeira.") + _audio("Segunda.")


async def test_fish_fora_do_ar_cai_para_a_voz_local_e_fica_de_lado():
    now = [100.0]

    async def chunks(text):
        raise ConnectionError("sem internet")
        yield b""

    synth, fallback, events, out = _fish(chunks, clock=lambda: now[0])
    synth.speak("Um instante, senhor.")
    synth.speak("Amanhã está livre.")
    assert await _wait(lambda: ("local:start", "Um instante, senhor.") in events, pump=synth.pump)
    assert out.written == []
    assert "Amanhã está livre." in fallback.queue or ("local:start", "Amanhã está livre.") in events
    synth.speak("Mais uma.")  # dentro dos 5 min: nem tenta a Fish
    assert fallback.queue[-1] == "Mais uma."


async def test_fish_interromper_corta_o_audio():
    gate = asyncio.Event()

    async def chunks(text):
        yield _audio(text)[:5000]
        await gate.wait()
        yield b"resto"

    synth, fallback, events, out = _fish(chunks)
    synth.speak("Frase longa.")
    synth.speak("Outra.")
    assert await _wait(lambda: ("start", "Frase longa.") in events)
    synth.stop()
    gate.set()
    assert await _wait(lambda: ("cancel", "Frase longa.") in events)
    await _settle()
    assert ("start", "Outra.") not in events
    assert out.aborted == 1
    assert ("stop", "") in fallback.log


async def test_fish_frase_fixa_guardada_sai_sem_rede():
    calls: list[str] = []

    async def chunks(text):
        calls.append(text)
        yield _audio(text)

    synth, _, events, out = _fish(chunks)
    synth.prefetch(["Um instante, senhor."])
    assert await _wait(lambda: calls == ["Um instante, senhor."])
    synth.speak("Um instante, senhor.")
    assert await _wait(lambda: ("start", "Um instante, senhor.") in events)
    assert calls == ["Um instante, senhor."]  # baixou uma vez só, no prefetch


async def test_fish_manda_o_nivel_da_voz_no_ritmo_do_som():
    import numpy as np

    loud = (np.sin(np.arange(9_600) / 3) * 12_000).astype(np.int16).tobytes()  # 0,4 s alto
    quiet = np.zeros(4_800, np.int16).tobytes()  # 0,2 s de silêncio

    async def chunks(text):
        yield loud + quiet

    synth, _, _, out = _fish(chunks)
    levels: list[float] = []
    synth.on_level = levels.append
    synth.speak("Frase.")
    await _settle(synth)
    assert len(levels) <= 2  # os níveis saem quando o som sai, não quando o áudio chega
    await asyncio.sleep(0.75)
    # ~15 por segundo: 0,6 s de áudio dá ~9 níveis, mais o zero do fim
    assert 8 <= len(levels) <= 12
    assert max(levels[:5]) > 0.8 and levels[-2] < 0.05 and levels[-1] == 0.0


async def test_fish_sem_ouvinte_de_nivel_nao_faz_nada():
    async def chunks(text):
        yield _audio(text)

    synth, _, events, _ = _fish(chunks)
    synth.speak("Frase.")
    # tocou normalmente, sem on_level
    assert await _wait(lambda: ("start", "Frase.") in events, pump=synth.pump)


# --- saída de áudio segue o dispositivo padrão (fone ligado/tirado, AirPods)


class FakeSD:
    def __init__(self):
        self.log = []
        self.fail_next_write = False
        sd = self

        class Stream:
            latency = 0.01

            def __init__(self, **kw):
                sd.log.append("abre")

            def start(self):
                pass

            def write(self, data):
                if sd.fail_next_write:
                    sd.fail_next_write = False
                    raise RuntimeError("PaErrorCode -9986: dispositivo sumiu")
                sd.log.append("escreve")

            def abort(self):
                pass

            def close(self):
                sd.log.append("fecha")

        self.RawOutputStream = Stream

    def _terminate(self):
        self.log.append("reinicia-portaudio")

    def _initialize(self):
        pass


def _out(monkeypatch, device):
    import sys

    from jarvis.tts import PortAudioOut

    sd = FakeSD()
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    current = {"id": device}
    return PortAudioOut(24_000, current=lambda: current["id"]), sd, current


def test_saida_segue_o_dispositivo_padrao(monkeypatch):
    out, sd, current = _out(monkeypatch, 41)  # alto-falante
    assert out.follow_default() is False and sd.log == ["abre"]
    current["id"] = 115  # o Kaio liga o fone
    assert out.follow_default() is True
    assert sd.log == ["abre", "fecha", "reinicia-portaudio", "abre"]
    assert out.follow_default() is False  # já está no fone


def test_dispositivo_some_no_meio_da_frase(monkeypatch):
    out, sd, _ = _out(monkeypatch, 41)
    sd.fail_next_write = True
    out.write(b"\0\0" * 10)  # não estoura: a thread de áudio reabre e escreve
    out.drain()
    assert sd.log[-3:] == ["reinicia-portaudio", "abre", "escreve"]


def test_thread_de_audio_mantem_o_ritmo_e_a_folga(monkeypatch):
    import time

    out, sd, _ = _out(monkeypatch, 41)
    second = 24_000 * 2  # bytes de 1 s
    written = []
    sd_write = sd.RawOutputStream.write

    def realtime(self, data):  # o dispositivo consome em tempo real
        time.sleep(len(data) / second)
        written.append(len(data))
        return sd_write(self, data)

    monkeypatch.setattr(sd.RawOutputStream, "write", realtime)
    t0 = time.monotonic()
    out.write(b"\0" * (second // 10))  # 0,1 s: entra na fila sem esperar
    assert time.monotonic() - t0 < 0.05
    for _ in range(6):  # mais 0,6 s: espera a fila ficar abaixo de 0,4 s (ritmo do som)
        out.write(b"\0" * (second // 10))
    assert time.monotonic() - t0 > 0.2
    out.drain()
    assert sum(written) == 7 * (second // 10)


def test_calar_descarta_a_fila(monkeypatch):
    import time

    out, sd, _ = _out(monkeypatch, 41)
    monkeypatch.setattr(sd.RawOutputStream, "write", lambda self, d: time.sleep(0.05))
    for _ in range(5):
        out.write(b"\0" * 2400)
    out.abort()
    t0 = time.monotonic()
    out.drain()
    assert time.monotonic() - t0 < 0.2  # não toca o resto


async def test_fish_confere_a_saida_antes_de_cada_frase():
    calls = []

    async def chunks(text):
        yield _audio(text)

    synth, _, events, out = _fish(chunks)
    out.follow_default = lambda: calls.append("confere") or False
    synth.speak("Primeira.")
    synth.speak("Segunda.")
    assert await _wait(lambda: ("finish", "Segunda.") in events, pump=synth.pump)
    assert calls == ["confere", "confere"]


def test_coreaudio_responde_a_saida_padrao():
    import sys

    from jarvis.tts import default_output_id

    got = default_output_id()
    if sys.platform == "darwin":
        assert isinstance(got, int) and got > 0


async def test_fish_pede_qualidade_normal_com_protecao():
    import json

    import httpx

    from jarvis.tts import FishSynth

    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, content=b"\0\0" * 10)

    synth = FishSynth(lambda k, t: None, FakeSynth(lambda k, t: None), "key", "voz", out=FakeOut())
    synth._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    _ = [c async for c in synth._http_chunks("Olá.")]
    assert seen["latency"] == "normal" and seen["features"] == ["quality-guard"]

    seen.clear()
    fast = FishSynth(
        lambda k, t: None,
        FakeSynth(lambda k, t: None),
        "key",
        "voz",
        out=FakeOut(),
        latency="balanced",
        quality_guard=False,
    )
    fast._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    _ = [c async for c in fast._http_chunks("Olá.")]
    assert seen["latency"] == "balanced" and "features" not in seen
