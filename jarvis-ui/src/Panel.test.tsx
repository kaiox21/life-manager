import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SAMPLE } from "./lib/panel.sample";
import { EMPTY_PANEL, applyPanel, type PanelState } from "./lib/panel";
import { Agenda, Log, Money } from "./Panel";

const ok = (data = SAMPLE): PanelState => applyPanel(EMPTY_PANEL, data, Date.parse("2026-10-09T14:00:00-03:00"));

afterEach(cleanup);

describe("colunas do painel", () => {
  it("mostra só números vindos do núcleo", () => {
    render(<Money panel={ok()} />);
    expect(screen.getAllByText("R$ 77,90")).toHaveLength(2); // total do mês e fatura
    expect(screen.getByText("R$ 47,90")).toBeTruthy();
    expect(screen.getByText(/fecha 31\/10 · vence 08\/11/)).toBeTruthy();
  });

  it("dia livre e sem cartão de crédito", () => {
    const data = { ...SAMPLE, agenda: { hoje: [], proximos: [] }, faturas: [] };
    render(
      <>
        <Agenda panel={ok(data)} />
        <Money panel={ok(data)} />
      </>,
    );
    expect(screen.getByText("Dia livre.")).toBeTruthy();
    expect(screen.getByText("Nenhum cartão de crédito.")).toBeTruthy();
  });

  it("lista longa no registro e perguntas da sessão", () => {
    const registro = Array.from({ length: 10 }, (_, i) => ({
      tipo: "gasto" as const,
      quando: `2026-10-09T1${i}:00:00-03:00`,
      texto: `gasto ${i}`,
      origem: i % 2 ? ("whatsapp" as const) : ("mac" as const),
    }));
    render(<Log panel={ok({ ...SAMPLE, registro })} />);
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
    render(<Money panel={{ ...EMPTY_PANEL, error: "cérebro indisponível" }} />);
    expect(screen.getByRole("status").textContent).toBe("cérebro indisponível");
    expect(screen.queryByText("carregando…")).toBeNull();
  });
});
