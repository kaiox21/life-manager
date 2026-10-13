"""Modo estudo: Foco por atalhos, playlist, avisos retidos, blocos com pausa e o relógio."""

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from jarvis.local_tools import Completed
from jarvis.proactive import Proactive
from jarvis.spotify import SpotifyError
from jarvis.study import END_REPLY, StudyMode
from tests.fakes import StreamingScriptedLLM, call, reply
from tests.jarvis.test_agent import FakeCore
from tests.jarvis.test_proativo import Speaker, ask, noite_brain

TZ = ZoneInfo("America/Sao_Paulo")


class Clock:
    def __init__(self, h=20, m=0):
        self.now = datetime(2026, 10, 13, h, m, tzinfo=TZ)
        self.mono = 1000.0

    def advance(self, minutes=0, seconds=0):
        self.now += timedelta(minutes=minutes, seconds=seconds)
        self.mono += minutes * 60 + seconds


class Shortcuts:
    """`shortcuts list` e `shortcuts run` falsos: quais existem, quais travam ou falham."""

    def __init__(self, names=("Jarvis Foco", "Jarvis Foco Fim"), hang=(), fail=()):
        self.names, self.hang, self.fail = list(names), set(hang), set(fail)
        self.calls = []

    async def __call__(self, argv, stdin):
        self.calls.append(argv)
        if argv[:2] == ["shortcuts", "list"]:
            return Completed(0, "\n".join(self.names) + "\n", "")
        name = argv[2]
        if name in self.hang:
            await asyncio.sleep(3600)
        return Completed(1 if name in self.fail else 0, "", "")

    @property
    def runs(self):
        return [a[2] for a in self.calls if a[:2] == ["shortcuts", "run"]]


class FakeSpotify:
    def __init__(self, playlists=("Estudo 📚 foco",), login=True):
        self.playlists, self.login = list(playlists), login
        self.played = []

    async def search(self, tipo, query):
        if not self.login:
            raise SpotifyError("login", login=True)
        assert tipo == "minha_playlist"
        hit = [p for p in self.playlists if query.lower() in p.lower()]
        return {"nome": hit[0], "contexto": "spotify:playlist:1"} if hit else None

    async def play(self, found):
        self.played.append(found["nome"])


class FakeWake:
    def __init__(self):
        self.collecting = False
        self.expected = []

    def busy(self):
        return self.collecting

    def expect_answer(self, rid):
        self.expected.append(rid)
        return True


class Brain:
    """Só o que o modo usa: relógio, falas fixas e a pergunta com as duas ações."""

    def __init__(self, clock):
        self.clock = lambda: clock.now
        self.speaker = Speaker()
        self.busy = False
        self.said = []
        self.prompts = []

    def wake_paused(self):
        return self.busy

    async def announce(self, rid, emit, said, text):
        self.said.append(text)

    async def study_prompt(self, rid, emit, text, *, yes_reply, on_yes, no_reply, on_no):
        self.prompts.append({"text": text, "yes": on_yes, "no": on_no, "yes_reply": yes_reply})


def build(tmp_path, h=20, m=0, shortcuts=None, spotify="ok", **kw):
    clock = Clock(h, m)
    brain = Brain(clock)
    wake = FakeWake()

    async def bc(ev):
        pass

    proactive = Proactive(
        brain,
        FakeCore(),
        bc,
        wake=lambda: wake,
        state_file=tmp_path / "proativo.json",
        monotonic=lambda: clock.mono,
    )
    sc = shortcuts or Shortcuts()
    sp = FakeSpotify() if spotify == "ok" else spotify
    study = StudyMode(brain=brain, proactive=proactive, broadcast_ui=bc, run=sc, spotify=sp, **kw)
    proactive.study = study
    return study, brain, proactive, sc, clock, wake


