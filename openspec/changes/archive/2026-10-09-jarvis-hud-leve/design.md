## Context

O orbe do HUD (`Orb.tsx`) é um SVG com 140 partículas e dois anéis girando por CSS (`spin` de 18–40 s), um brilho que "respira" (`breathe`) e um `filter: drop-shadow` no SVG inteiro. Com um filtro no elemento, qualquer animação dentro dele obriga o WebKit a refazer o filtro a cada quadro. Medido em 09/10/2026: ~17% de CPU com o HUD aberto e parado. Motivação: ver `proposal.md`.

## Decisions

1. **Pausar, não remover:** `.orb--idle` põe `animation-play-state: paused` no núcleo, nos anéis e no brilho. A animação continua de onde parou quando o estado muda, sem salto. Alternativa descartada: `animation: none` no parado (o orbe pularia para a posição inicial ao voltar a girar).
2. **Brilho estático:** o filtro `drop-shadow` fica (é o visual), mas sem nada animado embaixo ele é desenhado uma vez.
3. **Estados com movimento** (ouvindo, pensando, falando) continuam iguais, com as durações atuais.
4. **Medição:** a mesma do painel (soma de `%cpu` do app e dos processos do WebKit, a cada 2 s, por 30 s), com o HUD aberto e parado, antes e depois.

## Risks / Trade-offs

- [O HUD parado parece "morto"] → o brilho e a cor continuam; se o Kaio sentir falta de vida, dá para um giro muito lento a poucos quadros por segundo, medindo de novo.

## Medição (09/10/2026)

- HUD aberto e parado, soma de `%cpu` do app e dos processos do WebKit a cada 2 s por 30 s: **0,7% de média** (máximo 3,6%, nos primeiros segundos, ao abrir). Antes: ~17%. Meta (< 5%) atingida.
- Aceite do Kaio (09/10/2026): "aceito".
