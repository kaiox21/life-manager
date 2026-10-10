import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { inTerminal } from "../Panel";
import { alertActive, resolveAlert, RESOLVED_MS, type ShownAlert } from "../lib/terminals";
import type { TerminalInfo, TerminalOpened, TerminalTab } from "../lib/types";
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
const withButtons: ShownAlert = { ...base, pedido: "p1", aba: "abcd1234" };

describe("aviso com botões", () => {
  it("sessão de fora: sem botões", () => {
    render(<AlertBar alert={base} onAnswer={() => {}} />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("aba: Permitir e Negar mandam a decisão do pedido", () => {
    const onAnswer = vi.fn();
    render(<AlertBar alert={withButtons} onAnswer={onAnswer} />);
    fireEvent.click(screen.getByRole("button", { name: "Permitir" }));
    fireEvent.click(screen.getByRole("button", { name: "Negar" }));
    expect(onAnswer.mock.calls).toEqual([
      ["p1", "permitir"],
      ["p1", "negar"],
    ]);
  });

  it("depois do clique, botões travados; resolvido, mostra o resultado", () => {
    const { rerender } = render(<AlertBar alert={{ ...withButtons, enviado: "permitir" }} onAnswer={() => {}} />);
    expect((screen.getByRole("button", { name: "Permitir" }) as HTMLButtonElement).disabled).toBe(true);
    rerender(<AlertBar alert={{ ...withButtons, resolvido: "respondido na aba" }} onAnswer={() => {}} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Respondido no terminal.");
  });

  it("não aprova com Enter: nenhum botão começa com foco", () => {
    render(<AlertBar alert={withButtons} onAnswer={() => {}} />);
    expect(document.activeElement?.tagName).not.toBe("BUTTON");
  });

  it("o aviso da aba não some em 20 s; some 2,5 s depois de resolvido", () => {
    expect(alertActive(withButtons, [], 1000 + 120_000)).toBe(true);
    const done = resolveAlert(withButtons, "p1", "permitido", 50_000)!;
    expect(alertActive(done, [], 50_000 + RESOLVED_MS - 1)).toBe(true);
    expect(alertActive(done, [], 50_000 + RESOLVED_MS + 1)).toBe(false);
    expect(resolveAlert(withButtons, "outro", "permitido", 1)).toBe(withButtons);
  });
});

const tabs: TerminalTab[] = [
  { sid: "aaaa1111", numero: 3, pasta: "life-manager", aberta: true, pid: 10 },
  { sid: "bbbb2222", numero: 4, pasta: "sisdec", aberta: false },
];
const terms = (estado: TerminalInfo["estado"]): TerminalInfo[] => [
  { numero: 3, pasta: "life-manager", desde: 1, estado, sessao: "", pid: 10, ferramenta: "", resumo: "", aba: "aaaa1111" },
];

function renderTabs(over: Partial<Parameters<typeof TerminalTabs>[0]> = {}) {
  const props = {
    tabs,
    terminals: terms("esperando você"),
    active: CENTRAL,
    onSelect: vi.fn(),
    onOpen: vi.fn(async (): Promise<TerminalOpened> => ({ status: "aberto", numero: 5, pasta: "x", sid: "cccc3333" })),
    onClose: vi.fn(),
    ...over,
  };
  render(<TerminalTabs {...props} />);
  return props;
}

describe("abas de terminal", () => {
  it("mostra Central, as abas e a encerrada com Retomar", () => {
    renderTabs();
    expect(screen.getByRole("tab", { name: "Central" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tab", { name: /Terminal 3 · life-manager/ })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /Terminal 4 · sisdec \(encerrada\)/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retomar" })).toBeTruthy();
  });

  it("Retomar pede a sessão anterior", async () => {
    const p = renderTabs();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Retomar" })));
    expect(p.onOpen).toHaveBeenCalledWith({ retomar: "bbbb2222" });
    expect(p.onSelect).toHaveBeenCalledWith("cccc3333");
  });

  it("+ abre pela pasta e seleciona a aba nova", async () => {
    const p = renderTabs();
    fireEvent.click(screen.getByRole("button", { name: "Abrir um Claude Code" }));
    fireEvent.change(screen.getByLabelText("Pasta do projeto"), { target: { value: "life-manager" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Abrir" })));
    expect(p.onOpen).toHaveBeenCalledWith({ pasta: "life-manager" });
    expect(p.onSelect).toHaveBeenCalledWith("cccc3333");
  });

  it("pasta ambígua mostra as opções; erro aparece", async () => {
    const onOpen = vi
      .fn()
      .mockResolvedValueOnce({ opcoes: ["~/Projetos pessoais/sisdec", "~/AmicusIA/sisdec"] })
      .mockResolvedValueOnce({ erro: "Já há 4 sessões abertas pelo Jarvis (o limite é 4)." });
    renderTabs({ onOpen });
    fireEvent.click(screen.getByRole("button", { name: "Abrir um Claude Code" }));
    fireEvent.change(screen.getByLabelText("Pasta do projeto"), { target: { value: "sisdec" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Abrir" })));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "~/AmicusIA/sisdec" })));
    expect(onOpen).toHaveBeenLastCalledWith({ pasta: "~/AmicusIA/sisdec" });
    expect(screen.getByRole("alert").textContent).toMatch(/limite é 4/);
  });

  it("fechar aba parada fecha direto", () => {
    const p = renderTabs();
    fireEvent.click(screen.getByRole("button", { name: "Fechar Terminal 3" }));
    expect(p.onClose).toHaveBeenCalledWith("aaaa1111");
  });

  it("fechar aba trabalhando pede confirmação", () => {
    const p = renderTabs({ terminals: terms("trabalhando"), active: "aaaa1111" });
    fireEvent.click(screen.getByRole("button", { name: "Fechar Terminal 3" }));
    expect(p.onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirmar: fechar Terminal 3" }));
    expect(p.onClose).toHaveBeenCalledWith("aaaa1111");
    expect(p.onSelect).toHaveBeenCalledWith(CENTRAL);
  });
});

describe("terminal", () => {
  it("quadro binário: tipo, sessão e bytes", () => {
    const buf = new Uint8Array([1, ...new TextEncoder().encode("abcd1234"), 104, 105]).buffer;
    const f = parseFrame(buf)!;
    expect([f.kind, f.sid, new TextDecoder().decode(f.data)]).toEqual(["output", "abcd1234", "hi"]);
    expect(parseFrame(new Uint8Array([9, 1, 2]).buffer)).toBeNull();
  });

  it("anexa, desenha a tela guardada, manda teclas e desanexa", async () => {
    const { TerminalView } = await import("./TerminalView");
    let sink: TermSink | null = null;
    const detach = vi.fn();
    const attach = vi.fn((_sid: string, s: TermSink) => {
      sink = s;
      return detach;
    });
    const send = vi.fn();
    const { unmount } = render(<TerminalView sid="aaaa1111" label="Terminal 3 · life-manager" attach={attach} send={send} />);
    expect(attach).toHaveBeenCalledWith("aaaa1111", expect.any(Function));
    expect(send).toHaveBeenCalledWith({ type: "term_resize", sid: "aaaa1111", cols: 100, rows: 30 });
    const term = fake.terms[0];
    sink!("replay", new Uint8Array([65]));
    expect(term.resets).toBe(1);
    term.callbacks[0](); // terminou de desenhar a tela guardada
    term.data!("\x1b");
    expect(send).toHaveBeenCalledWith({ type: "term_input", sid: "aaaa1111", data: "\x1b" });
    unmount();
    expect(detach).toHaveBeenCalled();
    expect(term.disposed).toBe(true);
  });

  it("respostas do xterm à tela guardada não vão para a sessão; teclas depois sim", async () => {
    const { TerminalView } = await import("./TerminalView");
    let sink: TermSink | null = null;
    const send = vi.fn();
    render(
      <TerminalView
        sid="aaaa1111"
        label="T"
        attach={(_s, s) => {
          sink = s;
          return () => {};
        }}
        send={send}
      />,
    );
    const term = fake.terms[0];
    sink!("replay", new TextEncoder().encode("\x1b[c"));
    term.data!("\x1b[?1;2c"); // o xterm respondendo à pergunta antiga
    expect(send).not.toHaveBeenCalledWith(expect.objectContaining({ type: "term_input" }));
    term.callbacks[0](); // terminou de desenhar
    term.data!("a");
    expect(send).toHaveBeenCalledWith({ type: "term_input", sid: "aaaa1111", data: "a" });
  });

  it("controle de fluxo: pausa acima de 500 KB e retoma abaixo de 100 KB", async () => {
    const { TerminalView } = await import("./TerminalView");
    let sink: TermSink | null = null;
    const send = vi.fn();
    render(
      <TerminalView
        sid="aaaa1111"
        label="T"
        attach={(_s, s) => {
          sink = s;
          return () => {};
        }}
        send={send}
      />,
    );
    const term = fake.terms[0];
    sink!("output", new Uint8Array(300_000));
    sink!("output", new Uint8Array(300_000));
    expect(send).toHaveBeenCalledWith({ type: "term_pause", sid: "aaaa1111", on: true });
    term.callbacks[0]();
    expect(send).not.toHaveBeenCalledWith({ type: "term_pause", sid: "aaaa1111", on: false });
    term.callbacks[1]();
    expect(send).toHaveBeenCalledWith({ type: "term_pause", sid: "aaaa1111", on: false });
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
