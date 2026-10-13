import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SAMPLE } from "./lib/panel.sample";
import { EMPTY_PANEL, applyPanel, nextEvent, type PanelState } from "./lib/panel";
import { Agenda, ClaudeCard, ClockCard, Conversation, Log, MacCard, Month, NoticiasCard, Projects, VagasCard, Weather, boletimTitle, pausedLabel } from "./Panel";
import { resetsIn } from "./lib/panel";
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

  it("núcleo fora: clima e Mac aparecem, agenda avisa", () => {
    const down = applyPanel(EMPTY_PANEL, {
      erro: "núcleo indisponível",
      clima: { agora: 28, max: 32, min: 20, chuva: 0, cidade: "Brasília" },
      mac: { memoria_livre: 34, swap_gb: 18.7, bateria: { pct: 27, carregando: false } },
      musica: null,
      projetos: [],
    }, Date.now());
    render(
      <>
        <Weather panel={down} />
        <MacCard panel={down} />
        <Agenda panel={down} />
      </>,
    );
    expect(screen.getByText("28°")).toBeTruthy();
    expect(screen.getByRole("img", { name: "Memória livre: 34%" })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe("núcleo indisponível");
  });

  it("limites do Claude Code: 5 horas e semana, com quando zeram", () => {
    const now = new Date("2026-10-12T10:00:00-03:00");
    const t = now.getTime() / 1000;
    const panel = applyPanel(EMPTY_PANEL, {
      erro: "núcleo indisponível",
      claude: {
        cinco_horas: { pct: 82.4, resets_at: t + 2 * 3600 + 600 },
        semana: null,
        atualizado: t - 60,
        sessoes: {},
      },
    }, Date.now());
    render(<ClaudeCard panel={panel} now={now} />);
    expect(screen.getByRole("img", { name: "Limite de 5 horas: 82% usado" })).toBeTruthy();
    expect(screen.getByText("zera em 2h10")).toBeTruthy();
    expect(screen.getByText("zerou")).toBeTruthy();
    expect(resetsIn(t + 3 * 86400, now.getTime())).toBe("zera em 3 dias");
  });

  it("sem barra de status ainda: explica como aparecer", () => {
    const panel = applyPanel(EMPTY_PANEL, { erro: "x", claude: null }, Date.now());
    render(<ClaudeCard panel={panel} />);
    expect(screen.getByText("Sem dados: abra uma sessão do Claude Code.")).toBeTruthy();
  });

  it("vagas do radar com código, prazo e link", () => {
    const vagas = [
      { codigo: "V12", titulo: "Estágio em Dev", organizacao: "Empresa X", tipo: "estágio", local: "Remoto", prazo: "20/10/2026", link: "https://gupy.io/vagas/123", resumo: "" },
      { codigo: "V13", titulo: "Bolsa PIBIC", organizacao: "UnB", tipo: "bolsa", local: "Brasília", prazo: "sem prazo informado", link: "https://unb.br/x", resumo: "" },
    ];
    render(<VagasCard panel={ok({ ...SAMPLE, vagas })} />);
    expect(screen.getByRole("link", { name: /V12.*Estágio em Dev/ }).getAttribute("href")).toBe("https://gupy.io/vagas/123");
    expect(screen.getByText(/até 20\/10/)).toBeTruthy();
    expect(screen.getByText(/sem prazo/)).toBeTruthy();
  });

  it("sem vagas recentes", () => {
    render(<VagasCard panel={ok({ ...SAMPLE, vagas: [] })} />);
    expect(screen.getByText("Nenhuma vaga nova nos últimos 14 dias.")).toBeTruthy();
  });

  it("notícias: gerais e futebol à parte, título é o link", () => {
    const noticias = {
      data: "2026-10-09",
      itens: [
        { titulo: "Nova IA lançada", resumo: "r", fonte: "G1", link: "https://g1.globo.com/a", futebol: false },
        { titulo: "Flamengo vence", resumo: "r", fonte: "ge", link: "https://ge.globo.com/b", futebol: true },
      ],
    };
    render(<NoticiasCard panel={ok({ ...SAMPLE, noticias })} now={at("09:00")} />);
    expect(screen.getByText("Notícias de hoje")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Nova IA lançada/ }).getAttribute("href")).toBe("https://g1.globo.com/a");
    expect(screen.getByText("Futebol")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Flamengo vence.*ge/ })).toBeTruthy();
  });

  it("notícias: de madrugada mostra a de ontem; sem boletim, avisa a hora", () => {
    expect(boletimTitle("2026-10-13", new Date(2026, 9, 14, 1, 0))).toBe("Notícias de ontem, 13/10");
    expect(boletimTitle("2026-10-14", new Date(2026, 9, 14, 8, 0))).toBe("Notícias de hoje");
    expect(boletimTitle("2026-10-10", new Date(2026, 9, 14, 8, 0))).toBe("Notícias de 10/10");
    render(<NoticiasCard panel={ok({ ...SAMPLE, noticias: null })} />);
    expect(screen.getByText("O boletim sai às 07:30.")).toBeTruthy();
  });
});

describe("botão Silenciar (jarvis-proativo)", () => {
  it("mostra até quando os avisos estão pausados, e some quando a pausa passou", () => {
    const now = new Date("2026-10-13T14:40:00-03:00");
    expect(pausedLabel({ pausa_ate: "2026-10-13T15:40:00-03:00" }, now)).toBe("15:40");
    expect(pausedLabel({ pausa_ate: "2026-10-13T14:00:00-03:00" }, now)).toBeNull();
    expect(pausedLabel({ pausa_ate: null }, now)).toBeNull();
    expect(pausedLabel(undefined, now)).toBeNull();
  });
});
