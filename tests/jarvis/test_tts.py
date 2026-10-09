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


async def _wait(cond, limit=2.0):
    for _ in range(int(limit / 0.01)):
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
    await _settle()
    assert events == [("start", "Primeira.")]  # tocou sem a frase ter chegado inteira
    gates["Segunda."].set()
    await _settle()
    assert ("start", "Segunda.") not in events  # espera a primeira acabar
    gates["Primeira."].set()
    await _settle()
    assert [e for e in events if e[0] in ("start", "finish")] == [
        ("start", "Primeira."),
        ("finish", "Primeira."),
        ("start", "Segunda."),
        ("finish", "Segunda."),
    ]
    assert b"".join(out.written) == _audio("Primeira.") + _audio("Segunda.")


async def test_fish_fora_do_ar_cai_para_a_voz_local_e_fica_de_lado():
    now = [100.0]

    async def chunks(text):
        raise ConnectionError("sem internet")
        yield b""

    synth, fallback, events, out = _fish(chunks, clock=lambda: now[0])
    synth.speak("Um instante, senhor.")
    synth.speak("Amanhã está livre.")
    await _settle(synth)
    assert out.written == []
    assert ("local:start", "Um instante, senhor.") in events
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
    await _settle()
    synth.stop()
    gate.set()
    await _settle()
    assert ("cancel", "Frase longa.") in events
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
    await _settle()
    synth.speak("Um instante, senhor.")
    await _settle()
    assert ("start", "Um instante, senhor.") in events
    assert calls == ["Um instante, senhor."]  # baixou uma vez só, no prefetch
