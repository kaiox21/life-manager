import hashlib
import io
import tarfile

import pytest

from jarvis import wake_model as wm


def make_archive(tmp_path, extra=None):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:bz2") as tar:
        for name in (*wm.NEEDED, *(extra or [])):
            data = b"x"
            info = tarfile.TarInfo(name if name.startswith(("/", "..")) else f"{wm.NAME}/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    path = tmp_path / "kws.tar.bz2"
    path.write_bytes(buf.getvalue())
    return path, hashlib.sha256(buf.getvalue()).hexdigest()


def test_baixa_confere_e_extrai_so_o_necessario(tmp_path):
    archive, sha = make_archive(tmp_path, extra=["README.md", "../fora.txt"])
    dest = tmp_path / "kws"
    path = wm.ensure(url=archive.as_uri(), sha256=sha, dest=dest)
    assert sorted(p.name for p in path.iterdir()) == sorted(wm.NEEDED)
    assert wm.present(dest)
    assert not (tmp_path / "fora.txt").exists()
    assert wm.ensure(url="http://nao-usado", sha256="x", dest=dest) == path  # já presente


def test_hash_errado_recusa(tmp_path):
    archive, _ = make_archive(tmp_path)
    with pytest.raises(ValueError, match="hash"):
        wm.ensure(url=archive.as_uri(), sha256="0" * 64, dest=tmp_path / "kws")
    assert not wm.present(tmp_path / "kws")
