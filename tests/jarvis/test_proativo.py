"""Jarvis proativo: fechamento do dia, resposta sem o nome, avisos falados e silêncio."""

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from jarvis.agent import is_good_night, is_negative
from jarvis.mcp_client import ToolResult
from jarvis.wake import IDLE, WAIT, WakeService
from tests.fakes import StreamingScriptedLLM, call, reply
from tests.jarvis.test_agent import FakeCore
from tests.jarvis.test_voice import FakeTranscriber, FakeVad, brain
from tests.jarvis.test_wake import NOME, SIL, FakeGate, FakeSpotter, blocks

TZ = ZoneInfo("America/Sao_Paulo")
PAINEL = {
    "hoje": {"total": "R$ 63,50", "total_centavos": 6350, "lancamentos": 2},
    "mes": {"total": "R$ 1.240,00"},
    "agenda": {
        "hoje": [],
        "proximos": [{"titulo": "Aula", "hora": "19:00", "data": "quarta 14/10/2026"}],
    },
    "faturas": [],
}


class Speaker:
    def __init__(self):
        self.said = []

    def say(self, s):
        self.said.append(s)


def noite_brain(llm=None, core=None, **kw):
    b = brain(
        llm or StreamingScriptedLLM(), core or FakeCore({"painel": ToolResult(True, PAINEL)}), **kw
    )
    b.clock = lambda: datetime(2026, 10, 13, 22, tzinfo=TZ)
    b.speaker = Speaker()
    return b


async def ask(b, text, mode="texto"):
    got = []

    async def emit(ev):
        got.append(ev)

    await b.ask("r1", text, emit, mode=mode)
    return got


def test_so_a_frase_exata_e_boa_noite():
    assert is_good_night("Boa noite") and is_good_night("Jarvis, boa noite!")
    assert is_good_night("boa noite, Jarvis.") and is_good_night("Hey Jarvis, boa noite")
    assert not is_good_night("boa noite, quanto gastei hoje?")
    assert is_negative("Não.") and is_negative("não, obrigado") and is_negative("Já lancei tudo")
    assert not is_negative("não lancei o uber de 30")


async def test_boa_noite_fecha_o_dia_sem_o_modelo_e_nao_encerra():
    llm = StreamingScriptedLLM()
    b = noite_brain(llm)
    got = await ask(b, "Boa noite")
    assert [e.type for e in got] == ["token", "done"]
    assert got[-1].text == (
        "Boa noite, senhor. Hoje foram 2 gastos, R$ 63,50; no mês, R$ 1.240,00."
        " Amanhã o senhor tem Aula às 19h. O senhor teve algum gasto hoje que ainda não lançou?"
    )
    assert b.speaker.said[-1] == "O senhor teve algum gasto hoje que ainda não lançou?"
    assert b._core.calls == [("painel", {})]  # uma chamada, nenhuma linha em agent_runs
    got = await ask(b, "não")
    assert got[-1].text == "Perfeito, senhor. Boa noite."
    assert llm.calls == []  # nenhum token nas duas


async def test_gasto_esquecido_vai_ao_modelo_com_a_pergunta_no_historico():
    llm = StreamingScriptedLLM(
        call(
            "lancar_gasto", {"amount_cents": 3000, "description": "uber", "payment_method": "pix"}
        ),
        reply("Lancei R$ 30,00 de uber no Pix."),
    )
    b = noite_brain(llm)
    await ask(b, "Jarvis, boa noite")
    await ask(b, "30 de uber no pix")
    messages = llm.calls[0]["messages"]
    assert messages[-3:-1] == [
        {"role": "user", "content": "Jarvis, boa noite"},
        {"role": "assistant", "content": messages[-2]["content"]},
    ]
    assert messages[-2]["content"].endswith("ainda não lançou?")
    assert messages[-1] == {"role": "user", "content": "30 de uber no pix"}
    assert (
        "lancar_gasto",
        {"amount_cents": 3000, "description": "uber", "payment_method": "pix"},
    ) in b._core.calls


async def test_nao_fora_da_janela_vai_ao_modelo():
    llm = StreamingScriptedLLM(reply("Certo."))
    b = noite_brain(llm)
    await ask(b, "boa noite")
    b._answer_until = 0.0  # passaram os 2 minutos
    await ask(b, "não")
    assert len(llm.calls) == 1


