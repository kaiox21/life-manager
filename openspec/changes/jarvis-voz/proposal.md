## Why

O Jarvis por texto está aprovado (08/10/2026) e, com o Claude Haiku 5.5, responde em poucos segundos. A segunda porta do `SPEC.md` é **voz**: falar sem tirar a mão do teclado e ouvir a resposta. A lentidão que bloqueava a voz foi resolvida pelo change `modelo-anthropic`.

## What Changes

- **Push-to-talk**: segurar **⌘⇧Espaço** grava; soltar envia. **⌥Espaço** continua só para o modo texto (Esc fecha). Atalhos separados por decisão do Kaio em 09/10/2026.
- **Captura no app** (WebView do Jarvis.app, `getUserMedia` → PCM 16 kHz), com a **forma de onda** desenhada ao vivo no HUD. A permissão de Microfone fica atribuída ao Jarvis.app, não a um processo `python`.
- **Transcrição local** no cérebro, com `mlx-whisper` (`mlx-community/whisper-large-v3-turbo-q4`: 0,64 GB de RAM, ~0,85 s por frase, mesma qualidade do fp16 no teste) no M5, depois de cortar o silêncio com Silero VAD (`pysilero-vad`). Modelo carregado na subida.
- **Resposta por streaming**: o `AnthropicLLM` ganha `stream()`; o cérebro emite `token` conforme o texto chega e **fala a primeira frase enquanto o resto ainda é gerado**.
- **Fala local** com o `AVSpeechSynthesizer` do macOS (voz `Luciana` por padrão, configurável; primeiro áudio em 0,03–0,05 s, contra 0,8 s do `say`), numa thread do cérebro via PyObjC. Kokoro (`mlx-audio`, vozes `pf_dora`/`pm_alex`; exige `espeak-ng`) fica como experimento opcional.
- **Modo voz** no agente: resposta falada de no máximo duas frases, sem listas; detalhes continuam nos cartões. Comando digitado continua respondendo em texto.
- HUD ganha os estados **ouvindo**, **transcrevendo** e **falando**; a transcrição aparece como a pergunta; apertar o atalho de novo interrompe a fala (ou cancela o turno). Em modo voz o HUD **não rouba o foco** do app em uso e se esconde sozinho depois de falar.
- Ao chamar uma ferramenta, o Jarvis fala um curto "deixa eu ver…" (ligado por padrão, desligável), para a espera não ficar muda.
- Decisões do `SPEC.md` tocadas: a captura passa do Python (`sounddevice`) para o app (permissão limpa, forma de onda sem tráfego de áudio de volta) e a fala passa do `say` para o `AVSpeechSynthesizer`; o resto (push-to-talk, VAD, `mlx-whisper`, streaming para a fala) segue o `SPEC.md`.

## Non-goals

- Palavra de ativação ("Jarvis, ...") — próximo change, `jarvis-wake-word`.
- Voz no bot do WhatsApp (áudio lá continua com `faster-whisper` no núcleo).
- Conversa contínua de mãos livres (sem segurar o atalho).
- Central de comando em tela cheia (`jarvis-painel`).

## Capabilities

### New Capabilities
- `jarvis-voz`: push-to-talk, captura, transcrição local, fala local com streaming e interrupção.

### Modified Capabilities
- `jarvis-interface`: novos estados (ouvindo, transcrevendo, falando), forma de onda, transcrição como pergunta.
- `jarvis-agente`: modo voz (resposta curta, sem listas) e streaming de texto.

## Impact

- `jarvis/` (novos módulos `audio.py`, `tts.py`; `agent.py`, `server.py`, `events.py`), `jarvis-ui/` (captura, waveform, estados; `src-tauri`: evento de pressionar/soltar, `Info.plist` com `NSMicrophoneUsageDescription`), `app/agent/llm.py` (streaming no adaptador Anthropic).
- Dependências novas só no Mac, num extra `jarvis` do `pyproject` (o Docker do núcleo não as instala): `mlx-whisper` (traz `torch` e `numba`: ~1,1 GB no ambiente), `pysilero-vad`, `pyobjc-framework-AVFoundation`; `mlx-audio` opcional.
- Download único do modelo (~0,5 GB) e permissão de Microfone na primeira execução.
