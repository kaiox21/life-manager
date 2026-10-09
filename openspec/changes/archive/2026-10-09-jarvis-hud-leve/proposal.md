## Why

Medido em 09/10/2026: com o HUD aberto e parado, o Jarvis gasta ~17% de CPU (app + processos do WebKit), porque os anéis e as partículas do orbe giram o tempo todo e o brilho do SVG inteiro é recalculado a cada quadro. Num MacBook Air sem ventoinha e com pouca memória livre, isso é bateria e calor sem motivo.

## What Changes

- Com o Jarvis **parado** (online e sem ouvir, pensar ou falar), o orbe do HUD **congela** na posição em que está: sem giro e sem "respiração".
- Ele **volta a se mexer** na hora em que o Jarvis ouve, pensa ou fala, como hoje. Congelar é pausar a animação, sem salto visual.
- Nada muda no painel (já medido: 9,2% de CPU) nem no comportamento da conversa.

## Non-goals

- Redesenhar o orbe ou trocar SVG por canvas.
- Mexer no painel ou na voz.

## Capabilities

### New Capabilities
<!-- nenhuma -->

### Modified Capabilities
- `jarvis-interface`: o requisito "Estados visíveis" passa a dizer que o orbe só se anima quando há atividade, com meta de CPU com o HUD parado.

## Impact

- `jarvis-ui/src/theme.css` (animações do orbe por estado). Sem mudança em Rust, Python ou no núcleo.
- `SPEC.md`: fecha a questão "HUD leve".
