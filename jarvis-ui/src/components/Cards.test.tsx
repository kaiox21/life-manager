import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CardView } from "./Cards";

afterEach(cleanup);

describe("cartões", () => {
  it("agenda lista hora, título e detalhes", () => {
    render(
      <CardView
        card={{
          kind: "agenda",
          title: "Agenda · 09/10",
          omitted: 0,
          items: [{ hora: "14:00", titulo: "Dentista", data: "sexta 09/10/2026", pessoa: "Carlos" }],
        }}
      />,
    );
    expect(screen.getByRole("region", { name: "Agenda · 09/10" })).toBeTruthy();
    expect(screen.getByText("14:00")).toBeTruthy();
    expect(screen.getByText("Dentista")).toBeTruthy();
    expect(screen.getByText("sexta 09/10/2026 · Carlos")).toBeTruthy();
  });

  it("agenda vazia", () => {
    render(<CardView card={{ kind: "agenda", title: "Agenda", omitted: 0, items: [] }} />);
    expect(screen.getByText("Nada na agenda.")).toBeTruthy();
  });

  it("fatura mostra total e situação vindos do núcleo", () => {
    render(
      <CardView
        card={{
          kind: "fatura",
          title: "Fatura Nubank",
          total: "R$ 47,00",
          due: "08/11/2026",
          closing: "31/10/2026",
          status: "aberta",
          count: 1,
          items: [{ descricao: "almoço", valor: "R$ 47,00" }],
        }}
      />,
    );
    expect(screen.getAllByText("R$ 47,00").length).toBe(2);
    expect(screen.getByText("aberta")).toBeTruthy();
    expect(screen.getByText(/vence 08\/11\/2026/)).toBeTruthy();
  });

  it("gráfico usa o maior valor como 100%", () => {
    const { container } = render(
      <CardView
        card={{
          kind: "grafico",
          title: "Gastos",
          total: "R$ 90,00",
          series: [
            { label: "Mercado", value: 6000, display: "R$ 60,00", count: 2 },
            { label: "Lazer", value: 3000, display: "R$ 30,00", count: 1 },
          ],
        }}
      />,
    );
    const fills = container.querySelectorAll<HTMLElement>(".bars__fill");
    expect(fills[0].style.inlineSize).toBe("100%");
    expect(fills[1].style.inlineSize).toBe("50%");
  });

  it("texto com opções", () => {
    render(<CardView card={{ kind: "texto", title: "Atenção", text: "Qual cartão?", options: ["A", "B"] }} />);
    expect(screen.getByText("A")).toBeTruthy();
  });
});
