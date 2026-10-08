"""Transcrição real (marcador whisper): uv run pytest -m whisper -s"""

import shutil
import subprocess

import pytest

from app.agent.tools.resolve import normalize
from app.integrations.transcribe import FasterWhisper

pytestmark = pytest.mark.whisper


@pytest.mark.skipif(shutil.which("say") is None, reason="precisa do say do macOS")
async def test_transcreve_portugues(tmp_path):
    audio = tmp_path / "gasto.m4a"
    subprocess.run(  # noqa: ASYNC221 - teste manual, bloquear aqui não importa
        [
            "say",
            "-v",
            "Luciana",
            "-o",
            str(audio),
            "--data-format=aac",
            "paguei cento e vinte reais de gasolina no pix",
        ],
        check=True,
    )
    whisper = FasterWhisper("small")
    await whisper.transcribe(audio.read_bytes())  # 1ª chamada carrega o modelo
    result = await whisper.transcribe(audio.read_bytes(), hints=["Nubank", "Inter"])
    print(f"\n{result.model} em {result.elapsed_ms} ms (modelo já carregado): {result.text!r}")
    text = normalize(result.text)
    assert "gasolina" in text and "pix" in text
