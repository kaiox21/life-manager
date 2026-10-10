## Context

Motivação: ver `proposal.md`. Como a voz funciona hoje (`openspec/specs/jarvis-voz`):
- O push-to-talk captura o microfone **no webview** (`getUserMedia`, `MicCapture`) só enquanto ⌘⇧Espaço está segurado.
- O PCM vai por WebSocket ao cérebro, que corta o silêncio (Silero VAD) e transcreve com `mlx-whisper`.
- O cérebro roda sob o launchd. O Mac tem 16 GB de RAM e o swap vive quase cheio.

### Fatos conferidos (10/10/2026)

**Documentação oficial:**
- **openWakeWord** (github.com/dscripka/openWakeWord, PyPI):
  - versão 0.6.0, de 02/2024, com último commit em 12/2025;
  - o código é Apache 2.0, mas os modelos prontos são **CC BY-NC-SA 4.0** (não comerciais);
  - só existe "hey jarvis" (não existe "jarvis" sozinho), e o treino é só em inglês;
  - a meta é menos de 0,5 falso aceite por hora.
- **Picovoice Porcupine** (FAQ, PyPI `pvporcupine` 4.0.3): tem o "jarvis" pronto e suporte a português, mas **não tem plano pessoal ou não comercial**, só um teste gratuito "for enterprise developers", único, que exige chave e valida pela internet.
- **sherpa-onnx** (github.com/k2-fsa/sherpa-onnx):
  - Apache 2.0, versão 1.13.8 (09/2026), ativo;
  - a detecção de palavras-chave aceita **vocabulário aberto**: a palavra é escrita em texto, sem treino;
  - os modelos são em inglês (GigaSpeech, 3,3 M parâmetros); não há modelo em português.
- **Apple:**
  - o `SFSpeechRecognizer` tem "a one-minute limit on audio duration";
  - não existe API pública de palavra de ativação personalizada.
- **Ponto laranja** (Apple Support, Mac Help): "An orange dot… indicates the microphone on your Mac is in use". Com escuta contínua, ele fica aceso o tempo todo, e não há como esconder.
- **Permissão de microfone para processo do launchd** (Quinn, Apple Developer Forums, thread 756510):
  - "if you run the tool as a launchd daemon then launchd is not considered the tool's responsible code";
  - o algoritmo "is not documented… may well change";
  - um Python solto num LaunchAgent não tem uma identidade estável para essa permissão.

**Na prática** (scratchpad; áudio do `say` do macOS a 16 kHz):
1. **openWakeWord "hey jarvis":**
   - em inglês, "Hey Jarvis" e "Jarvis, what time is it" deram pico de 0,999 e 0,998;
   - com vozes pt-BR do macOS (Luciana e outra), **0 de 12** frases ("Jarvis", "Jarvis, que horas são?", "Ô Jarvis…", "Bom dia Jarvis"…), com picos de 0,002 a 0,06 e limiar de 0,5;
   - custou 2,25 ms de CPU a cada 80 ms (~2,8% de um núcleo), com 186 MB no processo de teste.
2. **sherpa-onnx**, com as palavras `JARVIS`, `JARVES`, `JAR VIS` e `JAVIS`:
   - **8 de 12** frases pt-BR detectadas;
   - acertou todas que **começam** com "Jarvis", em "Ô Jarvis…" e "Jarvis, quanto eu gastei…";
   - errou "Ei Jarvis…" e "Bom dia Jarvis";
   - custou cerca de 1,7 ms a cada 100 ms (~1,7% de um núcleo), com 100 MB no processo de teste.
3. **Alarmes falsos:** ~3,5 min de fala pt-BR sem a palavra (finanças, faculdade, jornal, receita), em duas vozes, deram **0** nos dois motores.
4. **Voz sintética não é a voz do Kaio:** a calibração final (limiar e variantes da palavra) precisa de gravações dele (tarefa 4.1).

## Goals / Non-Goals

