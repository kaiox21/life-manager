## Context

- **Painel atual** (`jarvis-ui/src/Panel.tsx`, `panel.css`, `components/PanelOrb.tsx`): orbe de 500 partículas num canvas (30 fps ativo, 20 fps parado), colunas de agenda, gastos por categoria, faturas e registro, e conversa embaixo do orbe. Os dados vêm do evento `panel` (`brain.panel` → `painel` do núcleo pelo MCP, mais as perguntas da sessão).
- **HUD** (`components/Orb.tsx`): parado sem atividade (change `jarvis-hud-leve`, < 5% de CPU).
- **Voz:** quem toca é o cérebro (`jarvis/tts.py`). A Fish Audio vai por `PortAudioOut.write(pcm)` (Int16, 24 kHz, em pedaços), e a reserva é o `say` do macOS (um subprocesso, sem acesso ao áudio). A interface hoje só recebe `speaking on/off`.
- **Maquete aprovada (10/10/2026):** claude.ai/artifact/FtWvJdN6FFMtU6pnpPqCSu, 1440×900.
- **A maquete não tinha** os gastos por categoria nem o registro, que a spec atual exige. Eles continuam: as categorias entram no cartão do mês (decisão 2), e o registro fica numa aba da conversa.

## Goals / Non-Goals

**Goals:**
- O layout da maquete com os dados reais.
- O orbe ligado à fala real.
- CPU no mesmo patamar de hoje com o painel parado.

**Non-Goals:** ver a proposta.

## Decisions

1. **Grade da tela.**
   - Colunas `minmax(300px, 23%) 1fr minmax(300px, 23%)`, com o centro em `min(42vw, 640px)`. O painel abre em tela cheia em qualquer monitor (`show_panel` já usa o tamanho do monitor).
   - Em telas baixas (menos de 820 px de altura), os cartões das colunas encolhem e a lista da agenda rola dentro do cartão. Nada sai da tela.
   - Alvos de clique com pelo menos 44 px.

2. **Cartões:**

   | Coluna | Cartão | Conteúdo |
   | --- | --- | --- |
   | esquerda | **Relógio** | anel do dia do mês, hora, dia da semana e próximo compromisso |
   | esquerda | **Mac** | 3 medidores em anel: memória livre (%), swap (GB usados) e bateria (%, com carregando) |
   | esquerda | **Terminais** | número, pasta, tipo e estado, com cor por estado (os mesmos dados de hoje) |
   | esquerda | **Mês** | anel da fatura do cartão que fecha primeiro (fração do ciclo, dias até fechar), total, vencimento e total do mês; até 4 barras de categoria e "outras" |
   | centro | **Orbe** | orbe, anéis de marcação e os modos em volta |
   | centro | **Conversa** | abas **Conversa** e **Registro**; campo de pedido e botão de voz; faixa da música |
   | direita | **Agenda** | linha do tempo de hoje com o próximo aceso, e depois os próximos 7 dias |
   | direita | **Projetos** | lista das pastas de `JARVIS_PASTAS` |
   | direita | **Clima** | medidor da temperatura (escala de 0 a 40 °C), condição, máxima e mínima, e chuva |

   - Mais de um cartão de crédito: o anel mostra o que fecha primeiro, e os outros aparecem em linhas abaixo, com o total e a data.

3. **Anéis e medidores em SVG, parados.**
   - Componentes `Ring` (arco proporcional com marcações) e `Gauge` (arco de 270°).
   - O valor muda com `stroke-dasharray`, numa transição de 300 ms, só quando o dado muda. Não há animação contínua.
   - Os padrões de marcação são gerados uma vez (memo).

4. **Orbe ligado à voz.**
   - **Cérebro:** `FishSynth` calcula o RMS de cada pedaço escrito em `PortAudioOut` e emite `voice_level(n)`, com `n` de 0 a 1 normalizado pela média móvel. O envio tem limite de 15 por segundo e é atrasado pela latência da saída (`out.latency`), para o pulso coincidir com o som e não com o download.
   - Na reserva local (`say`), não há como medir o áudio. A interface usa um pulso sintético de cerca de 3 Hz enquanto `speaking` estiver ligado.
   - **Interface:** `PanelOrb` e `Orb` recebem `voiceLevel`, suavizado com ataque de 60 ms e soltura de 180 ms. Ele modula o raio (até +12%), o brilho do núcleo e a velocidade.
   - **Respondendo:** a cada `token`, o orbe recebe um impulso que decai em 400 ms. Com texto chegando seguido, ele fica rápido e brilhante; sem voz (texto digitado), é isso que move o orbe.
   - **Reduzir movimento:** nada disso se aplica, e o orbe fica estático.

5. **Dados locais junto do `panel`.**
   - Um módulo novo, `jarvis/panel_extras.py`, monta os dados em paralelo com o `painel` do núcleo:
     - **clima:** `briefing.fetch_weather`, guardado por 10 min;
     - **mac:**
       - memória por `kern.memorystatus_level` (função existente);
       - swap por `sysctl vm.swapusage`;
       - bateria por `pmset -g batt`, lida por expressão regular (%, se está carregando);
     - **música:** AppleScript, só se o Spotify estiver aberto (`is running`): nome, artista e estado. Timeout de 2 s;
     - **projetos:** os nomes das pastas de `Folders`.
   - Cada parte que falhar vira `null` (o cartão mostra "indisponível").
   - Os **dias até fechar** são calculados no cérebro a partir de `fechamento` (que já vem pronto do núcleo) e da data de hoje.
   - Atualização: igual à de hoje (60 s e depois de turnos que gravam). Fechado, não busca.

6. **Modos.**
   - **Resumo** manda `{"type":"briefing"}` ao cérebro, que roda `brain.briefing` com os eventos para a interface.
   - **Música** manda `{"type":"local","acao":"musica_tocar_pausar"}`, que chama `controlar_musica` direto, sem o modelo.
   - **Terminais** abre a área de terminais (estado da interface).
   - **Projeto:** um clique chama `control.open(pasta, claude=False)` (o mesmo caminho do "abrir terminal" de hoje).
   - Uma lista no código define quais modos aparecem. Os changes futuros acrescentam os deles.

7. **Fontes empacotadas.** Orbitron, Rajdhani e Share Tech Mono (todas OFL), em `woff2` dentro do app, com `font-display: swap`. Nenhuma requisição ao Google Fonts no app.

## Risks / Trade-offs

- **[CPU com o pulso da voz]** → o orbe já anima a 30 fps quando está ativo. O pulso só muda parâmetros, sem mais partículas. O aceite mede o painel parado (meta: igual a hoje) e falando.
- **[Pulso fora de sincronia]** → o atraso pela latência da saída. Se ainda ficar perceptível, ajusta-se um deslocamento fixo no aceite.
- **[Reserva `say` sem nível real]** → pulso sintético. É raro, porque a Fish é a voz principal.
- **[Tela pequena]** → a regra das colunas mínimas e a rolagem dentro dos cartões. O aceite confere no monitor do MacBook (1470×956) e num externo.
- **[Muitos dados disputando atenção]** → hierarquia de brilho: o próximo compromisso e os valores principais em branco, o resto em azul apagado, como na maquete.

## Open Questions

- Nenhuma.
