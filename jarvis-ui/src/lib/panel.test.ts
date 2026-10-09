import { describe, expect, it } from "vitest";
import { EMPTY_PANEL, applyPanel, barShare, dayShort, panelFailed, panelLoading, whenShort } from "./panel";
import { SAMPLE } from "./panel.sample";


describe("painel", () => {
  it("dados novos limpam o erro e marcam a hora", () => {
    const s = applyPanel(panelLoading(EMPTY_PANEL), SAMPLE, 1000);
    expect(s).toEqual({ data: SAMPLE, error: "", updatedAt: 1000, loading: false });
  });

  it("núcleo fora mantém os dados antigos, mas marcados com erro e a hora antiga", () => {
    const ok = applyPanel(EMPTY_PANEL, SAMPLE, 1000);
    const down = applyPanel(ok, { erro: "núcleo indisponível" }, 5000);
    expect(down.data).toBe(SAMPLE);
    expect(down.error).toBe("núcleo indisponível");
    expect(down.updatedAt).toBe(1000);
  });

  it("cérebro fora sem dados nenhum", () => {
    expect(panelFailed(EMPTY_PANEL, "cérebro indisponível")).toMatchObject({ data: null, error: "cérebro indisponível" });
  });

  it("barras proporcionais ao maior valor, com mínimo visível", () => {
    expect(barShare(4790, 4790)).toBe(100);
    expect(barShare(3000, 4790)).toBe(63);
    expect(barShare(1, 100000)).toBe(2);
    expect(barShare(0, 0)).toBe(0);
  });

  it("datas curtas", () => {
    expect(dayShort("sábado 10/10/2026")).toBe("sáb 10/10");
    const now = new Date("2026-10-09T15:00:00-03:00");
    expect(whenShort("2026-10-09T13:05:00-03:00", now)).toBe("13:05");
    expect(whenShort("2026-10-08T18:35:00-03:00", now)).toBe("08/10");
  });
});