**Goals:**
- Detectar "Jarvis, …" dito pelo Kaio com pelo menos 90% de acerto.
- No máximo cerca de 1 alarme falso por hora de conversa ou vídeo em português.
- Menos de 5% de um núcleo de CPU e menos de 100 MB a mais de memória.
- Nenhum áudio fora do Mac.

**Non-Goals:**
- treinar modelo;
- palavra no meio da frase;
- interromper a fala dizendo "Jarvis".

## Decisions

1. **Motor: sherpa-onnx, detecção de palavras-chave com o modelo inglês de 3,3 M parâmetros (int8).**
   - É o único testado que pegou a pronúncia brasileira sem treino.
   - Não precisa de chave nem de rede, tem licença Apache 2.0 e é ativo.
   - As palavras são escritas em texto, com variantes de pronúncia: `JARVIS`, `JARVES`, `JAR VIS` e `JAVIS`. A tarefa 4.1 pode acrescentar ou tirar variantes conforme a voz do Kaio.
   - O limiar (`keywords_threshold`) e o peso (`keywords_score`) ficam no `.env`, para calibrar sem mudar o código.
   - O modelo (~19 MB) é baixado pelo `install_mac.sh` para `~/Library/Application Support/Jarvis/kws/`, com o hash conferido.
   - Alternativas:
     - openWakeWord, que deu 0 de 12 em pt-BR e tem modelo não comercial;
     - Porcupine, sem plano pessoal, com chave e internet;
     - Apple Speech, com limite de 1 min (transcrição contínua seria pesada demais);
     - Vosk, um reconhecedor completo, mais pesado e com mais alarmes falsos;
     - treinar um modelo próprio, que fica para depois, se a tarefa 4.1 falhar.

2. **Captura no app, em Rust (`cpal`)**, não no webview nem no Python.
   - A permissão de Microfone já é do Jarvis.app (`NSMicrophoneUsageDescription`), e a spec "Áudio local" exige captura pelo app.
   - Alternativas descartadas:
     - O cérebro com `sounddevice`: sob o launchd, a identidade da permissão é incerta (fato da Apple acima).
     - O webview: o HUD fica escondido quase o tempo todo, e não está documentado se o `getUserMedia` e o `AudioWorklet` seguem estáveis numa janela escondida por horas.
   - Detalhes da captura:
     - uma thread no Rust abre o dispositivo de entrada padrão, converte para 16 kHz mono Int16 e manda blocos de 100 ms ao cérebro;
     - o envio é por um cliente WebSocket próprio (`tungstenite`), que lê porta e token do `session.json`;
     - o quadro é binário: `0x10` + PCM.
   - Escuta desligada = stream fechado = ponto laranja apagado.
   - Se o cérebro estiver fora, o Rust tenta reconectar a cada 5 s e descarta o áudio nesse meio-tempo.

3. **Detecção no cérebro (`jarvis/wake.py`):**
   - **porteiro:** o Silero VAD (já carregado para a voz) olha cada bloco, e o detector só recebe áudio enquanto há voz, com 0,5 s de folga antes;
   - **buffer:** um buffer circular de 1,5 s guarda o começo da frase;
   - **ao detectar:**
     - o cérebro manda `wake` ao cliente do Rust, que faz o mesmo que o atalho de voz faz hoje. Ele decide entre HUD e painel (só o Rust sabe se o painel está aberto): mostra o HUD sem foco e pega o Esc, ou deixa o painel, e emite `jarvis://wake` com o alvo;
     - **os eventos do turno vão para as interfaces, não para quem detectou.** Hoje, os eventos de um turno (`heard`, `step`, `token`, `card`, `confirm`, `done`) vão só para a conexão que o começou. Um turno aberto pela palavra é começado pela conexão do Rust, que não desenha nada. Por isso ele usa o `broadcast` do servidor para as interfaces (HUD e painel; a escondida ignora). A resposta a um `confirm` já é global (`confirm_id`), então qualquer uma das duas pode confirmar. A conexão do Rust é marcada como "escuta" e não recebe esses eventos;
     - junta o áudio a partir da palavra até 0,8 s de silêncio (VAD) ou 15 s no máximo;
     - transcreve com o `mlx-whisper` e tira o "Jarvis" do começo ("Jarvis,", "Jarvis.", "Ô Jarvis");
     - segue por `brain.ask(..., mode="voz")`;
     - texto vazio depois de tirar o nome vira "esperando o pedido": até 6 s de escuta pelo VAD; sem fala, `no_speech`.
   - O áudio da escuta só vive no buffer circular; nada vai para disco.
   - **Log:** a cada ativação, `wake: confiança=…` (sem áudio e sem texto).

