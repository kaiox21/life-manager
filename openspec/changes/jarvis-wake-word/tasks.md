## 1. Detector no cérebro

- [x] 1.1 Dependência `sherpa-onnx` no extra `jarvis` do `pyproject.toml`; `install_mac.sh` baixa o modelo de detecção (gigaspeech 3,3 M, int8) para `~/Library/Application Support/Jarvis/kws/` conferindo o hash; teste do download com arquivo falso e hash errado (recusa)
- [x] 1.2 `jarvis/wake.py`: VAD como porteiro, buffer circular de 1,5 s, detector com variantes e limiar do `.env` (`JARVIS_WAKE_*`), pausas (falando + 0,5 s, push-to-talk, turno em andamento), juntar o pedido até 0,8 s de silêncio ou 15 s, tirar "Jarvis" do começo, "esperando o pedido" por 6 s; log de cada ativação sem áudio nem texto; testes com os áudios do `say` (positivos, negativos, pausas, só o nome, só o nome e silêncio)
- [x] 1.3 Servidor: conexão "escuta" (do Rust) com quadros `0x10` (PCM) e `wake_listen` on/off; `wake` vai só ao cliente do Rust; o turno aberto pela palavra segue por `brain.ask(mode="voz")` com os eventos mandados às interfaces (`broadcast`, sem a conexão de escuta) e `confirm` respondível por qualquer uma; testes em `test_server.py` e `test_voice.py`

## 2. App (Rust)

- [x] 2.1 Captura com `cpal` (dispositivo de entrada padrão, 16 kHz mono Int16, blocos de 100 ms) e cliente WebSocket (`tungstenite`, porta e token do `session.json`, reconecta a cada 5 s, descarta áudio sem conexão); stream fechado com a escuta desligada
- [x] 2.2 Item marcável "Ouvir 'Jarvis'" no menu da barra, guardado em `config.json` (`escuta`), ligado por padrão na instalação; abre/fecha o stream na hora e avisa o cérebro
- [x] 2.3 `wake` no Rust faz o que o atalho de voz faz (HUD sem foco com Esc, ou o painel se aberto) e emite `jarvis://wake` com o alvo; as interfaces mostram "ouvindo" e recebem o turno pelos eventos do `broadcast`; testes de componente (`npx vitest run`)

## 5. Revisão: só voz e resumo do dia (10/10/2026)

- [x] 5.1 `jarvis/briefing.py`: texto fixo do resumo (cumprimento pela hora, clima Open-Meteo com timeout de 2 s e `JARVIS_CLIMA_*`, compromissos de hoje até 5, faturas que fecham/vencem em 3 dias, permissões pendentes; partes vazias omitidas; sem rede → sem clima; núcleo fora → "agenda indisponível"); testes com relógio fixo e respostas falsas (sem rede)
- [x] 5.2 `brain.briefing(rid, emit)` falando pelos eventos de sempre; `WakeService`: "só o nome" → resumo → "esperando o pedido" depois da fala; testes
- [x] 5.3 Rust: `wake` abre o painel (não o HUD, sem pegar o Esc), que mostra a conversa; `NSMicrophoneUsageDescription` atualizado para a escuta contínua; testes

## 3. Fechamento técnico

- [ ] 3.1 `uv run pytest`, `uv run ruff check . && uv run ruff format .`, `npx vitest run`, `openspec validate --all --strict`, `npm run tauri build -- --bundles app` e `bash jarvis/install_mac.sh`; a prova do núcleo (`uv run pytest -m eval`) não precisa rodar porque o núcleo e seus prompts não mudam

## 4. Calibração e aceite com o Kaio

- [ ] 4.1 Calibração com a voz do Kaio: script `jarvis/wake_calibrar.py` grava 20 frases "Jarvis, …" e 5 minutos de fala normal dele sem a palavra (o áudio fica só numa pasta temporária e é apagado no fim), mede acertos e alarmes falsos por limiar e variante, e grava o resultado no `design.md`; meta: ≥ 90% de acertos e 0 alarmes falsos nos 5 minutos
- [ ] 4.2 Aceite real, com memória e CPU anotadas antes e depois (Monitor de Atividade, `kern.memorystatus_level`):
  - "Jarvis, o que eu tenho amanhã?" com outro app em primeiro plano (o painel abre, resposta falada);
  - "Hey Jarvis" sozinho: resumo do dia falado (clima, compromissos) em ~15 s; e depois um pedido sem repetir o nome;
  - "Hey Jarvis" sem internet (resumo sem clima);
  - painel aberto;
  - desligar e ligar pelo menu (ponto laranja some e volta);
  - reiniciar e a escolha lembrada;
  - resposta que diz "Jarvis" sem se ativar;
  - push-to-talk com a escuta ligada;
  - uma hora de uso normal com vídeo ou conversa e o log de ativações;
  - tempo do fim da fala até a primeira palavra da resposta;
  - nenhum pedido novo de permissão de Microfone além do de sempre
- [ ] 4.3 `SPEC.md` (decisão da palavra de ativação: motor, privacidade, ponto laranja; fecha "push-to-talk antes de wake word") e `/opsx:archive`
