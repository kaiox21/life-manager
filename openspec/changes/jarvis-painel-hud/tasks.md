## 1. Cérebro

- [ ] 1.1 `voice_level`: RMS de cada pedaço tocado em `FishSynth`/`PortAudioOut`, normalizado, no máximo ~15/s, atrasado pela latência da saída; evento novo em `events.py` (documentado); testes com saída falsa
- [ ] 1.2 `jarvis/panel_extras.py`: clima (cache 10 min), Mac (`kern.memorystatus_level`, `vm.swapusage`, `pmset -g batt`), Spotify (AppleScript só se aberto, 2 s), projetos (`Folders`), dias até fechar por cartão; cada parte falha para `null`; junto do `panel`; testes com executores falsos
- [ ] 1.3 Mensagens `briefing` e `local` (só `musica_tocar_pausar`) no servidor e abrir terminal por pasta pelo lançador; testes

## 2. Interface

- [ ] 2.1 Fontes OFL empacotadas (`woff2`) e tokens do tema HUD (cartão chanfrado, cantos, grade de fundo) em `theme.css`/`panel.css`
- [ ] 2.2 Componentes `Ring` e `Gauge` (SVG, marcações memorizadas, transição só na mudança do valor); testes de componente
- [ ] 2.3 `Panel.tsx` no layout da maquete: relógio, Mac, terminais, mês (anel da fatura + categorias + outros cartões), orbe com anéis e modos, conversa com abas Conversa/Registro, faixa da música, agenda em linha do tempo, projetos, clima; indisponível por cartão; telas baixas; testes (`Panel.test.tsx` atualizado)
- [ ] 2.4 Orbe reagindo: `voiceLevel` (ataque/soltura), impulso por `token`, pulso sintético com `say`, sem nada com "Reduzir movimento"; em `PanelOrb` e `Orb`; testes

## 3. Fechamento

- [ ] 3.1 `uv run pytest`, `uv run ruff check . && uv run ruff format .`, `npx vitest run`, `openspec validate --all --strict`, `npm run tauri build -- --bundles app`, `bash jarvis/install_mac.sh`
- [ ] 3.2 Aceite real com o Kaio: painel igual à maquete com dados reais no MacBook e num monitor externo; orbe pulsando com a voz (pergunta falada) e acelerando com texto (pergunta digitada); botões Resumo, Música, Terminais e um projeto; sem internet (clima indisponível); "Reduzir movimento" ligado; CPU do painel parado e falando anotada (Monitor de Atividade, app + WebKit)
- [ ] 3.3 `SPEC.md` (Jarvis: visual HUD, orbe ligado à voz) e `/opsx:archive`
