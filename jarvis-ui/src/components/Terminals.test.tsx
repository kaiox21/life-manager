import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { TerminalInfo } from "../lib/types";
import { CardView, TerminalList } from "./Cards";

afterEach(cleanup);

const t = (numero: number, estado: TerminalInfo["estado"], resumo = ""): TerminalInfo => ({
  numero,
  pasta: numero === 1 ? "life-manager" : "sisdec",
  desde: 1791553000,
  estado,
  sessao: `s${numero}`,
  pid: 100 + numero,
  ferramenta: resumo ? "Bash" : "",
  resumo,
});

describe("terminais", () => {
  it("lista número, pasta, estado e o pedido pendente", () => {
    render(<TerminalList items={[t(1, "pedindo permissão", "npm test"), t(2, "trabalhando")]} />);
    expect(screen.getByText("T1")).toBeTruthy();
    expect(screen.getByText("pedindo permissão")).toBeTruthy();
    expect(screen.getByText("npm test")).toBeTruthy();
    expect(screen.getByText("sisdec")).toBeTruthy();
  });

  it("sem terminais", () => {
    render(<TerminalList items={[]} />);
    expect(screen.getByText("Nenhum terminal aberto.")).toBeTruthy();
  });

  it("cartão de terminais", () => {
    render(<CardView card={{ kind: "terminais", title: "Terminais", items: [t(1, "esperando você")] }} />);
    expect(screen.getByRole("region", { name: "Terminais" })).toBeTruthy();
    expect(screen.getByText("esperando você")).toBeTruthy();
  });
});
