import { describe, expect, it } from "vitest";
import { MAX_TURNS, applyEvent, clearConfirm, startTurn } from "./conversation";

describe("conversa", () => {
  it("acumula passos, cartões e termina com a resposta", () => {
    let t = startTurn([], "r1", "o que eu tenho amanhã?");
    t = applyEvent(t, { type: "step", id: "r1", text: "consultando a agenda…" }, 1000);
    t = applyEvent(t, { type: "card", id: "r1", card: { kind: "texto", title: "x", text: "y" } });
    t = applyEvent(t, { type: "done", id: "r1", text: "Dentista às 14h." });
    expect(t[0]).toMatchObject({
      steps: [{ text: "consultando a agenda…", at: 1000 }],
      answer: "Dentista às 14h.",
      status: "done",
    });
    expect(t[0].cards).toHaveLength(1);
  });

  it("ignora eventos de outra pergunta", () => {
    const t = applyEvent(startTurn([], "r1", "a"), { type: "step", id: "r2", text: "x" });
    expect(t[0].steps).toEqual([]);
  });

  it("confirmação entra e sai", () => {
    let t = startTurn([], "r1", "a");
    t = applyEvent(t, { type: "confirm", id: "r1", confirm_id: "c1", text: "Confirma?" });
    expect(t[0].confirm).toEqual({ confirmId: "c1", text: "Confirma?" });
    expect(clearConfirm(t, "c1")[0].confirm).toBeUndefined();
  });

  it("erro marca a pergunta", () => {
    const t = applyEvent(startTurn([], "r1", "a"), { type: "error", id: "r1", text: "falhou" });
    expect(t[0].status).toBe("error");
  });

  it("voz: ouvindo vira a pergunta transcrita", () => {
    let t = startTurn([], "v1", "", "voz");
    expect(t[0].status).toBe("listening");
    t = applyEvent(t, { type: "heard", id: "v1", text: "o que eu tenho amanhã?" });
    expect(t[0]).toMatchObject({ question: "o que eu tenho amanhã?", status: "thinking", mode: "voz" });
  });

  it("voz sem fala some da conversa", () => {
    const t = applyEvent(startTurn([], "v1", "", "voz"), { type: "no_speech", id: "v1" });
    expect(t).toEqual([]);
  });

  it("guarda só as últimas perguntas", () => {
    let t: ReturnType<typeof startTurn> = [];
    for (let i = 0; i < MAX_TURNS + 2; i++) t = startTurn(t, `r${i}`, "q");
    expect(t).toHaveLength(MAX_TURNS);
    expect(t[0].id).toBe("r2");
  });
});

describe("palavra de ativação", () => {
  it("o wake começa um turno de voz ouvindo, e o heard vira a pergunta", async () => {
    const { startWakeTurn, applyEvent } = await import("./conversation");
    let turns = startWakeTurn([], "wake-1");
    expect(turns).toHaveLength(1);
    expect(turns[0]).toMatchObject({ id: "wake-1", mode: "voz", status: "listening", question: "" });
    expect(startWakeTurn(turns, "wake-1")).toBe(turns); // repetido: não duplica
    turns = applyEvent(turns, { type: "heard", id: "wake-1", text: "Que horas são?" });
    expect(turns[0]).toMatchObject({ question: "Que horas são?", status: "thinking" });
    expect(applyEvent(turns, { type: "no_speech", id: "wake-1" })).toHaveLength(0);
  });
});
