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
