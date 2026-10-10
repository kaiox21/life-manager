import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { inTerminal } from "../Panel";
import { alertActive, closingEnds, resolveAlert, RESOLVED_MS, type ShownAlert } from "../lib/terminals";
import type { TerminalInfo, TerminalOpened } from "../lib/types";
import { parseFrame, type TermSink } from "../lib/useJarvis";
import { AlertBar } from "./AlertBar";
import { CENTRAL, TerminalTabs } from "./TerminalTabs";

// xterm desenha em canvas (não existe no jsdom): um terminal falso guarda o que recebeu.
const fake = vi.hoisted(() => ({ terms: [] as FakeTerm[] }));
interface FakeTerm {
  written: Uint8Array[];
  callbacks: (() => void)[];
  resets: number;
  data?: (d: string) => void;
  cols: number;
  rows: number;
  disposed: boolean;
}
vi.mock("@xterm/xterm", () => ({
  Terminal: class {
    cols = 100;
    rows = 30;
    written: Uint8Array[] = [];
    callbacks: (() => void)[] = [];
    resets = 0;
    disposed = false;
    data?: (d: string) => void;
    constructor() {
      fake.terms.push(this as unknown as FakeTerm);
    }
    loadAddon() {}
    open() {}
    focus() {}
    attachCustomKeyEventHandler() {}
    reset() {
      this.resets += 1;
    }
    write(d: Uint8Array, cb: () => void) {
      this.written.push(d);
      this.callbacks.push(cb);
    }
    onData(fn: (d: string) => void) {
      this.data = fn;
      return { dispose() {} };
    }
    onResize() {
      return { dispose() {} };
    }
    dispose() {
      this.disposed = true;
    }
  },
}));
vi.mock("@xterm/addon-fit", () => ({ FitAddon: class { fit() {} } }));
vi.mock("@xterm/xterm/css/xterm.css", () => ({}));

afterEach(cleanup);
beforeEach(() => {
  fake.terms.length = 0;
});

const base: ShownAlert = {
  tipo: "permissao",
  numero: 3,
  pasta: "life-manager",
  ferramenta: "Bash",
  resumo: "npm test",
  texto: "Terminal 3 (life-manager) está pedindo para rodar `npm test`",
  at: 1000,
};
const withButtons: ShownAlert = { ...base, pedido: "p1", chave: "tmux:$3" };

describe("aviso com botões", () => {
  it("sessão de fora: sem botões", () => {
    render(<AlertBar alert={base} onAnswer={() => {}} />);
    expect(screen.queryByRole("button", { name: /Permitir|Negar/ })).toBeNull();
  });

  it("terminal compartilhado: Permitir e Negar mandam a decisão do pedido", () => {
    const onAnswer = vi.fn();
    render(<AlertBar alert={withButtons} onAnswer={onAnswer} />);
    fireEvent.click(screen.getByRole("button", { name: "Permitir" }));
    fireEvent.click(screen.getByRole("button", { name: "Negar" }));
    expect(onAnswer.mock.calls).toEqual([
      ["p1", "permitir"],
      ["p1", "negar"],
    ]);
  });

  it("depois do clique, botões travados; resolvido, diz o que foi enviado (não 'permitido')", () => {
    const { rerender } = render(<AlertBar alert={{ ...withButtons, enviado: "permitir" }} onAnswer={() => {}} />);
    expect((screen.getByRole("button", { name: "Permitir" }) as HTMLButtonElement).disabled).toBe(true);
    rerender(<AlertBar alert={{ ...withButtons, resolvido: "permitido" }} onAnswer={() => {}} />);
    expect(screen.getByRole("status").textContent).toBe("Permitir enviado ao terminal.");
    rerender(<AlertBar alert={{ ...withButtons, resolvido: "respondido na aba" }} onAnswer={() => {}} />);
    expect(screen.queryByRole("button", { name: /Permitir|Negar/ })).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Respondido no terminal.");
  });

  it("× fecha o aviso (o HUD do aviso não pega o Esc)", () => {
    const onDismiss = vi.fn();
    render(<AlertBar alert={withButtons} onAnswer={() => {}} onDismiss={onDismiss} />);
    fireEvent.click(screen.getByRole("button", { name: "Fechar o aviso" }));
    expect(onDismiss).toHaveBeenCalled();
  });

  it("não aprova com Enter: nenhum botão começa com foco", () => {
    render(<AlertBar alert={withButtons} onAnswer={() => {}} />);
    expect(document.activeElement?.tagName).not.toBe("BUTTON");
  });

  it("o aviso com pedido não some em 20 s; some 2,5 s depois de resolvido", () => {
    expect(alertActive(withButtons, [], 1000 + 120_000)).toBe(true);
    const done = resolveAlert(withButtons, "p1", "permitido", 50_000)!;
    expect(alertActive(done, [], 50_000 + RESOLVED_MS - 1)).toBe(true);
    expect(alertActive(done, [], 50_000 + RESOLVED_MS + 1)).toBe(false);
    expect(resolveAlert(withButtons, "outro", "permitido", 1)).toBe(withButtons);
  });
});

