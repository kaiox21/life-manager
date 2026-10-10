"""Calibração da palavra "Jarvis" com a voz do Kaio (tarefa 4.1 do jarvis-wake-word).

    uv run --extra jarvis python -m jarvis.wake_calibrar gravar      # imprime a pasta
    uv run --extra jarvis python -m jarvis.wake_calibrar analisar PASTA --apagar

`gravar`: 20 frases com "Jarvis" (a frase aparece numa janela no centro da tela; um bipe
abre e outro fecha cada gravação de 4 s) e 5 min de fala normal sem a palavra. O áudio fica
numa pasta temporária.
`analisar`: roda a escuta (porteiro de voz + detector, como no cérebro) em cada combinação de
limiar, peso e variantes, e imprime acertos e alarmes falsos. `--apagar` remove o áudio no fim.
Desligue "Ouvir 'Jarvis'" no menu antes de gravar, senão o Jarvis responde às frases.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from jarvis.wake import RATE, WORDS, SherpaSpotter, WakeListener
from jarvis.wake_model import model_dir

PHRASES = [
    "Hey Jarvis",
    "Jarvis, que horas são?",
    "Hey Jarvis",
    "Jarvis, o que eu tenho amanhã?",
    "Jarvis",
    "Jarvis, quanto eu gastei esse mês?",
    "Hey Jarvis",
    "Jarvis, abre o Spotify",
    "Ô Jarvis, como estão meus terminais?",
    "Jarvis, lança cinquenta reais de mercado",
    "Hey Jarvis",
    "Jarvis, quando fecha a fatura do Nubank?",
    "Jarvis",
    "Jarvis, me lembra de ligar pra minha mãe às seis",
    "Hey Jarvis",
    "Jarvis, abre o painel",
    "Jarvis, vai chover hoje?",
    "Hey Jarvis",
    "Jarvis, qual é o meu próximo compromisso?",
    "Jarvis, obrigado",
]
CLIP_S = 4.0
NORMAL_S = 300.0
SOUNDS = Path("/System/Library/Sounds")

THRESHOLDS = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3)
SCORES = (1.0, 1.5, 2.0, 3.0)
VARIANTS = {
    "padrão": WORDS,
    "+jarbas/djarvis": (*WORDS, "JARBAS", "DJARVIS"),
}


def _show(text: str, seconds: float) -> subprocess.Popen[bytes]:
    """Janela no centro da tela por `seconds` (notificação de script o macOS costuma esconder)."""
    script = (
        'tell application "System Events" to display dialog '
        f'{json.dumps(text)} with title "Calibração do Jarvis" buttons {{"OK"}} '
        f"giving up after {max(1, round(seconds))}"
    )
    return subprocess.Popen(
        ["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def _notify(text: str, seconds: float = 5) -> None:
    _show(text, seconds)


def _beep(name: str) -> None:
    subprocess.run(["afplay", str(SOUNDS / f"{name}.aiff")], check=False)


def _record(seconds: float) -> np.ndarray:
    import sounddevice as sd

    audio = sd.rec(int(seconds * RATE), samplerate=RATE, channels=1, dtype="int16")
    sd.wait()
    return audio[:, 0]


def record() -> Path:
    folder = Path(tempfile.mkdtemp(prefix="jarvis-calibracao-"))
    _notify("Começando em 5 s: leia cada frase quando ouvir o bipe.", 5)
    time.sleep(5)
    for i, phrase in enumerate(PHRASES, 1):
        _show(f"{i}/{len(PHRASES)}\n\nNo bipe, diga:\n\n“{phrase}”", 1.5 + CLIP_S + 0.5)
        time.sleep(1.5)
        _beep("Tink")
        np.save(folder / f"pos{i:02d}.npy", _record(CLIP_S))
        _beep("Pop")
        print(f"frase {i}/{len(PHRASES)} gravada", flush=True)
        time.sleep(0.5)
    _notify(
        "Agora 5 minutos de fala normal, SEM dizer Jarvis (conversa, vídeo, ler algo).\n\n"
        "Começa no próximo som e termina no seguinte.",
        8,
    )
    time.sleep(4)
    _beep("Glass")
    np.save(folder / "neg.npy", _record(NORMAL_S))
    _beep("Glass")
    _notify("Pronto, pode parar. Gravação terminada.")
    print(f"PASTA {folder}", flush=True)
    return folder


def _count(audio: np.ndarray, words: tuple[str, ...], threshold: float, score: float) -> int:
    from jarvis.audio import Vad

    hits = {"n": 0}
    listener: WakeListener

    def woke() -> None:
        hits["n"] += 1

    def request(_a: np.ndarray) -> None:
        listener.done()  # volta a ouvir o nome, como depois de um pedido

    listener = WakeListener(
        SherpaSpotter(model_dir(), words, threshold, score),
        Vad(),
        on_wake=woke,
        on_request=request,
        on_nothing=lambda: listener.done(),
    )
    silence = np.zeros(RATE, np.int16)
    listener.feed(np.concatenate([silence, audio, silence, silence]).tobytes())
    return hits["n"]


def analyze(folder: Path) -> list[dict[str, object]]:
    positives = [np.load(p) for p in sorted(folder.glob("pos*.npy"))]
    negative = np.load(folder / "neg.npy")
    peak = max(int(np.abs(p.astype(np.int32)).max()) for p in positives)
    print(f"{len(positives)} frases, {len(negative) / RATE:.0f} s de fala normal, pico {peak}")
    rows = []
    for name, words in VARIANTS.items():
        for threshold in THRESHOLDS:
            for score in SCORES:
                hit = sum(_count(p, words, threshold, score) > 0 for p in positives)
                false = _count(negative, words, threshold, score)
                row = {
                    "variantes": name,
                    "limiar": threshold,
                    "peso": score,
                    "acertos": f"{hit}/{len(positives)}",
                    "taxa": round(hit / len(positives), 2),
                    "alarmes_falsos": false,
                }
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
    return rows


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "gravar":
        record()
    elif len(sys.argv) >= 3 and sys.argv[1] == "analisar":
        folder = Path(sys.argv[2])
        try:
            analyze(folder)
        finally:
            if "--apagar" in sys.argv:
                shutil.rmtree(folder, ignore_errors=True)
                print("áudio apagado")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