async def test_nucleo_fora_nao_pergunta():
    class Down(FakeCore):
        async def call(self, name, args):
            raise ConnectionError("núcleo fora")

    b = noite_brain(core=Down())
    got = await ask(b, "boa noite")
    assert "indisponíveis" in got[-1].text and not b.wants_answer()


async def test_frase_maior_vai_ao_modelo():
    llm = StreamingScriptedLLM(reply("Hoje foram R$ 63,50."))
    b = noite_brain(llm)
    await ask(b, "boa noite, quanto gastei hoje?")
    assert len(llm.calls) == 1


async def test_resumo_e_lembrete_entram_no_historico_sem_virar_pergunta_do_painel():
    b = noite_brain()

    async def no_weather(lat, lon):
        return None

    b.fetch_weather = no_weather
    sent = []

    async def emit(ev):
        sent.append(ev)

    await b.briefing("w1", emit)
    await b.spending_reminder("p1", emit, "Senhor, nenhum gasto lançado hoje. Teve algum?")
    roles = [m["role"] for m in b._history]
    assert roles == ["user", "assistant", "user", "assistant"]  # alternância que a API pede
    await b.panel("r2", emit)
    assert sent[-1].data["perguntas"] == []
    got = await ask(b, "nada")
    assert got[-1].text == "Perfeito, senhor."


async def test_voz_nao_aprova_permissao():
    """ "permite" vai ao modelo, que não tem ferramenta de aprovar: o pedido fica aberto."""
    llm = StreamingScriptedLLM(reply("Só pelo botão, senhor."))
    b = noite_brain(llm)
    await ask(b, "Jarvis, permite", mode="voz")
    names = {t["function"]["name"] for t in llm.calls[0]["tools"]}
    assert not any("permiss" in n or "aprova" in n for n in names)


# --- a escuta espera a resposta sem o nome


async def test_boa_noite_pela_palavra_espera_a_resposta_sem_o_nome():
    t = FakeTranscriber("Jarvis, boa noite.")
    llm = StreamingScriptedLLM(reply("Lancei."))
    b = noite_brain(llm, transcriber=t, vad=FakeVad(True))
    emitted = []

    async def bc(ev):
        emitted.append(ev)

    svc = WakeService(b, FakeSpotter, FakeGate, bc, bc)
    svc.set_listening(True)
    svc.feed(blocks((NOME, 1), (SIL, 8)))
    for _ in range(50):
        await asyncio.sleep(0.01)
        if svc._listener.state == WAIT:
            break
    assert svc._listener.state == WAIT and b._waiting_request
    t.text = "Não."  # sem o nome
    result = await b.wake_turn("wake-2", np.zeros(16000, np.float32), bc)
    assert result == "ok" and emitted[-1].text == "Perfeito, senhor. Boa noite."
    assert llm.calls == []


async def test_lembrete_poe_a_escuta_esperando_a_resposta():
    b = noite_brain()

    async def bc(ev):
        pass

    svc = WakeService(b, FakeSpotter, FakeGate, bc, bc)
    assert not svc.expect_answer("p1")  # escuta desligada
    svc.set_listening(True)
    assert not svc.expect_answer("p1")  # sem pergunta aberta
    await b.spending_reminder("p1", bc, "Senhor, nenhum gasto lançado hoje. Teve algum?")
    assert svc._listener.state == IDLE and not svc.busy()
    assert svc.expect_answer("p1") and svc._listener.state == WAIT and svc.busy()


# --- serviço proativo: fila, silêncio, avisos e lembrete

from jarvis.proactive import REMINDER_TEXT, Proactive, terminal_speech  # noqa: E402
from jarvis.terminals import Terminals  # noqa: E402


class Clock:
    def __init__(self, h, m=0):
        self.now = datetime(2026, 10, 13, h, m, tzinfo=TZ)
        self.mono = 1000.0

    def advance(self, minutes):
        self.now += timedelta(minutes=minutes)
        self.mono += minutes * 60


