## Context

Hoje o `FishSynth` (change `jarvis-voz`, arquivado) pede cada frase em MP3, espera o arquivo inteiro e toca com um `AVAudioPlayer` por frase. Motivação: ver `proposal.md`.

## Goals / Non-Goals

**Goals:** primeiro som de cada frase em ~0,7–0,8 s depois de a frase fechar; sem engasgos; interrupção imediata; mesma reserva local.

**Non-Goals:** mexer na transcrição, no modelo ou no provedor de voz.

## Decisions

1. **PCM 24 kHz por streaming.** Teste de 09/10/2026 (mesma frase, 3 rodadas, conexão reaproveitada): MP3 inteiro em 1,8–2,0 s; PCM com 1º byte em 0,67–0,82 s e frase inteira em 1,8–2,1 s para 2,8 s de áudio, ou seja, chega mais rápido do que toca. Em 44,1 kHz o 1º byte demorou 1,85 s, então fica 24 kHz. Campos da API conferidos em docs.fish.audio em 09/10/2026: `format: "pcm"`, `sample_rate`, resposta `audio/pcm` em `Transfer-Encoding: chunked`.
2. **Uma saída de áudio contínua pelo PortAudio** (`sounddevice.RawOutputStream`, Int16 mono, `latency="low"`), aberta no primeiro uso e reaproveitada. Alternativas: `AVAudioEngine` + `AVAudioPlayerNode` pelo PyObjC (copiar amostras para `AVAudioPCMBuffer` em Python é trabalhoso e frágil); `afplay` com arquivo (não toca enquanto baixa). O `sounddevice` traz o PortAudio no wheel do macOS, sem instalar nada no sistema.
3. **Download e tocador separados.** Cada frase ganha uma fila de pedaços e uma tarefa de download que começa na hora (a próxima baixa enquanto a anterior toca). Um único tocador consome as frases em ordem e escreve na saída numa thread (`asyncio.to_thread`, porque `write` bloqueia até caber no buffer).
4. **Pré-buffer de 0,1 s** antes do primeiro `write` de cada frase, para não começar e engasgar logo em seguida. Pedaços são cortados em amostras inteiras (número par de bytes).
5. **Eventos de fala:** "start" no primeiro `write` de cada frase (é o que a medição `→fala` usa); "finish" depois do último `write`, somado à latência da saída (o fim ainda está no buffer).
6. **Interrupção:** cancela downloads e tocador e chama `abort()` na saída (descarta o buffer na hora), reabrindo-a em seguida.
7. **Falhas:** erro antes de sair som → a frase e o resto vão para a voz local e a Fish fica de lado por 5 min (como hoje); erro no meio de uma frase → a frase termina ali e a próxima segue.
8. **Enchimentos em cache** guardam o PCM inteiro e são escritos de uma vez.

## Risks / Trade-offs

- [Rede lenta faz o áudio chegar mais devagar do que toca] → o PortAudio toca silêncio enquanto falta dado (um engasgo audível, sem travar); o pré-buffer de 0,1 s cobre variações pequenas. Se acontecer com frequência, subir o pré-buffer.
- [Saída de áudio presa a um dispositivo] → trocar de fone ou caixa com o Jarvis aberto pode manter o som no dispositivo antigo até a próxima interrupção (que reabre a saída). Anotado; tratar se incomodar.
- [Mais uma dependência nativa] → `sounddevice` só no extra `jarvis`; os testes usam saída falsa.

## Medições (09/10/2026)

- Fish isolada, PCM em streaming: 1º som de cada frase em 0,67–1,0 s (MP3 inteiro: 1,0–2,0 s).
- Ponta a ponta com os áudios de teste (o áudio chega todo de uma vez, então "ouvir→texto" fica ~1 s maior que no uso real, ~1,7 s contra ~0,65 s): do 1º token até a fala, 0,85–1,2 s (antes, com MP3: 1,3–1,7 s). Pergunta simples: fala em 3,7–4,3 s; com ferramenta: "um instante" em 3,2 s e resposta em 4,9 s. Descontando a diferença do microfone real, a estimativa é de ~2,7–3,2 s (simples) e ~3,9 s (com ferramenta).
- Abrir a saída de áudio na primeira fala custava tempo; ela passou a abrir quando o Jarvis liga.
- O que sobra é o modelo terminar a primeira frase (a fala só começa quando a frase fecha) mais ~0,7 s da Fish.
- **Microfone real (aceite, 09/10/2026):** fala→texto 0,57–1,1 s; pergunta simples com fala em 3,4–4,4 s; com ferramenta, "um instante" em 2,5–3,0 s e resposta em 4,9–5,4 s. A estimativa estava otimista: o 1º token do modelo variou de 1,9 a 3,4 s depois do texto, e é ele que domina agora. As metas de 3 s / 4 s não foram atingidas; o Kaio aprovou o resultado. Próximo ganho, se precisar: o modelo (latência do 1º token), não a voz.