async def test_iniciar_liga_foco_playlist_e_silencio(tmp_path):
    study, brain, proactive, sc, clock, _ = build(tmp_path)
    out = await study.start(50, 10)
    assert out["status"] == "iniciado" and out["ate"] == "20:50"
    assert out["foco"] == "ligado" and out["musica"] == "tocando Estudo 📚 foco"
    assert sc.calls[0] == ["shortcuts", "list"] and sc.runs == ["Jarvis Foco"]
    assert study.status() == {
        "fase": "bloco",
        "ate": "2026-10-13T20:50:00-03:00",
        "minutos": 50,
        "pausa": 10,
    }
    # avisos retidos: nada é falado nem guardado, e o WhatsApp os tem
    proactive.terminal({"tipo": "permissao", "numero": 1, "pasta": "x", "ferramenta": "Bash"})
    await proactive.tick()
    assert brain.speaker.said == []
    assert study.start_text(out) == (
        "Modo estudo até as 20h50, senhor. Foco ligado. Playlist de estudo tocando."
        " Avisos em silêncio."
    )


async def test_sem_atalhos_sem_spotify_o_modo_comeca_assim_mesmo(tmp_path):
    sc = Shortcuts(names=["Outro atalho"])
    study, _, _, _, _, _ = build(tmp_path, shortcuts=sc, spotify=FakeSpotify(login=False))
    out = await study.start()
    assert out["foco"] == "os atalhos do Foco não existem"
    assert out["musica"] == "o Spotify não está autorizado"
    assert sc.runs == []  # nunca roda um atalho que não está na lista (ele trava)
    assert study.status()["fase"] == "bloco" and out["minutos"] == 50
    assert "Sem o Foco: os atalhos do Foco não existem." in study.start_text(out)
    await study.stop()
    assert sc.runs == []  # o Foco não ligou: o desligar não roda


async def test_atalho_que_trava_ou_falha_nao_segura_o_modo(tmp_path):
    import jarvis.study as mod

    mod.SHORTCUT_TIMEOUT = 0.05
    try:
        study, *_ = build(tmp_path, shortcuts=Shortcuts(hang={"Jarvis Foco"}))
        assert (await study.start())["foco"] == "o atalho do Foco não terminou"
        study2, *_ = build(tmp_path / "b", shortcuts=Shortcuts(fail={"Jarvis Foco"}))
        assert (await study2.start())["foco"] == "o atalho do Foco falhou"
    finally:
        mod.SHORTCUT_TIMEOUT = 10.0


async def test_playlist_nao_encontrada_e_spotify_nao_configurado(tmp_path):
    study, *_ = build(tmp_path, spotify=FakeSpotify(playlists=["Festa"]))
    assert (await study.start())["musica"] == "não encontrei a playlist 'estudo'"
    study2, *_ = build(tmp_path / "b", spotify=None)
    assert (await study2.start())["musica"] == "o Spotify não está configurado"


async def test_fim_do_bloco_pergunta_pausa_sim_e_depois_novo_bloco(tmp_path):
    study, brain, proactive, sc, clock, wake = build(tmp_path)
    await study.start(50, 10)
    clock.advance(minutes=49)
    await study.tick()
    assert brain.prompts == []
    clock.advance(minutes=1)
    brain.busy = True  # falando: a pergunta espera
    await study.tick()
    assert brain.prompts == []
    brain.busy = False
    await study.tick()
    assert (
        brain.prompts[-1]["text"]
        == "Senhor, acabaram os 50 minutos de estudo. Pausa de 10 minutos?"
    )
    assert brain.prompts[-1]["yes_reply"] == "Pausa de 10 minutos, senhor."
    assert study.status()["fase"] == "pergunta" and wake.expected  # escuta espera o "sim"
    await brain.prompts[-1]["yes"]()
    assert study.status()["fase"] == "pausa" and study.status()["ate"].endswith("T21:00:00-03:00")
    clock.advance(minutes=10)
    await study.tick()
    assert brain.prompts[-1]["text"] == "Senhor, a pausa acabou. Mais 50 minutos?"
    await brain.prompts[-1]["yes"]()
    st = study.status()
    assert st["fase"] == "bloco" and st["ate"].endswith("T21:50:00-03:00")
    assert sc.runs == ["Jarvis Foco"]  # o Foco não é religado nem desligado entre as fases


async def test_nao_encerra_e_desliga_o_foco(tmp_path):
    study, brain, proactive, sc, clock, _ = build(tmp_path)
    await study.start(25, 5)
    clock.advance(minutes=25)
    await study.tick()
    await brain.prompts[-1]["no"]()
    assert study.status() is None and sc.runs == ["Jarvis Foco", "Jarvis Foco Fim"]
    # os avisos voltam
    proactive.terminal({"tipo": "permissao", "numero": 1, "pasta": "x", "ferramenta": "Bash"})
    await proactive.tick()
    assert len(brain.speaker.said) == 1


