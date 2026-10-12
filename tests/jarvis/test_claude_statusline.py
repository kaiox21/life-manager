import io
import json

from jarvis.hooks import claude_statusline as sl
from jarvis.hooks.install import add_statusline, remove_statusline
from jarvis.panel_extras import claude_limits

PAYLOAD = {
    "session_id": "abc",
    "model": {"display_name": "Opus"},
    "workspace": {"current_dir": "/Users/k/Projetos pessoais/life-manager"},
    "context_window": {"used_percentage": 8.4},
    "rate_limits": {
        "five_hour": {"used_percentage": 23.5, "resets_at": 2_000_000_000},
        "seven_day": {"used_percentage": 41.2, "resets_at": 2_000_500_000},
    },
}


def test_linha_da_barra():
    assert sl.line(PAYLOAD) == "Opus · 5h 24% · semana 41% · contexto 8%"
    assert sl.line({"context_window": {"used_percentage": 3}}) == "contexto 3%"  # plano sem limites


def test_grava_os_limites_e_o_contexto_da_sessao(tmp_path, capsys):
    out = tmp_path / "claude_limits.json"
    sl.main(io.StringIO(json.dumps(PAYLOAD)), str(out), now=100.0)
    data = json.loads(out.read_text())
    assert data["cinco_horas"] == {"pct": 23.5, "resets_at": 2_000_000_000}
    assert data["semana"]["pct"] == 41.2
    assert data["sessoes"]["abc"] == {"contexto": 8.4, "pasta": "life-manager", "em": 100.0}
    assert "5h 24%" in capsys.readouterr().out
    # atualização sem as janelas (antes da 1ª resposta): as anteriores ficam
    sl.main(
        io.StringIO(json.dumps({"session_id": "xyz", "context_window": {"used_percentage": 1}})),
        str(out),
        now=200.0,
    )
    data = json.loads(out.read_text())
    assert data["cinco_horas"]["pct"] == 23.5 and set(data["sessoes"]) == {"abc", "xyz"}


def test_json_ruim_nao_quebra(tmp_path, capsys):
    sl.main(io.StringIO("isso não é json"), str(tmp_path / "x.json"))
    assert capsys.readouterr().out == ""


def test_painel_le_e_esconde_janela_que_ja_zerou(tmp_path):
    f = tmp_path / "claude_limits.json"
    f.write_text(
        json.dumps(
            {
                "cinco_horas": {"pct": 90, "resets_at": 1000},
                "semana": {"pct": 41.2, "resets_at": 5000},
                "atualizado": 900,
                "sessoes": {"abc": {"contexto": 8.4}},
            }
        )
    )
    got = claude_limits(f, now=2000)
    assert got["cinco_horas"] is None and got["semana"]["pct"] == 41.2
    assert got["sessoes"]["abc"]["contexto"] == 8.4
    assert claude_limits(tmp_path / "nao-existe.json") is None


def test_instalador_nao_toma_a_barra_de_outro():
    mine = add_statusline({}, "/h/claude_statusline.py")
    assert "claude_statusline.py" in mine["statusLine"]["command"]
    other = {"statusLine": {"type": "command", "command": "~/minha-barra.sh"}}
    assert add_statusline(dict(other), "/h/claude_statusline.py") == other
    assert "statusLine" not in remove_statusline(mine)
    assert remove_statusline(dict(other)) == other
