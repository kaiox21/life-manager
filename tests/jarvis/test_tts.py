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