class FakeBrain:
    def __init__(self, clock):
        self.clock = lambda: clock.now
        self.speaker = Speaker()
        self.busy = False
        self.reminders = []

    def wake_paused(self):
        return self.busy

    async def spending_reminder(self, rid, emit, text):
        self.reminders.append(text)


class FakeWake:
    def __init__(self):
        self.collecting = False
        self.expected = []

    def busy(self):
        return self.collecting

    def expect_answer(self, rid):
        self.expected.append(rid)
        return True


def service(tmp_path, h=14, m=0, core=None, **kw):
    clock = Clock(h, m)
    b = FakeBrain(clock)
    wake = FakeWake()

    async def bc(ev):
        pass

    p = Proactive(
        b,
        core or FakeCore(),
        bc,
        wake=lambda: wake,
        state_file=tmp_path / "proativo.json",
        monotonic=lambda: clock.mono,
        **kw,
    )
    return p, b, wake, clock


def notices_core(*avisos):
    return FakeCore({"avisos_recentes": ToolResult(True, list(avisos))})


def aviso(tipo, texto, hora="2026-10-13T14:00:30-03:00"):
    return {"tipo": tipo, "texto": texto, "hora": hora}


async def test_aviso_do_nucleo_falado_uma_vez_e_desde_avanca(tmp_path):
    core = notices_core(
        aviso("evento", "⏰ Aula: hoje às 19:00 — em 30 min."), aviso("noticias", "📰")
    )
    p, b, _, _ = service(tmp_path, core=core)
    await p.step()
    assert b.speaker.said == ["Aula: hoje às 19h, em 30 min."]  # o boletim não é falado
    assert core.calls[0] == ("avisos_recentes", {"desde": "2026-10-13T14:00:00-03:00"})
    await p.poll_notices()
    assert core.calls[-1][1]["desde"] == "2026-10-13T14:00:30-03:00"


async def test_espera_a_vez_e_descarta_depois_de_5_min(tmp_path):
    p, b, wake, clock = service(tmp_path)
    p.terminal({"tipo": "permissao", "numero": 2, "pasta": "life-manager", "ferramenta": "Bash"})
    b.busy = True  # falando ou atendendo um pedido
    await p.tick()
    wake.collecting, b.busy = True, False  # a escuta colhendo um pedido
    await p.tick()
    assert b.speaker.said == []
    wake.collecting = False
    await p.tick()
    assert b.speaker.said == [
        "Senhor, o Claude Code do life-manager está pedindo permissão para usar Bash."
    ]
    p.terminal({"tipo": "permissao", "numero": 3, "pasta": "sisdec", "ferramenta": "Edit"})
    b.busy = True
    clock.advance(6)
    b.busy = False
    await p.tick()
    assert len(b.speaker.said) == 1  # esperou demais: descartado


def test_terminal_so_permissao_e_trabalho_longo():
    base = {"numero": 1, "pasta": "life-manager"}
    assert terminal_speech(base | {"tipo": "terminou", "duracao": 20}) is None
    assert terminal_speech(base | {"tipo": "terminou", "duracao": 150}) == (
        "Senhor, o Claude Code do life-manager terminou."
    )
    assert terminal_speech(base | {"tipo": "espera"}) is None
    resumo = base | {"tipo": "permissao", "ferramenta": "Bash", "resumo": "TOKEN=x npm test"}
    assert "TOKEN" not in terminal_speech(resumo)  # o comando nunca é falado


async def test_um_aviso_por_terminal_por_minuto(tmp_path):
    p, b, _, clock = service(tmp_path)
    alert = {"tipo": "permissao", "numero": 2, "pasta": "x", "ferramenta": "Bash"}
    p.terminal(alert)
    p.terminal(alert)  # o mesmo pedido pelos dois caminhos
    await p.tick()
    await p.tick()
    assert len(b.speaker.said) == 1
    clock.advance(2)
    p.terminal(alert)
    await p.tick()
    assert len(b.speaker.said) == 2


