import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SAMPLE } from "./lib/panel.sample";
import { EMPTY_PANEL, applyPanel, nextEvent, type PanelState } from "./lib/panel";
import { Agenda, ClockCard, Conversation, Log, MacCard, Month, Projects, Weather } from "./Panel";
import type { PanelData } from "./lib/types";

const ok = (data: PanelData = SAMPLE): PanelState =>
  applyPanel(EMPTY_PANEL, data, Date.parse("2026-10-09T14:00:00-03:00"));
const at = (hhmm: string) => new Date(`2026-10-09T${hhmm}:00-03:00`);

afterEach(cleanup);

describe("cartões do painel HUD", () => {
  it("mês: só números vindos do núcleo, com o anel da fatura que fecha primeiro", () => {
    const faturas = [{ ...SAMPLE.faturas[0], dias_para_fechar: 2, fracao_ciclo: 0.93 }];
    render(<Month panel={ok({ ...SAMPLE, faturas })} />);
    expect(screen.getAllByText("R$ 77,90")).toHaveLength(2); // fatura e total do mês
    expect(screen.getByText("R$ 47,90")).toBeTruthy();
    expect(screen.getByText(/fecha 31\/10 · vence 08\/11/)).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByRole("img", { name: "Fatura Nubank: R$ 77,90" })).toBeTruthy();
  });

  it("dia livre e sem cartão de crédito", () => {
    const data = { ...SAMPLE, agenda: { hoje: [], proximos: [] }, faturas: [] };
    render(
      <>
        <Agenda panel={ok(data)} />
        <Month panel={ok(data)} />
      </>,
    );
    expect(screen.getByText("Dia livre.")).toBeTruthy();
    expect(screen.getByText("Nenhum cartão de crédito.")).toBeTruthy();
  });

  it("agenda: o próximo compromisso fica aceso e os que passaram, apagados", () => {
    const hoje = [
      { id: "1", titulo: "Dentista", tipo: "c", data: "sexta 09/10/2026", hora: "09:00" },
      { id: "2", titulo: "Reunião", tipo: "c", data: "sexta 09/10/2026", hora: "14:00" },
      { id: "3", titulo: "Aula", tipo: "c", data: "sexta 09/10/2026", hora: "19:50" },
    ];
    const { container } = render(<Agenda panel={ok({ ...SAMPLE, agenda: { hoje, proximos: [] } })} now={at("13:00")} />);
    expect(container.querySelector(".hud-timeline__item--past")?.textContent).toMatch(/Dentista/);
    expect(container.querySelector(".hud-timeline__item--next")?.textContent).toMatch(/Reunião/);
    expect(nextEvent(hoje, at("20:00"))).toBeNull();
  });

  it("relógio mostra o próximo compromisso", () => {
    render(<ClockCard now={at("14:30")} panel={ok()} />);
    expect(screen.getByText("Dentista")).toBeTruthy();
    expect(screen.getByRole("img", { name: "9 de outubro" })).toBeTruthy();
  });

  it("registro e perguntas da sessão na aba Registro", () => {
    const registro = Array.from({ length: 10 }, (_, i) => ({
      tipo: "gasto" as const,
      quando: `2026-10-09T1${i}:00:00-03:00`,
      texto: `gasto ${i}`,
      origem: i % 2 ? ("whatsapp" as const) : ("mac" as const),
    }));
    render(<Conversation panel={ok({ ...SAMPLE, registro })} onConfirm={() => {}} />);
    expect(screen.queryByText("gasto 0")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Registro" }));
    expect(screen.getAllByText(/^gasto \d$/)).toHaveLength(10);
    expect(screen.getAllByText("WhatsApp")).toHaveLength(5);
    expect(screen.getByText("quanto gastei?")).toBeTruthy();
  });

  it("núcleo fora: avisa e esmaece os dados antigos", () => {
    const down = applyPanel(ok(), { erro: "núcleo indisponível" }, Date.now());
    const { container } = render(<Agenda panel={down} />);
    expect(screen.getByRole("status").textContent).toMatch(/núcleo indisponível · dados de \d\d:\d\d/);
    expect(container.querySelector(".painel__stale")).toBeTruthy();
  });

  it("cérebro fora sem dados: só o aviso", () => {
    render(<Month panel={{ ...EMPTY_PANEL, error: "cérebro indisponível" }} />);
    expect(screen.getByRole("status").textContent).toBe("cérebro indisponível");
    expect(screen.queryByText("carregando…")).toBeNull();
  });

  it("clima, Mac e registro sozinhos", () => {
    const data = {
      ...SAMPLE,
      clima: { agora: 27.4, max: 34.1, min: 21.9, chuva: 0, cidade: "Brasília" },
      mac: { memoria_livre: 37, swap_gb: 0.8, bateria: { pct: 84, carregando: true } },
    };
    render(
      <>
        <Weather panel={ok(data)} />
        <MacCard panel={ok(data)} />
        <Log panel={ok(data)} />
      </>,
    );
    expect(screen.getByText("27°")).toBeTruthy();
    expect(screen.getByText("máx 34° · mín 22°")).toBeTruthy();
    expect(screen.getByRole("img", { name: "Memória livre: 37%" })).toBeTruthy();
    expect(screen.getByText("0,8G")).toBeTruthy();
    expect(screen.getByText("CARREGANDO")).toBeTruthy();
    expect(screen.getByText("uber · R$ 30,00 · Nubank")).toBeTruthy();
  });

  it("sem internet ou sem dados do Mac: o cartão diz indisponível", () => {
    render(
      <>
        <Weather panel={ok({ ...SAMPLE, clima: null })} />
        <MacCard panel={ok({ ...SAMPLE, mac: null })} />
      </>,
    );
    expect(screen.getByText("Clima indisponível.")).toBeTruthy();
    expect(screen.getByText("Dados do Mac indisponíveis.")).toBeTruthy();
  });

  it("projeto no lançador abre um terminal na pasta dele", () => {
    const onOpen = vi.fn();
    const projetos = [{ nome: "life-manager", caminho: "/Users/k/Projetos pessoais/life-manager" }];
    render(<Projects panel={ok({ ...SAMPLE, projetos })} onOpen={onOpen} />);
    fireEvent.click(screen.getByRole("button", { name: /life-manager/ }));
    expect(onOpen).toHaveBeenCalledWith("/Users/k/Projetos pessoais/life-manager");
  });
});
