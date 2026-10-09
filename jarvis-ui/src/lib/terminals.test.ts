import { describe, expect, it } from "vitest";
import { alertActive, isLoud, type ShownAlert } from "./terminals";
import type { TerminalInfo } from "./types";

const term = (estado: TerminalInfo["estado"]): TerminalInfo => ({
  numero: 1,
  pasta: "life-manager",
  desde: 1,
  estado,
  sessao: "s1",
  pid: 7958,
  ferramenta: "Bash",
  resumo: "npm test",
});
const alert: ShownAlert = {
  tipo: "permissao",
  numero: 1,
  pasta: "life-manager",
  ferramenta: "Bash",
  resumo: "npm test",
  texto: "Terminal 1 (life-manager) está pedindo para rodar `npm test`",
  at: 1000,
};

describe("avisos de terminal", () => {
  it("fica enquanto o terminal pede permissão", () => {
    expect(alertActive(alert, [term("pedindo permissão")], 5000)).toBe(true);
  });
  it("some quando o terminal volta a trabalhar", () => {
    expect(alertActive(alert, [term("trabalhando")], 5000)).toBe(false);
  });
  it("some em 20 s e quando o terminal fecha", () => {
    expect(alertActive(alert, [term("pedindo permissão")], 21_001)).toBe(false);
    expect(alertActive(alert, [], 2000)).toBe(false);
  });
  it("terminou não chama por cima", () => {
    expect(isLoud({ ...alert, tipo: "terminou" })).toBe(false);
    expect(isLoud(alert)).toBe(true);
  });
});
