## Context

O Jarvis já tem: cérebro Python com protocolo de eventos (`step`, `token`, `card`, `confirm`, `done`, `error`), interface Tauri + React com ⌥Espaço e HUD, e o modelo rápido (Haiku 5.5, ~1,5 s por chamada). O protocolo foi desenhado para a voz: `token` existe e ainda não é usado. Antes de codar foi feita uma análise crítica e um teste de 1 hora (resultados no fim).

## Goals / Non-Goals

**Goals:**
- Segurar ⌥Espaço, falar, soltar e ouvir a resposta, sem perder o foco do app em uso.
- Primeira palavra falada em menos de 3 s numa pergunta simples (critério do `SPEC.md`); até 4 s com uma ferramenta.
- Tudo local, exceto o modelo de linguagem: áudio não sai do Mac e não é guardado.

**Non-Goals:**
- Wake word, mãos livres, painel de tela cheia.

## Decisions

1. **Dois atalhos, uma função cada** (revisto em 09/10/2026, a pedido do Kaio). A primeira versão usava ⌥Espaço para as duas coisas (toque = texto, segurar = voz); na prática confundia e quebrava o Esc, porque o HUD abria sem foco esperando a fala. Agora: **⌥Espaço** abre/fecha o modo texto com foco (Esc fecha); **⌘⇧Espaço segurado** é o push-to-talk: `Pressed` abre o HUD em "ouvindo" sem roubar o foco e começa a capturar; `Released` fecha a captura. Se o VAD não encontrou fala, o HUD volta a como estava. Nunca "não ouvi" como resposta. O plugin `global-shortcut` entrega os dois estados (`ShortcutState::Pressed`/`Released`, conferido na versão 2.4.0). **A conferir na tarefa 3.1:** se o macOS repete `Pressed` com a tecla segurada (auto-repeat); se repetir, ignorar repetições.
2. **Captura no WebView** (`getUserMedia` + `AudioWorklet`, mono, Int16, 16 kHz; se o `AudioContext` não aceitar 16 kHz, reamostrar no cérebro), enviada ao cérebro em quadros binários do WebSocket enquanto a tecla está segurada. Por quê: a permissão de Microfone fica no **Jarvis.app** (o ponto laranja mostra "Jarvis", não "python"), e a forma de onda é desenhada do próprio áudio. O `wry` 0.57 implementa o delegate `requestMediaCapturePermissionForOrigin` (conferido no código); `Info.plist` em `src-tauri/` com `NSMicrophoneUsageDescription` (o Tauri mescla o arquivo). **Risco a fechar na tarefa 3.1, que vem primeiro:** confirmar que o Tauri expõe o handler de permissão e que o binário de `tauri dev` carrega o `Info.plist`; se falhar, captura no Rust com `cpal` (mesma atribuição de permissão), mesmo caminho dos quadros.
3. **VAD leve antes do whisper**: `pysilero-vad` 3.4 (onnxruntime) corta silêncio nas pontas e decide "houve fala?" (decisão 1). Evita as alucinações do whisper em silêncio ("Obrigado por assistir"). Mínimo de 0,3 s de fala.
4. **Transcrição com `mlx-whisper` 0.4.3, modelo `mlx-community/whisper-large-v3-turbo-q4`** (0,64 GB de RAM residente, ~0,85 s por frase curta, mesma qualidade do fp16 no teste; o fp16 usa 1,37 GB e não transcreveu melhor). `language="pt"`, `condition_on_previous_text=False`, `initial_prompt` com os nomes cadastrados (como no núcleo). Carregado na subida (~3 s com o modelo em cache; ~80 s na primeira vez, baixando ~0,5 GB; o HUD avisa). Roda em thread. **Correção da versão anterior deste design:** `mlx-whisper` depende de `torch` e `numba` (~1,1 GB no ambiente do Mac); o "sem torch" vale só para o VAD. Extra `jarvis` no `pyproject` com marcador `sys_platform == 'darwin' and platform_machine == 'arm64'`; o Dockerfile (`uv sync --no-dev`, sem extras) não instala nada disso. Modelo trocável por `JARVIS_WHISPER_MODEL`.
   - **Alternativa condicional:** o reconhecimento nativo do macOS (`SFSpeechRecognizer`, no aparelho, pt-BR) transcreve **enquanto o usuário fala** (texto pronto ao soltar, sem download, sem RAM extra, com vocabulário via `contextualStrings`). No teste com voz sintética ele cortou as frases cedo e o resultado ficou inconclusivo. **Se o teste com a voz real do Kaio mostrar qualidade equivalente ao whisper, trocar para ele num change próprio (`jarvis-stt-nativo`)**; a transcrição ao vivo no HUD vem junto. Não bloqueia este change.
