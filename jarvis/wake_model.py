"""Baixa o modelo do detector da palavra "Jarvis" (sherpa-onnx, detecção de palavras-chave).

    python3 jarvis/wake_model.py      baixa (se faltar) e confere o hash

Modelo em inglês (GigaSpeech, 3,3 M parâmetros, Apache 2.0) com vocabulário aberto: a palavra é
escrita em texto, sem treino (openspec/changes/jarvis-wake-word, design, decisão 1). Só a
biblioteca padrão: roda com o /usr/bin/python3 do macOS no install_mac.sh.
"""

import hashlib
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/"
    "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2"
)
SHA256 = "f170013b4716e41b62b9bfd809687c207cef798ef9bc6534d524e17af9b6561a"
NAME = "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
DEST = Path.home() / "Library/Application Support/Jarvis/kws"
NEEDED = (
    "tokens.txt",
    "bpe.model",
    "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
)


def model_dir(dest=DEST):
    return dest / NAME


def present(dest=DEST):
    return all((model_dir(dest) / f).exists() for f in NEEDED)


def ensure(url=URL, sha256=SHA256, dest=DEST):
    """Baixa, confere o hash e extrai (só os arquivos necessários, sem caminhos estranhos)."""
    if present(dest):
        return model_dir(dest)
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "kws.tar.bz2"
        with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as f:
            shutil.copyfileobj(response, f)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != sha256:
            raise ValueError(f"hash do modelo não confere ({digest})")
        out = Path(tmp) / "out"
        with tarfile.open(archive, "r:bz2") as tar:
            wanted = [
                m
                for m in tar.getmembers()
                if m.isfile() and m.name in {f"{NAME}/{n}" for n in NEEDED}
            ]
            for member in wanted:
                tar.extract(member, out)  # nomes conferidos acima: nada fora da pasta
        shutil.rmtree(model_dir(dest), ignore_errors=True)
        shutil.move(str(out / NAME), str(model_dir(dest)))
    return model_dir(dest)


def main():
    try:
        path = ensure()
    except Exception as exc:  # noqa: BLE001
        print("modelo da palavra 'Jarvis' não baixado: " + str(exc))
        return 1
    print("modelo da palavra 'Jarvis' em " + str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
