import json

from jarvis.terminals import DONE, PERMISSION, WAITING, WORKING, Terminals


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def ev(evento, pid=100, sessao="s1", pasta="/Users/kaio/Downloads/life-manager", t=1000.0, **kw):
    return {"evento": evento, "pid": pid, "sessao": sessao, "pasta": pasta, "t": t, **kw}


def _terms(tmp_path, alive=lambda pid: True, clock=None):
    return Terminals(tmp_path / "e.jsonl", clock=clock or Clock(), alive=alive)


def test_duas_sessoes_numeradas_por_ordem(tmp_path):
    ts = _terms(tmp_path)
    ts.apply(ev("SessionStart", pid=100))
    ts.apply(ev("SessionStart", pid=200, sessao="s2", pasta="/Users/kaio/AmicusIA/sisdec"))
    assert [(t["numero"], t["pasta"], t["estado"]) for t in ts.snapshot()] == [
        (1, "life-manager", WAITING),
        (2, "sisdec", WAITING),
    ]


def test_permissao_avisa_e_some_no_proximo_evento(tmp_path):
    ts = _terms(tmp_path)
    ts.apply(ev("UserPromptSubmit"))
    alert = ts.apply(ev("PermissionRequest", ferramenta="Bash", resumo="npm test"))
    assert alert["texto"] == "Terminal 1 (life-manager) está pedindo para rodar `npm test`"
    assert ts.snapshot()[0]["estado"] == PERMISSION
    assert ts.snapshot()[0]["resumo"] == "npm test"
    ts.apply(ev("PostToolUse"))
    assert ts.snapshot()[0]["estado"] == WORKING
    assert ts.snapshot()[0]["resumo"] == ""


def test_permissao_sem_resposta_volta_a_trabalhando_em_20s(tmp_path):
    clock = Clock(1000.0)
    ts = _terms(tmp_path, clock=clock)
    ts.apply(ev("PermissionRequest", ferramenta="Bash", resumo="npm test", t=1000.0))
    clock.t = 1015.0
    assert ts.tick() is False
    clock.t = 1021.0
    assert ts.tick() is True
    assert ts.snapshot()[0]["estado"] == WORKING


def test_clear_mantem_o_numero(tmp_path):
    ts = _terms(tmp_path)
    ts.apply(ev("SessionStart", pid=100, sessao="s1"))
    ts.apply(ev("SessionStart", pid=200, sessao="s9", pasta="/x/sisdec"))
    ts.apply(ev("SessionEnd", pid=100, sessao="s1"))
    ts.apply(ev("SessionStart", pid=100, sessao="s2"))  # /clear: nova sessão, mesmo processo
    assert [(t["numero"], t["sessao"]) for t in ts.snapshot()] == [(1, "s2"), (2, "s9")]


def test_processo_fechado_libera_o_numero(tmp_path):
    alive = {100: True, 200: True}
    clock = Clock(1000.0)
    ts = _terms(tmp_path, alive=lambda p: alive.get(p, False), clock=clock)
    ts.apply(ev("SessionStart", pid=100))
    ts.apply(ev("SessionStart", pid=200, sessao="s2", pasta="/x/sisdec"))
    ts.apply(ev("SessionEnd", pid=100, t=1000.0))
    alive[100] = False
    clock.t = 1004.0
    assert ts.tick() is True
    ts.apply(ev("SessionStart", pid=300, sessao="s3", pasta="/x/novo"))
    assert [(t["numero"], t["pasta"]) for t in ts.snapshot()] == [(1, "novo"), (2, "sisdec")]


def test_espera_e_fim(tmp_path):
    ts = _terms(tmp_path)
    assert ts.apply(ev("Stop"))["texto"] == "Terminal 1 (life-manager) terminou"
    assert ts.snapshot()[0]["estado"] == DONE
    alert = ts.apply(ev("Notification", tipo="idle_prompt"))
    assert alert["texto"] == "Terminal 1 (life-manager) está esperando você"
    assert ts.snapshot()[0]["estado"] == WAITING


def test_mcp_sem_verbo(tmp_path):
    ts = _terms(tmp_path)
    alert = ts.apply(ev("PermissionRequest", ferramenta="mcp__x__apagar", resumo="mcp__x__apagar"))
    assert (
        alert["texto"]
        == "Terminal 1 (life-manager) está pedindo permissão para usar mcp__x__apagar"
    )


def test_le_o_arquivo_incrementalmente_e_carrega_sem_avisos(tmp_path):
    path = tmp_path / "e.jsonl"
    path.write_text(json.dumps(ev("SessionStart")) + "\n" + json.dumps(ev("Stop")) + "\n")
    ts = Terminals(path, clock=Clock(), alive=lambda p: True)
    ts.load()
    assert ts.snapshot()[0]["estado"] == DONE
    with path.open("a") as f:
        f.write(json.dumps(ev("PermissionRequest", ferramenta="Bash", resumo="ls")) + "\n")
        f.write('{"evento": "UserPromptSub')  # linha ainda pela metade
    changed, alerts = ts.poll()
    assert changed and [a["tipo"] for a in alerts] == ["permissao"]
    with path.open("a") as f:
        f.write('mit", "pid": 100, "sessao": "s1", "t": 1000}\n')
    changed, alerts = ts.poll()
    assert changed and alerts == [] and ts.snapshot()[0]["estado"] == WORKING


def test_carga_descarta_processos_mortos(tmp_path):
    path = tmp_path / "e.jsonl"
    path.write_text(json.dumps(ev("SessionStart", pid=100)) + "\n")
    ts = Terminals(path, clock=Clock(), alive=lambda p: False)
    ts.load()
    assert ts.snapshot() == []


def test_sessao_sem_pid_sai_no_session_end(tmp_path):
    ts = _terms(tmp_path)
    ts.apply(ev("SessionStart", pid=None, sessao="s1"))
    ts.apply(ev("SessionEnd", pid=None, sessao="s1"))
    assert ts.snapshot() == []


def test_arquivo_grande_e_reduzido_na_subida(tmp_path, monkeypatch):
    import jarvis.terminals as mod

    monkeypatch.setattr(mod, "MAX_BYTES", 500)
    monkeypatch.setattr(mod, "KEEP_LINES", 3)
    path = tmp_path / "e.jsonl"
    path.write_text("".join(json.dumps(ev("PostToolUse", t=1000.0 + i)) + "\n" for i in range(50)))
    Terminals(path, clock=Clock(), alive=lambda p: True).load()
    assert len(path.read_text().splitlines()) == 3
    assert oct(path.stat().st_mode & 0o777) == "0o600"
