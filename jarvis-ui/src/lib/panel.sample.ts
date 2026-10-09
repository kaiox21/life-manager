import type { PanelData } from "./types";

/** Dados de exemplo do painel para os testes. */
export const SAMPLE: PanelData = {
  agora: "2026-10-09T14:03:00-03:00",
  agenda: {
    hoje: [{ id: "1", titulo: "Dentista", tipo: "compromisso", data: "sexta 09/10/2026", hora: "15:00" }],
    proximos: [],
  },
  mes: {
    periodo: "01/10/2026 a 09/10/2026",
    total: "R$ 77,90",
    total_centavos: 7790,
    grupos: [
      { grupo: "Alimentação", total: "R$ 47,90", total_centavos: 4790, lancamentos: 1 },
      { grupo: "Transporte", total: "R$ 30,00", total_centavos: 3000, lancamentos: 1 },
    ],
  },
  faturas: [
    {
      cartao: "Nubank",
      mes_vencimento: "2026-11",
      vencimento: "08/11/2026",
      fechamento: "31/10/2026",
      situacao: "aberta",
      total: "R$ 77,90",
      total_centavos: 7790,
      lancamentos: 2,
    },
  ],
  registro: [{ tipo: "gasto", quando: "2026-10-09T13:00:00-03:00", texto: "uber · R$ 30,00 · Nubank", origem: "mac" }],
  perguntas: ["quanto gastei?"],
};
