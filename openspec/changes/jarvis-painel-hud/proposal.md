## Why

O Kaio aprovou em 10/10/2026 a maquete do painel no estilo HUD do J.A.R.V.I.S.: azul-marinho, anéis, medidores e linhas finas (maquete: claude.ai/artifact/FtWvJdN6FFMtU6pnpPqCSu; referências em `jarvis-ui/referencias-visuais/01-…` e `02-…`). O painel atual mostra os mesmos dados em colunas planas. Ele também pediu que **o orbe se mexa sempre que o Jarvis responder**. Hoje o orbe muda pouco entre "parado" e "falando" (velocidade 0,12 contra 0,30), e a voz não aparece nele.

## What Changes

- **Painel redesenhado, como na maquete:**
  - **centro:** o orbe dentro de anéis com marcações (estilo reator). Em volta, botões de modo. Embaixo, a última conversa, o campo de pedido e a música que está tocando;
  - **esquerda:**
    - anel de data e relógio, com o próximo compromisso;
    - medidores do Mac (memória livre, swap, bateria);
    - terminais com o estado de cada um;
    - fatura como anel (dias até fechar, total, vencimento e total do mês);
  - **direita:**
    - agenda de hoje numa linha do tempo, com o próximo compromisso aceso;
    - lançador de projetos;
    - medidor de clima de Brasília;
  - **estilo:** a paleta azul-marinho atual, cantos chanfrados, grade de fundo e tipografia geométrica (Orbitron nos números, Rajdhani nos textos, Share Tech Mono nos dados), com as fontes empacotadas no app, sem rede.
- **O que já funciona nos botões e no lançador:**
  - **Resumo** fala o resumo do dia (o mesmo do "Hey Jarvis");
  - **Música** pausa e retoma o Spotify;
  - **Terminais** abre a área de terminais;
  - **cada projeto** do lançador abre um terminal na pasta dele (as pastas que o Jarvis já conhece em `JARVIS_PASTAS`).
  - Os modos que dependem de changes futuros (Boa noite, Silenciar, Estudo) não aparecem até existirem.
- **Orbe que reage à resposta:**
  - enquanto o Jarvis **fala**, o orbe pulsa no ritmo do volume real da voz. O cérebro mede o áudio que toca e manda o nível à interface, cerca de 15 vezes por segundo;
  - enquanto o texto da resposta **chega**, inclusive digitada e sem voz, o orbe acelera e brilha;
  - vale para o orbe do painel e para o do HUD;
  - parado, continua como hoje (devagar no painel, parado no HUD), e com "Reduzir movimento" fica estático.
- **Dados novos para o painel:**
  - clima (o mesmo do resumo do dia, guardado por 10 min);
  - memória, swap e bateria do Mac;
  - faixa tocando no Spotify, lida pelo AppleScript, sem login.
  - Tudo vem do cérebro, sem o modelo e sem token.

## Non-goals

- Mudar o HUD pequeno além do orbe.
- Modos de changes futuros (Estudo, Boa noite, Silenciar): entram quando cada um existir.
- Abrir projetos no VS Code (é do change "Abrir projetos e rascunhos"); aqui o lançador abre só o terminal.
- Tema claro ou outra paleta.

## Capabilities

### New Capabilities
<!-- nenhuma -->

### Modified Capabilities
- `jarvis-painel`: o conteúdo ganha clima, Mac, música, modos e lançador de projetos, no layout HUD; o orbe reage à resposta; o movimento continua acessível.
- `jarvis-interface`: o orbe do HUD também reage à fala e ao texto chegando.

## Impact

- **Interface:**
  - `Panel.tsx` e `panel.css` reescritos no layout novo, com componentes de anel (`Ring`, `Gauge`) em SVG;
  - `PanelOrb.tsx` e `Orb.tsx` reagem ao nível da voz e aos tokens;
  - fontes em `jarvis-ui/src/fonts/` (licença OFL).
- **Cérebro:**
  - `jarvis/tts.py` mede o volume (RMS) de cada pedaço tocado e emite `voice_level`, com limite de cerca de 15 por segundo;
  - `jarvis/agent.py` ou um módulo novo `jarvis/panel_extras.py` junta ao `panel` o clima, o Mac (`kern.memorystatus_level`, `vm.swapusage`, `pmset -g batt`), a faixa do Spotify e a lista de projetos;
  - eventos novos `voice_level` e, no `panel`, os campos `clima`, `mac`, `musica` e `projetos`.
- **Desempenho:** os anéis são SVG estáticos (sem animação contínua). O orbe segue os limites de CPU do `jarvis-hud-leve` e do painel; o aceite mede o painel parado e falando.
- **`SPEC.md`:** linha do Jarvis (visual HUD; orbe ligado à voz).
