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


# --- voz da Fish Audio (rede e player falsos)


class FakePlayer:
    def __init__(self, audio, pumps=2):
        self.audio, self.left, self.stopped = audio, pumps, False

    def isPlaying(self):  # noqa: N802 — mesmo nome do AVAudioPlayer
        self.left -= 1
        return self.left > 0 and not self.stopped

    def stop(self):
        self.stopped = True


def _fish(fetch, clock=lambda: 0.0):
    from jarvis.tts import FishSynth

    events: list[tuple[str, str]] = []
    fallback = FakeSynth(lambda k, t: events.append((f"local:{k}", t)))
    played: list[bytes] = []

    def play(audio):
        played.append(audio)
        return FakePlayer(audio)

    synth = FishSynth(
        lambda k, t: events.append((k, t)),
        fallback,
        "key",
        "voz",
        fetch=fetch,
        play=play,
        clock=clock,
    )
    return synth, fallback, events, played


async def _pump(synth, n=12):
    for _ in range(n):
        synth.pump()
        await asyncio.sleep(0)


async def test_fish_toca_as_frases_na_ordem_mesmo_se_a_segunda_baixar_antes():
    gates = {"Primeira.": asyncio.Event(), "Segunda.": asyncio.Event()}

    async def fetch(text):
        await gates[text].wait()
        return text.encode()

    synth, _, events, played = _fish(fetch)
    synth.speak("Primeira.")
    synth.speak("Segunda.")
    gates["Segunda."].set()
    await _pump(synth, 3)
    assert played == []  # espera a primeira, mesmo com a segunda pronta
    gates["Primeira."].set()
    await _pump(synth)
    assert played == [b"Primeira.", b"Segunda."]
    assert [e for e in events if e[0] == "start"] == [("start", "Primeira."), ("start", "Segunda.")]
    assert events[-1] == ("finish", "Segunda.")


async def test_fish_fora_do_ar_cai_para_a_voz_local_e_fica_de_lado():
    now = [100.0]

    async def fetch(text):
        raise ConnectionError("sem internet")

    synth, fallback, events, played = _fish(fetch, clock=lambda: now[0])
    synth.speak("Um instante, senhor.")
    synth.speak("Amanhã está livre.")
    await _pump(synth, 8)
    assert played == []
    assert ("local:start", "Um instante, senhor.") in events
    assert ("local:start", "Amanhã está livre.") in events
    synth.speak("Mais uma.")  # dentro dos 5 min: nem tenta a Fish
    assert fallback.queue == ["Mais uma."]


async def test_fish_interromper_para_tudo():
    async def fetch(text):
        return text.encode()

    synth, fallback, events, played = _fish(fetch)
    synth.speak("Frase longa.")
    synth.speak("Outra.")
    await _pump(synth, 2)
    synth.stop()
    await _pump(synth, 6)
    assert played == [b"Frase longa."]
    assert ("cancel", "Frase longa.") in events
    assert ("stop", "") in fallback.log


async def test_fish_frase_fixa_guardada_sai_sem_rede():
    calls: list[str] = []

    async def fetch(text):
        calls.append(text)
        return text.encode()

    synth, _, events, played = _fish(fetch)
    synth.prefetch(["Um instante, senhor."])
    await _pump(synth, 2)
    synth.speak("Um instante, senhor.")
    synth.pump()  # no mesmo pump: já toca, sem esperar download
    assert played == [b"Um instante, senhor."]
    assert calls == ["Um instante, senhor."]  # baixou uma vez só, no prefetch