5. **Streaming no `AnthropicLLM`** (`client.messages.stream` → `text_stream`, depois `get_final_message()`), exposto como `stream()` no protocolo `LLM`, com `chat()` como fallback (o `GatewayLLM` continua só com `chat()`). O laço do Jarvis usa `stream()` e emite `token`; chamadas de ferramenta continuam saindo da mensagem final. **Só o turno final é falado**: texto que o modelo escreve antes de chamar uma ferramenta ("Vou verificar…") vira passo no log, não fala.
6. **Fala com `AVSpeechSynthesizer`** via PyObjC (`pyobjc-framework-AVFoundation`), **na thread principal do asyncio**, com o `NSRunLoop` bombeado por uma tarefa a cada 20 ms e os eventos de início/fim de cada frase vindos do **delegate** (testado em 08/10: início em 0,02 s; numa thread de fundo o delegate não dispara, e o polling de `isSpeaking` deu tempos errados). Voz `Luciana` (compacta) por padrão, velocidade configurável; `stopSpeaking` interrompe na hora. O `say` (0,8 s para sintetizar uma frase) fica só como fallback. Frases enfileiradas: a primeira começa a ser falada quando o primeiro ponto final chega no stream; **limite de duas frases faladas** (o prompt pede; o cérebro corta o excedente da fala, não do texto). "Luciana (Aprimorada)" recomendada ao Kaio (download em Ajustes → Acessibilidade → Conteúdo Falado). **Kokoro** (`mlx-audio` 0.5.8, vozes `pf_dora`/`pm_alex`, exige `espeak-ng` pelo Homebrew) é experimento opcional (`JARVIS_TTS=kokoro`) e não bloqueia o aceite.
7. **"Deixa eu ver." ao chamar ferramenta** (sem reticências: o sintetizador faz pausa longa nelas), ligado por padrão (`JARVIS_FILLER=true`): fala curta e aleatória entre três variantes, só uma vez por turno, só em modo voz. Cobre o pior trecho do orçamento (a chamada de ferramenta + a segunda chamada ao modelo).
8. **Modo voz no agente**: `ask` leva `mode: "voz" | "texto"`. Em voz, o prompt acrescenta: "responda em no máximo duas frases, sem listas nem tabelas (os detalhes estão nos cartões); escreva valores e datas por extenso para serem lidos em voz alta (quarenta e sete reais e noventa; oito de novembro; três da tarde)". A transcrição vira a pergunta do turno (`heard`) e entra no histórico como texto. Comando digitado continua respondendo em texto, como diz o `SPEC.md`.
9. **HUD em modo voz não rouba o foco**: a janela aparece por cima (`alwaysOnTop`) sem `set_focus`; o app em uso continua ativo. Esconde sozinha 8 s depois de terminar de falar (configurável). Em modo texto continua como hoje (foco no campo, some ao perder o foco).
10. **Interrupção e cancelamento**: ⌥Espaço durante a fala interrompe a fala e começa a ouvir; durante "pensando", cancela a tarefa do turno (`asyncio.Task.cancel`), com a ressalva de que uma chamada MCP já em andamento termina no núcleo. O cérebro marca o turno como cancelado (`error` com texto "cancelado").
11. **Protocolo** (acréscimos): UI → cérebro `voice_start {id}`, quadros binários PCM, `voice_end {id}`, `voice_cancel {id}`; cérebro → UI `heard {text}`, `speaking {on}`, `status {text}` ("transcrevendo…", "baixando o modelo de voz…"). `server.py` passa a distinguir quadros binários de JSON. Sem mudar os eventos existentes.
12. **Medição do aceite** no log do cérebro, por turno: `t_release → t_heard → t_first_token → t_tts_start` (o `didStart` do sintetizador marca o áudio de verdade). Meta: `t_tts_start − t_release < 3 s` sem ferramenta e ≤ 4 s com uma; o "deixa eu ver…" não conta como primeira palavra da resposta.
13. **Sem eco**: o microfone só está aberto com a tecla segurada; a fala do Jarvis nunca entra na gravação.
14. **Dois whispers** (o `faster-whisper small` no Docker para o áudio do WhatsApp e o `mlx-whisper` no Mac para o Jarvis): duplicação aceita enquanto o núcleo roda no Mac; quando o núcleo for para o VPS, continuam separados por natureza.

## Teste de 08/10/2026 (voz sintética do macOS, 8 frases com nomes de cartão e pessoa)

| | Qualidade | Latência por frase | RAM |
| --- | --- | --- | --- |
| `mlx-whisper` turbo **q4** | 8/8 corretas ("Intercrédito" junto) | ~0,85 s | 0,64 GB |
| `mlx-whisper` turbo fp16 | 7/8 (igual) | ~1,0 s | 1,37 GB |
| Apple no aparelho (`SFSpeechRecognizer`) | cortou 6/8 frases cedo (inconclusivo com voz sintética) | 0,06–0,1 s | 0 |
| `AVSpeechSynthesizer` (Luciana) | — | **primeiro áudio em 0,03–0,05 s** | — |
| `say` | — | 0,8 s só para sintetizar | — |

Os clipes gerados com a voz "Eddy" quebraram os dois motores e foram descartados como sinal de teste. Pendente: repetir com a voz real do Kaio (gravações no app Gravador).