4. **Pausas:**
   - Enquanto `speaking` = verdadeiro (o cérebro já sabe disso pela fala) e por mais 0,5 s depois, os blocos são descartados.
   - Também são descartados entre `voice_start` e `voice_end` do push-to-talk, e durante um turno em andamento. Assim o Jarvis não se ativa com a própria voz nem duas vezes no mesmo pedido.

5. **Liga e desliga:**
   - item marcável "Ouvir 'Jarvis'" no menu da barra (Rust), guardado em `~/Library/Application Support/Jarvis/config.json` (`"escuta": true|false`);
   - ao instalar, a escuta vem **ligada** (foi o pedido do Kaio). O ponto laranja aparece desde o login, e o menu desliga;
   - o Rust abre ou fecha o stream na hora e avisa o cérebro (`wake_listen` on/off), que descarta o estado do detector.

6. **Memória:**
   - o `sherpa-onnx` e o modelo int8 somam ~19 MB em disco. O processo de teste inteiro, com numpy e o runtime, ficou em 100 MB; no cérebro, que já carrega numpy, a estimativa é de +40 a 60 MB;
   - o aceite mede antes e depois;
   - o detector é criado só com a escuta ligada.

7. **Revisão de 10/10/2026: só voz e resumo do dia** (pedido do Kaio depois do primeiro teste real: "não quero que abra o HUD; falo 'hei Jarvis' e ele abre falando meus compromissos de hoje, quantos graus está etc.").
   - **Painel no lugar do HUD** (o Kaio pediu o painel depois de testar só voz): o `wake` no Rust chama `show_panel` (o mesmo do ⌥⇧Espaço, na thread principal) quando o painel está fechado, e não chama mais `place_and_show`. A interface escondida continua recebendo os eventos do turno (o `broadcast`) e toca a fala como hoje; o painel, se aberto, mostra a conversa. O Esc do HUD não vale para a palavra; para interromper, continua o atalho de voz.
   - **"Só o nome" = resumo**, no lugar de "abrir ouvindo e esperar o pedido". `wake_turn` devolve `so_nome`; o `WakeService` pede ao cérebro `brain.briefing(rid, emit)` e, quando a fala termina, entra em "esperando o pedido" (6 s), como antes.
   - **Texto fixo, sem LLM** (zero token, sem latência do modelo, igual ao "resumo do dia" do WhatsApp em `lembretes`): `jarvis/briefing.py` monta o texto a partir de:
     - `painel` do núcleo (MCP), que já traz agenda de hoje e faturas abertas;
     - Open-Meteo (`/v1/forecast`, `current=temperature_2m`, `daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max`, fuso `America/Sao_Paulo`), conferido em 10/10/2026: responde sem chave; timeout de 2 s; `JARVIS_CLIMA_LAT`/`JARVIS_CLIMA_LON`/`JARVIS_CLIMA_NOME` no `.env`, padrão Brasília (-15,79; -47,88);
     - pedidos de permissão pendentes de `jarvis/permissions.py`.
   - O texto sai pelos eventos de sempre (`heard` vazio não; `token` com o texto e `done`), então a fala usa o mesmo TTS e o mesmo controle de "falando" que pausa a escuta.
   - Cumprimento: "Bom dia" até 12h, "Boa tarde" até 18h, "Boa noite" depois. Horários falados como "às 14h" / "às 14h30". Máximo de 5 compromissos falados ("e mais 2").
   - Alternativa descartada: pedir o resumo ao modelo. Custaria tokens e uns 3 s a cada "Hey Jarvis", e poderia errar números (regra 3 do projeto).

