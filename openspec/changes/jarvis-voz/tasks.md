## 1. Risco primeiro: microfone no app

- [x] 1.1 Rust: ⌘⇧Espaço (voz) com `Pressed`/`Released`, ⌥Espaço só modo texto (ignorar auto-repeat) → eventos `jarvis://ptt`; `src-tauri/Info.plist` com `NSMicrophoneUsageDescription`; confirmar a permissão de microfone no `tauri dev` e no bundle (fallback `cpal`)
- [x] 1.2 Captura `getUserMedia` + `AudioWorklet` → PCM Int16 16 kHz em quadros binários pelo WebSocket; forma de onda no HUD

## 2. Base de áudio no cérebro

- [x] 2.1 Extra `jarvis` no `pyproject` (`mlx-whisper`, `pysilero-vad`, `pyobjc-framework-AVFoundation`, marcador darwin/arm64); `jarvis/audio.py` com VAD ("houve fala?"), transcrição `mlx-whisper` q4 (warmup, `initial_prompt` com nomes do núcleo, thread); testes com áudio gerado pelo `say` (marcador `whisper`)
- [x] 2.2 `jarvis/tts.py`: `AVSpeechSynthesizer` numa thread com `NSRunLoop`, fila de frases, `stop()`, callback de início (`didStart`) para a medição; `say` como fallback; backend `kokoro` opcional; testes com sintetizador falso
- [x] 2.3 Protocolo: `voice_start`/quadros binários/`voice_end`/`voice_cancel` e `heard`/`speaking`/`status` em `events.py` e `server.py` (binário x JSON); testes

## 3. Agente e streaming

- [x] 3.1 `AnthropicLLM.stream()` e `LLM.stream()` opcional com fallback para `chat()`; testes com cliente falso
- [x] 3.2 `JarvisBrain`: modo voz (prompt curto e por extenso), streaming de `token`, fala só do turno final, primeira frase assim que fechar, limite de duas frases, "deixa eu ver…" ao chamar ferramenta, interrupção e cancelamento; medição `t_release → t_tts_start` no log; testes com LLM falso

## 4. Interface

- [x] 4.1 Estados ouvindo/transcrevendo/pensando/falando no orbe e no cabeçalho; transcrição como pergunta; "sem fala → modo texto"
- [x] 4.2 Modo voz sem roubar o foco (mostrar sem `set_focus`, esconder 8 s depois de falar); modo texto como hoje; testes de componente

## 5. Fechamento

- [x] 5.1 `uv run pytest`, `ruff`, testes da UI; a prova do núcleo não precisa rodar (o prompt do núcleo não muda)
- [ ] 5.2 Aceite: segurar ⌘⇧Espaço, "que dia é hoje?" e "o que eu tenho amanhã?" → primeira palavra falada em menos de 3 s / 4 s (log com os tempos); `npm run tauri build` + `install_mac.sh`
- [ ] 5.3 Kaio escolhe a voz (Luciana x Luciana Aprimorada x Kokoro) e decide o "deixa eu ver…"; teste com a voz real decide se o reconhecimento nativo vira change; `SPEC.md` atualizado (captura no app, `AVSpeechSynthesizer`); arquivar
