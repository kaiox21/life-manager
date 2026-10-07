# Gerenciador de Vida

Assistente pessoal de agenda e gastos: bot de WhatsApp (núcleo num VPS) e, depois, um Jarvis por voz no Mac, ambos usando as mesmas ferramentas.

## Arquivos de partida

| Arquivo | Para quê |
| --- | --- |
| `SPEC.md` | Especificação completa: decisões, arquitetura, dados, ferramentas, roteiro em fases |
| `CLAUDE.md` | Regras que o Claude Code segue em toda sessão |
| `PRIMEIRO_PROMPT.md` | O que colar no Claude Code para começar a fase 1 |
| `tests/eval/casos.yaml` | A prova: 54 mensagens com a chamada de ferramenta esperada |
| `.env.example` | Variáveis de ambiente; copie para `.env` |
| `docs/fases/` | Planos e relatórios de cada fase (o Claude Code preenche) |

## Antes da fase 1

1. Instale Docker no Mac (Docker Desktop ou OrbStack) e o `uv`.
2. Compre o chip pré-pago e registre o WhatsApp Business nele, no seu celular.
3. `git init` nesta pasta e abra o Claude Code aqui.

## Antes da fase 2

- Troque os cartões de exemplo em `tests/eval/casos.yaml` pelos seus reais e recalcule os casos marcados com "fatura".
- Reescreva as frases (`msg`) do seu jeito de falar.
- Crie um time pessoal no Vercel, compre US$ 5–10 de créditos do AI Gateway e defina um orçamento mensal.
