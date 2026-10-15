import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CardView, CopyContext } from "./Cards";

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

describe("cartão de fontes", () => {
  it("mostra título e site de cada fonte", () => {
    render(
      <CardView
        card={{
          kind: "fontes",
          title: "Fontes",
          items: [
            { title: "Dólar fecha em alta", url: "https://www.g1.globo.com/economia/x" },
            { title: "Cotação do dia", url: "https://valor.globo.com/y" },
          ],
        }}
      />,
    );
    expect(screen.getByRole("link", { name: /Dólar fecha em alta/ }).getAttribute("href")).toBe(
      "https://www.g1.globo.com/economia/x",
    );
    expect(screen.getByText("g1.globo.com")).toBeTruthy();
  });

  it("rascunho mostra destinatário, assunto, texto inteiro e o Copiar manda o texto", () => {
    const copied: string[] = [];
    render(
      <CopyContext.Provider value={(t) => copied.push(t)}>
        <CardView
          card={{
            kind: "rascunho",
            title: "Rascunho · e-mail para o professor",
            to: "professor de redes",
            subject: "Segunda chamada",
            text: "Prezado professor,\n\nEstive doente.\n\nKaio",
            file: "~/Library/Application Support/Jarvis/rascunhos/x.md",
          }}
        />
      </CopyContext.Provider>,
    );
    expect(screen.getByRole("region", { name: "Rascunho · e-mail para o professor" })).toBeTruthy();
    expect(screen.getByText("Para: professor de redes")).toBeTruthy();
    expect(screen.getByText("Assunto: Segunda chamada")).toBeTruthy();
    expect(screen.getByText(/Estive doente\./)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Copiar" }));
    expect(copied).toEqual(["Prezado professor,\n\nEstive doente.\n\nKaio"]);
  });

  it("rascunho sem provedor: o Copiar não quebra", () => {
    render(<CardView card={{ kind: "rascunho", title: "Rascunho · texto", text: "oi" }} />);
    fireEvent.click(screen.getByRole("button", { name: "Copiar" }));
    expect(screen.getByText("oi")).toBeTruthy();
  });
});