def test_terminou_leva_a_duracao_do_trabalho(tmp_path):
    now = [100.0]
    t = Terminals(path=tmp_path / "eventos.jsonl", clock=lambda: now[0], alive=lambda pid: True)
    base = {"sessao": "s1", "pid": 1, "pasta": "/x/life-manager"}
    t.apply(base | {"evento": "SessionStart"})
    t.apply(base | {"evento": "UserPromptSubmit"})
    now[0] = 250.0
    alert = t.apply(base | {"evento": "Stop"})
    assert alert["tipo"] == "terminou" and alert["duracao"] == 150


async def test_madrugada_nada_e_falado(tmp_path):
    p, b, _, _ = service(tmp_path, h=1, core=notices_core(aviso("evento", "⏰ Voo: amanhã")))
    p.terminal({"tipo": "terminou", "numero": 1, "pasta": "x", "duracao": 600})
    await p.step()
    assert b.speaker.said == []


async def test_pausa_vale_depois_de_reiniciar_e_retomar(tmp_path):
    p, b, _, clock = service(tmp_path, core=notices_core(aviso("evento", "⏰ Aula")))
    assert p.pause(60) == {"status": "pausado", "ate": "15:00", "dia": "13/10"}
    p2, b2, _, _ = service(tmp_path, core=notices_core(aviso("evento", "⏰ Aula")))
    assert p2.status() == {"pausa_ate": "2026-10-13T15:00:00-03:00"}
    await p2.step()
    assert b2.speaker.said == []
    p2.resume()
    assert p2.status() == {"pausa_ate": None}


def test_pausar_ate_amanha_vai_ate_o_fim_do_silencio(tmp_path):
    p, *_ = service(tmp_path, h=22)
    assert p.pause_until_morning() == {"status": "pausado", "ate": "07:00", "dia": "14/10"}


async def test_lembrete_sem_gasto_uma_vez_por_dia(tmp_path):
    sem_gasto = {"hoje": {"lancamentos": 0}, "agenda": {}}
    core = FakeCore(
        {"painel": ToolResult(True, sem_gasto), "avisos_recentes": ToolResult(True, [])}
    )
    p, b, wake, clock = service(tmp_path, h=21, m=0, core=core)
    await p.step()
    assert b.speaker.said == []  # antes das 21:30
    clock.advance(31)
    p._last_poll = -1e9
    await p.step()
    assert " ".join(b.speaker.said) == REMINDER_TEXT and b.reminders == [REMINDER_TEXT]
    assert len(wake.expected) == 1  # a escuta espera a resposta sem o nome
    p2, b2, *_ = service(tmp_path, h=21, m=45, core=core)  # reiniciou
    await p2.step()
    assert b2.speaker.said == []


async def test_lembrete_com_gasto_ou_nucleo_fora_nao_pergunta(tmp_path):
    com_gasto = FakeCore({"painel": ToolResult(True, {"hoje": {"lancamentos": 1}})})
    p, b, *_ = service(tmp_path, h=21, m=40, core=com_gasto)
    await p.step()
    assert b.speaker.said == []

    class Down(FakeCore):
        async def call(self, name, args):
            raise ConnectionError

    p, b, *_ = service(tmp_path / "b", h=22, m=10, core=Down())
    await p.step()
    assert b.speaker.said == []


async def test_lembrete_ao_acordar_so_ate_o_silencio(tmp_path):
    core = FakeCore({"painel": ToolResult(True, {"hoje": {"lancamentos": 0}})})
    p, b, *_ = service(tmp_path, h=22, m=50, core=core)
    await p.step()
    assert " ".join(b.speaker.said) == REMINDER_TEXT
    p, b, *_ = service(tmp_path / "b", h=23, m=5, core=core)
    await p.step()
    assert b.speaker.said == []


async def test_silenciar_pela_ferramenta_e_pelo_botao(tmp_path):
    p, *_ = service(tmp_path)
    b = noite_brain()
    b._local.notices = p
    ok, out = await b._local.call("silenciar_avisos", {"acao": "pausar", "minutos": 60})
    assert ok and out["status"] == "pausado"
    await b.local_action("avisos_retomar")
    assert p.status() == {"pausa_ate": None}
    await b.local_action("avisos_pausar_1h")
    assert p.status()["pausa_ate"] is not None
    sent = []

    async def emit(ev):
        sent.append(ev)

    await b.panel("r1", emit)
    assert sent[-1].data["avisos"] == p.status()
