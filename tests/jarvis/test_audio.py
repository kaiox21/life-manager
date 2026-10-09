import numpy as np

from jarvis.audio import pcm16_to_float


def test_pcm16_para_float_16k():
    pcm = np.array([0, 16384, -32768, 32767], dtype=np.int16).tobytes()
    out = pcm16_to_float(pcm, 16000)
    assert out.dtype == np.float32
    assert np.allclose(out, [0, 0.5, -1.0, 32767 / 32768])


def test_reamostra_de_48k():
    t = np.arange(48000) / 48000
    pcm = (np.sin(2 * np.pi * 440 * t) * 20000).astype(np.int16).tobytes()
    out = pcm16_to_float(pcm, 48000)
    assert len(out) == 16000
    assert abs(out).max() > 0.5


async def test_prewarm_acorda_o_modelo_sem_atrapalhar_a_transcricao(monkeypatch):
    import asyncio

    import numpy as np

    from jarvis.audio import Transcriber

    calls: list[int] = []
    t = Transcriber()
    monkeypatch.setattr(t, "_run", lambda audio, warm=False: calls.append(len(audio)) or "oi")
    t.prewarm()
    t.prewarm()  # já acordando: não empilha
    await asyncio.sleep(0)  # o Kaio ainda está falando
    text, _ = await t.transcribe(np.zeros(16000, dtype=np.float32))
    assert text == "oi"
    assert calls == [4000, 16000]  # acordou primeiro, depois transcreveu