## Risks / Trade-offs

- **[A voz real do Kaio pode não bater com o modelo inglês]** → calibração com gravações dele (tarefa 4.1): limiar, variantes e meta de 90%. Se não chegar lá, o plano B é treinar um modelo próprio (fora deste change).
- **[Alarmes falsos com vídeo, reunião ou TV]**:
  - a palavra precisa abrir a frase;
  - o limiar é calibrado;
  - um alarme falso só abre o HUD e transcreve um trecho curto. Nada é executado sem pedido, e ações que gravam têm as confirmações de sempre;
  - o log permite medir.
- **[Ponto laranja sempre aceso]** → é o aviso do sistema, aceito pelo Kaio ao pedir a escuta; o menu desliga.
- **[Privacidade: microfone aberto o tempo todo]:**
  - o áudio fica num buffer circular de 1,5 s na memória e não vai para disco nem para a rede;
  - só o pedido depois da palavra é transcrito, localmente.
- **[CPU e bateria]** → VAD como porteiro e detector de ~1,7% de um núcleo; o aceite mede com a Monitor de Atividade.
- **[Swap cheio]** → +40 a 60 MB estimados; o aceite mede, e o detector só existe com a escuta ligada.
- **[Dois capturadores ao mesmo tempo]** (o Rust da escuta e o webview do push-to-talk) → o macOS permite. Os blocos da escuta são descartados durante o push-to-talk.
- **[Cérebro fora]** → o Rust descarta o áudio e reconecta; nada se acumula.
- **[Permissão de Microfone pedida de novo depois de cada build]** → a permissão é do Jarvis.app, e um build com assinatura diferente pode fazer o macOS perguntar de novo. É o mesmo que já acontece com o push-to-talk; o aceite confere que a captura do Rust usa a mesma permissão, sem um pedido novo além do de sempre.
- **[Resumo comprido demais]** → no máximo 5 compromissos e partes vazias omitidas; o aceite confere se fica em ~15 s.
- **[Clima fora]** → timeout de 2 s e o resumo segue sem o clima.
- **[Latência]** → o pedido só é transcrito depois de 0,8 s de silêncio, o equivalente a soltar o atalho. O resto do caminho é o da voz de hoje; o aceite mede o tempo do fim da fala até a primeira palavra.

## Open Questions

- Variantes da palavra e limiar finais: saem da calibração com a voz do Kaio (tarefa 4.1) e são registrados aqui.

## Registro da implementação (10/10/2026)

- O `sherpa-onnx` 1.13.8 precisa do pacote `sherpa-onnx-core`, que traz o `libonnxruntime.dylib`. O lock do projeto não o puxou sozinho, então ele entrou como dependência explícita no extra `jarvis`.
- O detector de voz (Silero) da escuta é uma **instância própria**: ele guarda estado entre blocos, e o corte de silêncio da voz zera o estado a cada uso.
- **Proteção a mais contra alarme falso:** se a transcrição do trecho não começa com o nome ("Jarvis", "Jarbas", "Javis"…), o turno é descartado (`no_speech`) e registrado no log, sem chamar o modelo.
- **Testes:**
  - 413 em Python, com 23 da escuta. Um deles usa o modelo real com áudio do `say` em pt-BR: achou "Jarvis, abre o Spotify" e ignorou uma frase comum;
  - 46 na interface;
  - 2 no Rust (reamostragem e mistura de canais).
- **Primeira instalação:**
  - a conexão de escuta caía com "keepalive ping timeout". O `sample` do app mostrou a thread de escuta parada em `AudioUnitSetProperty` → CoreAudio: o macOS segura a abertura do microfone até a pergunta de permissão ser respondida, e um build novo muda a assinatura e faz o macOS perguntar de novo;
  - correção: abrir o microfone **antes** de conectar ao cérebro, e despachar o pong do keepalive a cada volta, com ou sem áudio;
  - 5 s de microfone mudo vão para o `ui.log`.