async def test_sem_resposta_em_2_min_encerra_em_silencio(tmp_path):
    study, brain, _, sc, clock, _ = build(tmp_path)
    await study.start(50, 10)
    clock.advance(minutes=50)
    await study.tick()
    clock.advance(minutes=2, seconds=1)
    await study.tick()
    assert study.status() is None and sc.runs[-1] == "Jarvis Foco Fim"
    assert len(brain.prompts) == 1 and brain.said == []


async def test_pausa_zero_pergunta_mais_minutos_direto(tmp_path):
    study, brain, _, _, clock, _ = build(tmp_path)
    await study.start(30, 0)
    clock.advance(minutes=30)
    await study.tick()
    assert brain.prompts[-1]["text"] == "Senhor, acabaram os 30 minutos de estudo. Mais 30 minutos?"
    await brain.prompts[-1]["yes"]()
    assert study.status()["fase"] == "bloco"


async def test_mac_dormiu_alem_do_fim_encerra_sem_perguntar(tmp_path):
    study, brain, _, sc, clock, _ = build(tmp_path)
    await study.start(50, 10)
    clock.advance(minutes=65)  # acordou 15 min depois do fim
    await study.tick()
    assert study.status() is None and brain.prompts == [] and sc.runs[-1] == "Jarvis Foco Fim"
    study2, brain2, _, _, clock2, _ = build(tmp_path / "b")
    await study2.start(50, 10)
    clock2.advance(minutes=55)  # acordou 5 min depois: ainda pergunta
    await study2.tick()
    assert brain2.prompts


async def test_reinicio_retoma_o_bloco_ou_encerra_depois_da_hora(tmp_path):
    study, _, _, sc, clock, _ = build(tmp_path)
    await study.start(50, 10)
    # o cérebro reinicia 20 min depois: o mesmo arquivo, outro processo
    study2, brain2, proactive2, sc2, clock2, _ = build(tmp_path, h=20, m=20)
    await study2.tick()
    assert study2.status()["fase"] == "bloco" and "faltam 30 min" in study2.status_text()
    proactive2.terminal({"tipo": "terminou", "numero": 1, "pasta": "x", "duracao": 600})
    await proactive2.tick()
    assert brain2.speaker.said == []  # retido de novo
    assert sc2.runs == []
    # reinício depois da hora: encerra e desliga o Foco
    study3, brain3, _, sc3, _, _ = build(tmp_path, h=21, m=30)
    await study3.tick()
    assert study3.status() is None and sc3.runs == ["Jarvis Foco Fim"] and brain3.prompts == []


async def test_reinicio_com_pergunta_pendente_encerra(tmp_path):
    study, brain, _, _, clock, _ = build(tmp_path)
    await study.start(50, 10)
    clock.advance(minutes=50)
    await study.tick()
    assert study.status()["fase"] == "pergunta"
    study2, _, _, sc2, _, _ = build(tmp_path, h=20, m=51)
    await study2.tick()
    assert study2.status() is None and sc2.runs == ["Jarvis Foco Fim"]


async def test_parar_e_status(tmp_path):
    study, brain, _, sc, clock, _ = build(tmp_path)
    assert (await study.stop())["status"] == "sem_modo"
    assert study.status_text() == "Não há modo estudo ativo."
    await study.start(50, 10)
    clock.advance(minutes=13)
    assert study.status_text() == "No bloco de estudo, faltam 37 min (até as 20:50)."
    assert (await study.stop()) == {"status": "encerrado", "foco": "desligado"}
    assert study.status() is None


async def test_segundo_pedido_substitui_sem_religar_o_foco(tmp_path):
    study, _, _, sc, clock, _ = build(tmp_path)
    await study.start(50, 10)
    clock.advance(minutes=10)
    out = await study.start(25, 5)
    assert out["ate"] == "20:35" and sc.runs == ["Jarvis Foco"]