Fatos conferidos em 08/10/2026:
- `tauri-plugin-global-shortcut` 2.4.0: `ShortcutState::Pressed`/`Released`.
- `wry` 0.57.0: delegate `webView:requestMediaCapturePermissionForOrigin:…` com `Microphone`.
- `mlx-whisper` 0.4.3 (requer `torch`, `numba`, `mlx`); `pysilero-vad` 3.4.0 (só onnxruntime/numpy); `mlx-audio` 0.5.8; Kokoro-82M lista as vozes pt-BR `pf_dora`, `pm_alex`, `pm_santa` (G2P via `espeak-ng`).
- `say -v '?'` neste Mac: pt-BR `Luciana`, `Eddy`, `Flo`, `Reed`, `Rocko`, `Sandy`, `Shelley`; a voz padrão do `AVSpeechSynthesizer` em pt-BR é `Luciana` (compacta).
- Tauri mescla `src-tauri/Info.plist` no bundle (documentado em `tauri-utils` 2.10.1).
- Mac: arm64, 16 GB de RAM.

## Risks / Trade-offs

- **[`getUserMedia` no WKWebView / permissão em `tauri dev`]** → tarefa 3.1 primeiro; fallback `cpal` no Rust.
- **[Meta de 3 s com ferramenta]** → streaming + Haiku + sintetizador quente + "deixa eu ver…"; medir e registrar.
- **[Auto-repeat do atalho segurado]** → ignorar `Pressed` repetido enquanto a captura estiver aberta.
- **[16 GB de RAM com Docker + torch + whisper]** → q4 (0,64 GB); se apertar, descarregar o modelo após 30 min parado (`JARVIS_WHISPER_IDLE_MIN`).
- **[Cancelar durante uma chamada MCP]** → a chamada termina no núcleo; o cartão não é mostrado; registrado em `agent_runs` normalmente.
- **[Qualidade da voz]** → Luciana Aprimorada e Kokoro como melhorias; decisão do Kaio depois de ouvir.

## Open Questions

- ~~Atalho~~: decidido em 09/10/2026, ⌘⇧Espaço segurado para voz; ⌥Espaço só texto.
- Voz inicial: `Luciana` serve para começar?
- Resposta falada também em modo texto digitado? (Proposta: não, como diz o `SPEC.md`.)
- Resultado do teste com a voz real: whisper q4 (decidido) ou reconhecimento nativo (change futuro)?

## Ajustes depois do primeiro uso real (09/10/2026)

- **Demora na transcrição:** no uso real, 3,7 s de fala levaram 6 s para transcrever (pesos do whisper no swap depois de um tempo parado; Mac com 14 de 15 GB de swap usados). Correção: `mx.set_wired_limit(2 GB)` na subida, para os pesos ficarem na RAM, e `prewarm` ao apertar ⌘⇧Espaço, para acordar o modelo enquanto o Kaio fala.
- **Personalidade:** o Kaio achou a voz robótica e quer "o Jarvis". O prompt agora trata o Kaio por "senhor", com tom de mordomo britânico e humor seco discreto. Enchimentos: "Um instante, senhor." / "Verificando, senhor." / "Só um momento, senhor.". Toques curtos (WebAudio) ao começar e terminar de ouvir.
- **Voz:** o Kaio ouviu e recusou Luciana, Kokoro (Alex, Santa), Piper (Faber, Cadu, Jeff) e as vozes neurais da Microsoft. Ele escolheu uma voz "Jarvis" da comunidade da Fish Audio (`FISH_VOICE_ID` só no `.env`, fora do repositório público). Recusei criar um clone da voz do ator ou do dublador; a escolha de usar uma voz pronta da comunidade, em uso privado, foi do Kaio, avisado de que é uma imitação de uma pessoa real e de que o texto das respostas passa pela Fish Audio.
  - Backend `FishSynth`: `POST https://api.fish.audio/v1/tts` (cabeçalho `model: s2.1-pro-free`, gratuito; corpo `text`, `reference_id`, `format: mp3`, `latency: balanced`, `prosody.speed`), conferido em docs.fish.audio em 09/10/2026. Uma requisição por frase, pedida assim que a frase fecha (a próxima baixa enquanto a anterior toca) e tocada em ordem com `AVAudioPlayer`.
  - Falhou a rede ou a API: a frase e o resto da resposta vão para a voz local (`AVSynth`), e a Fish fica de lado por 5 minutos.
  - Isso muda a decisão "voz local" do `proposal.md`: a transcrição continua local; a fala vai para a nuvem só quando houver `FISH_API_KEY`.
- **Configuração:** `jarvis/__main__.py` agora lê `JARVIS_*` e `FISH_*` do ambiente e, na falta, do `.env`. Antes, os `JARVIS_*` só valiam se exportados no ambiente; o `.env` era ignorado.
- **Medição com o microfone real e a voz da Fish (09/10/2026, perguntas com ferramenta):** fala→texto 0,6–0,7 s; "Um instante, senhor." em 2,4–2,7 s; primeira frase da resposta em 4,7–5,2 s. A meta de ≤ 4 s com ferramenta ainda não é atingida pela resposta, só pelo enchimento; o que sobra é a Fish gerar a frase inteira (~1 s) antes de tocar. Próximo ganho possível: tocar o áudio enquanto ele chega (~0,5 s). O Kaio aprovou o resultado assim ("está ótimo").