const term = (over: Partial<TerminalInfo> = {}): TerminalInfo => ({
  numero: 3,
  pasta: "life-manager",
  desde: 1,
  estado: "livre",
  sessao: "",
  pid: null,
  ferramenta: "",
  resumo: "",
  tmux: "$3",
  tipo: "shell",
  aba: true,
  origem: "jarvis",
  janela: false,
  ocupado: false,
  ...over,
});

function renderTabs(over: Partial<Parameters<typeof TerminalTabs>[0]> = {}) {
  const props = {
    terminals: [
      term(),
      term({ numero: 4, pasta: "sisdec", tmux: "$4", aba: false }), // sem aba: fica só na lista
      term({ numero: 1, tmux: "", aba: false, tipo: "claude", estado: "trabalhando" }), // de fora
    ],
    active: CENTRAL,
    onSelect: vi.fn(),
    onOpen: vi.fn(async (): Promise<TerminalOpened> => ({ status: "aberto", numero: 5, pasta: "x", sessao: "$5", tipo: "shell" })),
    onCloseTab: vi.fn(),
    ...over,
  };
  render(<TerminalTabs {...props} />);
  return props;
}

describe("abas de terminal", () => {
  it("só os terminais compartilhados com aba viram abas", () => {
    renderTabs();
    expect(screen.getByRole("tab", { name: "Central" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tab", { name: /Terminal 3 · life-manager/ })).toBeTruthy();
    expect(screen.queryByRole("tab", { name: /Terminal 4/ })).toBeNull();
    expect(screen.queryByRole("tab", { name: /Terminal 1/ })).toBeNull();
  });

  it("+ abre terminal ou Claude Code pela pasta e seleciona a aba nova", async () => {
    const p = renderTabs();
    fireEvent.click(screen.getByRole("button", { name: "Abrir um terminal" }));
    fireEvent.click(screen.getByLabelText(/Claude Code/));
    fireEvent.change(screen.getByLabelText("Pasta do projeto"), { target: { value: "life-manager" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Abrir" })));
    expect(p.onOpen).toHaveBeenCalledWith({ pasta: "life-manager", claude: true });
    expect(p.onSelect).toHaveBeenCalledWith("$5");
  });

  it("pasta ambígua mostra as opções; erro aparece", async () => {
    const onOpen = vi
      .fn()
      .mockResolvedValueOnce({ opcoes: ["~/Projetos pessoais/sisdec", "~/AmicusIA/sisdec"] })
      .mockResolvedValueOnce({ erro: "Já há 4 Claude Code rodando nos terminais (o limite é 4)." });
    renderTabs({ onOpen });
    fireEvent.click(screen.getByRole("button", { name: "Abrir um terminal" }));
    fireEvent.change(screen.getByLabelText("Pasta do projeto"), { target: { value: "sisdec" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Abrir" })));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "~/AmicusIA/sisdec" })));
    expect(onOpen).toHaveBeenLastCalledWith({ pasta: "~/AmicusIA/sisdec", claude: false });
    expect(screen.getByRole("alert").textContent).toMatch(/limite é 4/);
  });

  it("fechar a aba de um terminal do Jarvis não pergunta (ele continua vivo)", () => {
    const p = renderTabs({ terminals: [term({ ocupado: true, estado: "rodando" })] });
    fireEvent.click(screen.getByRole("button", { name: "Fechar a aba do Terminal 3" }));
    expect(p.onCloseTab).toHaveBeenCalledWith("$3");
  });

  it("fechar a aba que encerra um terminal do Terminal.app com algo rodando pede confirmação", () => {
    const t = term({ origem: "terminal", janela: false, ocupado: true, estado: "rodando" });
    expect(closingEnds(t)).toBe(true);
    const p = renderTabs({ terminals: [t], active: "$3" });
    fireEvent.click(screen.getByRole("button", { name: "Fechar a aba do Terminal 3" }));
    expect(p.onCloseTab).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirmar: encerrar Terminal 3" }));
    expect(p.onCloseTab).toHaveBeenCalledWith("$3");
    expect(p.onSelect).toHaveBeenCalledWith(CENTRAL);
  });

  it("com a janela do Terminal.app aberta, fechar a aba não encerra e não pergunta", () => {
    const t = term({ origem: "terminal", janela: true, ocupado: true, estado: "rodando" });
    expect(closingEnds(t)).toBe(false);
    const p = renderTabs({ terminals: [t] });
    fireEvent.click(screen.getByRole("button", { name: "Fechar a aba do Terminal 3" }));
    expect(p.onCloseTab).toHaveBeenCalledWith("$3");
  });
});

describe("terminal", () => {
  it("quadro binário: sessão e bytes", () => {
    const buf = new Uint8Array([1, ...new TextEncoder().encode("$3      "), 104, 105]).buffer;
    const f = parseFrame(buf)!;
    expect([f.sessao, new TextDecoder().decode(f.data)]).toEqual(["$3", "hi"]);
    expect(parseFrame(new Uint8Array([2, 1, 2]).buffer)).toBeNull();
  });

  it("anexa com o tamanho, desenha, manda teclas e desanexa", async () => {
    const { TerminalView } = await import("./TerminalView");
    let sink: TermSink | null = null;
    const detach = vi.fn();
    const attach = vi.fn((_s: string, s: TermSink) => {
      sink = s;
      return detach;
    });
    const send = vi.fn();
    const { unmount } = render(<TerminalView sessao="$3" label="Terminal 3 · life-manager" attach={attach} send={send} />);
    expect(attach).toHaveBeenCalledWith("$3", expect.any(Function), 100, 30);
    const t = fake.terms[0];
    sink!(new Uint8Array([65]));
    expect(t.written).toHaveLength(1);
    t.data!("\x1b");
    expect(send).toHaveBeenCalledWith({ type: "term_input", sessao: "$3", data: "\x1b" });
    unmount();
    expect(detach).toHaveBeenCalled();
    expect(t.disposed).toBe(true);
  });

  it("controle de fluxo: pausa acima de 500 KB e retoma abaixo de 100 KB", async () => {
    const { TerminalView } = await import("./TerminalView");
    let sink: TermSink | null = null;
    const send = vi.fn();
    render(
      <TerminalView
        sessao="$3"
        label="T"
        attach={(_s, s) => {
          sink = s;
          return () => {};
        }}
        send={send}
      />,
    );
    const t = fake.terms[0];
    sink!(new Uint8Array(300_000));
    sink!(new Uint8Array(300_000));
    expect(send).toHaveBeenCalledWith({ type: "term_pause", sessao: "$3", on: true });
    t.callbacks[0]();
    expect(send).not.toHaveBeenCalledWith({ type: "term_pause", sessao: "$3", on: false });
    t.callbacks[1]();
    expect(send).toHaveBeenCalledWith({ type: "term_pause", sessao: "$3", on: false });
  });

  it("Esc dentro do terminal não fecha o painel", () => {
    const box = document.createElement("div");
    box.className = "term-view";
    const inner = document.createElement("textarea");
    box.appendChild(inner);
    document.body.appendChild(box);
    expect(inTerminal(inner)).toBe(true);
    expect(inTerminal(document.body)).toBe(false);
    box.remove();
  });
});
