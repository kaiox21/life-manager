import { describe, expect, it } from "vitest";
import { pulseOut, pulsing, smooth, tokenBoost, voiceTarget, type Pulse } from "./pulse";

const p = (over: Partial<Pulse> = {}): Pulse => ({ level: 0, levelAt: -1e9, tokenAt: -1e9, ...over });

describe("pulso do orbe", () => {
  it("segue o nível real da voz enquanto ele chega", () => {
    expect(voiceTarget(p({ level: 0.8, levelAt: 1000 }), true, 1100)).toBe(0.8);
    expect(voiceTarget(p({ level: 0.8, levelAt: 1000 }), false, 1100)).toBe(0);
  });

  it("voz local sem nível: pulso sintético entre 0,05 e 0,65", () => {
    const vals = Array.from({ length: 50 }, (_, i) => voiceTarget(p(), true, i * 20));
    expect(Math.min(...vals)).toBeGreaterThanOrEqual(0.05 - 1e-9);
    expect(Math.max(...vals)).toBeLessThanOrEqual(0.65 + 1e-9);
    expect(new Set(vals.map((v) => v.toFixed(2))).size).toBeGreaterThan(5);
  });

  it("ataque rápido e soltura mais lenta", () => {
    const up = smooth(0, 1, 60);
    const down = 1 - smooth(1, 0, 60);
    expect(up).toBeGreaterThan(down);
  });

  it("texto chegando acelera e brilha, e passa em 400 ms", () => {
    expect(tokenBoost(p({ tokenAt: 1000 }), 1000)).toBe(1);
    expect(tokenBoost(p({ tokenAt: 1000 }), 1500)).toBe(0);
    const calm = pulseOut(0, 0);
    const typing = pulseOut(0, 1);
    const loud = pulseOut(1, 0);
    expect(typing.speed).toBeGreaterThan(calm.speed);
    expect(typing.glow).toBeGreaterThan(calm.glow);
    expect(loud.scale).toBeCloseTo(1.12);
  });

  it("para de animar quando não há voz nem texto", () => {
    expect(pulsing(p(), false, 5000, 0)).toBe(false);
    expect(pulsing(p({ tokenAt: 4900 }), false, 5000, 0)).toBe(true);
    expect(pulsing(p(), true, 5000, 0)).toBe(true);
  });
});
