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


# --- terminais compartilhados (tmux)

from jarvis.terminals import FREE, RUNNING  # noqa: E402
from jarvis.tmux import Pane  # noqa: E402


def pane(
    sessao="$1",
    painel="%1",
    comando="zsh",
    clientes=1,
    origem="terminal",
    aba=False,
    pasta="/x/life-manager",
):
    return Pane(sessao, painel, 500, pasta, comando, clientes, 900.0, origem, aba)


def test_sessao_do_tmux_vira_terminal_shell_na_mesma_numeracao(tmp_path):
    ts = _terms(tmp_path)
    ts.apply(ev("SessionStart", pid=100))  # Claude Code de fora (VS Code): Terminal 1
    changed, _ = ts.sync_tmux([pane()])
    assert changed
    t = ts.by_key("tmux:$1")
    assert (t.numero, t.tipo, t.estado, t.pasta, t.janela, t.origem) == (
        2,
        "shell",
        FREE,
        "life-manager",
        True,
        "terminal",
    )
    assert not t.ocupado
    ts.sync_tmux([pane(comando="npm")])
    assert t.estado == RUNNING and t.ocupado
    ts.sync_tmux([])
    assert ts.by_key("tmux:$1") is None and [x["numero"] for x in ts.snapshot()] == [1]


def test_claude_dentro_do_terminal_pelo_painel(tmp_path):
    ts = _terms(tmp_path)
    ts.sync_tmux([pane()])
    tm = {"painel": "%1", "socket": "jarvis"}
    ts.apply(ev("SessionStart", pid=300, **tm))
    t = ts.by_key("tmux:$1")
    assert (t.tipo, t.estado, t.pid) == ("claude", WAITING, 300)
    assert len(ts.snapshot()) == 1  # não cria um terminal pelo pid
    assert ts.claude_count() == 1
    # pedido de permissão num terminal compartilhado: o aviso vem do hook síncrono, não daqui
    assert ts.apply(ev("PermissionRequest", pid=300, ferramenta="Bash", resumo="ls", **tm)) is None
    assert t.estado == PERMISSION and t.ocupado
    ts.apply(ev("SessionEnd", pid=300, **tm))
    assert (t.tipo, t.estado, t.pid) == ("shell", FREE, None)
    assert ts.claude_count() == 0


def test_claude_sem_eventos_conta_como_ocupado(tmp_path):
    ts = _terms(tmp_path)
    ts.sync_tmux([pane(comando="2.1.296")])
    t = ts.by_key("tmux:$1")
    assert t.tipo == "shell" and t.estado == RUNNING and t.ocupado


def test_evento_de_painel_ainda_nao_listado_espera_a_leitura(tmp_path):
    ts = _terms(tmp_path)
    tm = {"painel": "%9", "socket": "jarvis"}
    assert ts.apply(ev("SessionStart", pid=301, **tm)) is None
    assert ts.snapshot() == []
    _, alerts = ts.sync_tmux([pane(sessao="$4", painel="%9")])
    assert ts.by_key("tmux:$4").tipo == "claude"
    ts.apply(ev("Notification", pid=301, tipo="idle_prompt", **tm))
    assert ts.by_key("tmux:$4").estado == WAITING


def test_evento_de_outro_socket_vai_pelo_pid(tmp_path):
    ts = _terms(tmp_path)
    ts.sync_tmux([pane()])
    ts.apply(ev("SessionStart", pid=302, painel="%1", socket="pessoal"))
    assert len(ts.snapshot()) == 2  # o tmux pessoal do Kaio não é terminal compartilhado


def test_janela_desconta_as_abas_do_jarvis(tmp_path):
    ts = _terms(tmp_path)
    ts.sync_tmux([pane(clientes=1, aba=True)], own_clients={"$1": 1})
    t = ts.by_key("tmux:$1")
    assert t.aba and not t.janela
    ts.sync_tmux([pane(clientes=2, aba=True)], own_clients={"$1": 1})
    assert t.janela


def test_terminal_do_tmux_nao_expira_por_pid(tmp_path):
    clock = Clock()
    ts = _terms(tmp_path, alive=lambda pid: False, clock=clock)
    ts.sync_tmux([pane()])
    ts.apply(ev("SessionStart", pid=303, painel="%1", socket="jarvis"))
    clock.t += 13 * 3600
    ts.tick(force_liveness=True)
    t = ts.by_key("tmux:$1")
    assert t is not None and t.tipo == "shell"  # o claude morreu; o terminal fica
