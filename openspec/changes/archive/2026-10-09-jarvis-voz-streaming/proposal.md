## Why

A resposta falada do Jarvis ainda demora: com ferramenta, a primeira frase sai em 4,7–5,2 s depois de soltar o atalho (medido em 09/10/2026), acima da meta original de 4 s. Boa parte disso é esperar a Fish Audio gerar a frase inteira em MP3 (~1–2 s) antes de tocar. Um teste em 09/10/2026 mostrou que a Fish entrega o áudio em PCM por streaming com o primeiro som em ~0,7–0,8 s e mais rápido do que ele toca, então dá para começar a falar enquanto o resto chega.

## What Changes

- A voz da Fish passa a ser pedida em **PCM 24 kHz por streaming** e **tocada enquanto chega**, com um pré-buffer de 0,1 s, em vez de baixar o MP3 inteiro e só então tocar.
- As frases continuam em ordem e a próxima começa a baixar enquanto a anterior toca. "Um instante, senhor." continua guardado em memória e sai na hora.
- A saída de áudio passa a ser uma só, aberta uma vez (PortAudio, pacote `sounddevice`), em vez de um `AVAudioPlayer` por frase.
- Interromper (⌘⇧Espaço durante a fala) descarta o áudio que já estava no buffer, na hora.
- Se a Fish falhar antes de sair som, a frase e o resto vão para a voz local, como hoje; se cair no meio de uma frase, a frase termina onde parou e a resposta segue.
- Metas voltam ao original: primeira palavra em menos de 3 s numa pergunta simples e resposta com ferramenta em menos de 4 s.

## Non-goals

- Trocar de provedor de voz ou de modelo da Fish.
- Tocar o MP3 progressivamente (exigiria um decodificador em streaming; o PCM resolve sem isso).
- Mudanças na transcrição ou no modelo de linguagem.

## Capabilities

### New Capabilities
<!-- nenhuma -->

### Modified Capabilities
- `jarvis-voz`: o requisito "Fala com streaming" passa a exigir que a fala comece antes de a frase terminar de chegar, com metas de 3 s (simples) e 4 s (com ferramenta).

## Impact

- `jarvis/tts.py`: `FishSynth` reescrito (download em PCM por streaming, um tocador em ordem, `PortAudioOut`); o `AVAudioPlayer` sai.
- `pyproject.toml`: `sounddevice` no extra `jarvis`.
- Testes em `tests/jarvis/test_tts.py` com rede e saída de áudio falsas.
- `SPEC.md`: decisão do Jarvis atualizada com os tempos novos; fecha a questão "Voz mais rápida".
- Custo: nenhum (mesmo modelo gratuito da Fish).