async def test_botoes_falam_texto_fixo(tmp_path):
    study, brain, *_ = build(tmp_path)
    await study.start_by_button()
    assert brain.said == [
        "Modo estudo até as 20h50, senhor. Foco ligado. Playlist de estudo tocando."
        " Avisos em silêncio."
    ]
    await study.stop_by_button()
    assert brain.said[-1] == END_REPLY
    await study.stop_by_button()  # sem modo: nada a dizer
    assert len(brain.said) == 2


# --- o cérebro de verdade: "sim" e "não" sem o modelo, o resto vai ao modelo


class Study:
    def __init__(self):
        self.log = []

    async def on_yes(self):
        self.log.append("sim")

    async def on_no(self):
        self.log.append("não")


async def test_resposta_sim_executa_a_acao_sem_o_modelo():
    llm = StreamingScriptedLLM()
    b = noite_brain(llm)
    st = Study()
    got = []

    async def emit(ev):
        got.append(ev)

    await b.study_prompt(
        "e1",
        emit,
        "Senhor, acabaram os 50 minutos de estudo. Pausa de 10 minutos?",
        yes_reply="Pausa de 10 minutos, senhor.",
        on_yes=st.on_yes,
        no_reply=END_REPLY,
        on_no=st.on_no,
    )
    assert got[-1].text.endswith("Pausa de 10 minutos?") and b.wants_answer()
    assert b.speaker.said[-1] == "Pausa de 10 minutos?"
    out = await ask(b, "Ok")
    assert out[-1].text == "Pausa de 10 minutos, senhor." and st.log == ["sim"]
    assert llm.calls == []
    roles = [m["role"] for m in b._history]
    assert roles == ["user", "assistant", "user", "assistant"]


async def test_resposta_nao_e_pedido_diferente():
    llm = StreamingScriptedLLM(
        call("modo_estudo", {"acao": "iniciar", "minutos": 25}), reply("Mais 25 minutos.")
    )
    b = noite_brain(llm)
    st = Study()

    async def emit(ev):
        pass

    kw = dict(
        yes_reply="Mais 50 minutos, senhor.", on_yes=st.on_yes, no_reply=END_REPLY, on_no=st.on_no
    )
    await b.study_prompt("e1", emit, "Senhor, a pausa acabou. Mais 50 minutos?", **kw)
    out = await ask(b, "não, obrigado")
    assert out[-1].text == END_REPLY and st.log == ["não"] and llm.calls == []
    await b.study_prompt("e2", emit, "Senhor, a pausa acabou. Mais 50 minutos?", **kw)
    await ask(b, "mais 25 minutos")
    assert len(llm.calls) == 2 and st.log == ["não"]  # foi ao modelo, que chamou a ferramenta
    assert llm.calls[0]["messages"][-2]["content"].endswith("Mais 50 minutos?")


async def test_sim_fora_de_pergunta_vai_ao_modelo_e_boa_noite_nao_aceita_sim():
    llm = StreamingScriptedLLM(reply("Sim?"), reply("Certo."))
    b = noite_brain(llm)
    await ask(b, "sim")
    assert len(llm.calls) == 1
    await ask(b, "boa noite")
    await ask(b, "sim")  # o fechamento só tem a negativa fixa
    assert len(llm.calls) == 2


async def test_ferramenta_modo_estudo_valida_e_chama_o_modo(tmp_path):
    study, *_ = build(tmp_path)
    b = noite_brain()
    b._local.study = study
    ok, out = await b._local.call("modo_estudo", {"acao": "iniciar", "minutos": 600})
    assert not ok and "minutos" in out
    ok, out = await b._local.call("modo_estudo", {"acao": "iniciar", "minutos": 25, "pausa": 5})
    assert ok and out["status"] == "iniciado" and out["minutos"] == 25 and out["pausa"] == 5
    ok, out = await b._local.call("modo_estudo", {"acao": "status"})
    assert ok and out["status"]["fase"] == "bloco" and "faltam 25 min" in out["texto"]
    ok, out = await b._local.call("modo_estudo", {"acao": "parar"})
    assert ok and out["status"] == "encerrado"
    sent = []

    async def emit(ev):
        sent.append(ev)

    await b.panel("r1", emit)
    assert sent[-1].data["estudo"] is None
    await b.local_action("estudo_iniciar")
    await b.panel("r2", emit)
    assert sent[-1].data["estudo"]["fase"] == "bloco"
    await b.local_action("estudo_parar")
    assert study.status() is None
