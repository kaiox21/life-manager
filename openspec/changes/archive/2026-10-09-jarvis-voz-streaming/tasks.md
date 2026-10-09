## 1. Voz em streaming

- [x] 1.1 `FishSynth` reescrito: download PCM 24 kHz por streaming, fila por frase, tocador único em ordem, pré-buffer de 0,1 s, `PortAudioOut` (`sounddevice`), enchimentos em cache; `sounddevice` no extra `jarvis`
- [x] 1.2 Testes com rede e saída falsas: toca antes de a frase chegar inteira e na ordem; Fish fora do ar cai para a voz local e fica de lado; interromper corta o áudio (`abort`); enchimento em cache sai sem rede

## 2. Fechamento

- [x] 2.1 `uv run pytest` e `ruff`; reiniciar o cérebro e medir de ponta a ponta com os áudios de teste (`→fala` menor que antes); a prova do núcleo não precisa rodar (nada muda no núcleo)
- [x] 2.2 Aceite com o Kaio pelo microfone (09/10/2026, "funcionando perfeitamente", sem engasgos; tempos reais: simples 3,4–4,4 s, com ferramenta "um instante" 2,5–3,0 s e resposta 4,9–5,4 s; as metas de 3 s / 4 s **não** foram atingidas, ver design): "que dia é hoje?" com 1ª palavra < 3 s e "o que eu tenho amanhã?" com resposta < 4 s; fala sem engasgos; ⌘⇧Espaço durante a fala corta na hora
- [x] 2.3 `SPEC.md` (decisão do Jarvis com os tempos novos; fechar "Voz mais rápida") e arquivar
