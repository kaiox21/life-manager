## Context

O Jarvis hoje tem uma janela só (`main`, o HUD de 760×560, transparente, sempre no topo), dois atalhos globais (⌥Espaço texto, ⌘⇧Espaço voz) e um cérebro Python que fala com o núcleo só pelo MCP e com a interface por WebSocket local (vários clientes podem conectar; o histórico de conversa é do cérebro, não da conexão). O núcleo já tem as consultas (`buscar_eventos` com recorrência expandida, `resumo_gastos` em SQL, `total_fatura` com a regra de `app/domain/billing.py`) e a função `open_statement_month` que define a fatura aberta. Motivação e escopo: ver `proposal.md`.

Referência visual: `jarvis-ui/referencias-visuais/01-print-2026-10-08-18.07.png` (azul profundo com grade, orbe de partículas com anéis e marcações, colunas laterais com listas finas, valor em destaque embaixo do orbe, cantos com colchetes).

## Goals / Non-Goals

**Goals:**
- Abrir em menos de 300 ms (janela pré-carregada, dados em seguida) e mostrar dados em menos de 1 s com o núcleo no ar.
- Zero tokens para abrir e atualizar.
- Consumo baixo: nada roda com o painel fechado; aberto, animação a 60 fps sem esquentar o MacBook Air (sem ventoinha, então CPU baixa importa).

**Non-Goals:**
- Responsividade para telas pequenas ou janelas redimensionáveis: o painel é tela cheia em monitores a partir de 1280×800.
- Tema claro: o painel é sempre escuro (estilo holográfico), como o HUD.

## Decisions

1. **Ferramenta `painel` no núcleo, só no MCP, chamada sem o modelo.** O cérebro chama `painel` direto pelo cliente MCP quando a interface pede (`{"type":"panel"}`) e devolve o JSON num evento `panel`. Alternativas: (a) o cérebro chamar `buscar_eventos`, `resumo_gastos` e `total_fatura` um a um: obriga o cérebro a saber qual é a fatura aberta de cada cartão (regra de fatura fora do núcleo, contra a regra 3) e faz 2 + N chamadas; (b) a interface ler o `contexto`: é texto para modelo, não dado. A `painel` reusa as funções das ferramentas existentes por dentro, então os números batem com os da conversa por construção. Fica fora dos grupos do agente do WhatsApp e é registrada como `contexto` (direto no servidor, sem o `_wrap`): o `_wrap` grava `agent_runs` e chama o sync do Google Calendar a cada chamada, inclusive de leitura, o que com atualização a cada 60 s daria 60 linhas e 60 syncs por hora de painel aberto. O cérebro também tira `painel` da lista de ferramentas que entrega ao modelo (o resultado é grande e não ajuda numa conversa; o modelo já tem `contexto` e as consultas).

2. **Formato da `painel`** (centavos ao lado do texto formatado pelo núcleo):
   ```json
   {"agora": "2026-10-09T14:03:00-03:00",
    "agenda": {"hoje": [...], "proximos": [...]},          // mesmo item de buscar_eventos, 7 dias
    "mes": {"periodo": "01/10/2026 a 09/10/2026", "total": "R$ 0,00", "total_centavos": 0, "grupos": [{"grupo": "Alimentação", "total": "R$ 0,00", "total_centavos": 0, "lancamentos": 0}]},
    "faturas": [{"cartao": "Nubank", "mes_vencimento": "2026-11", "fechamento": "31/10/2026", "vencimento": "08/11/2026", "situacao": "aberta", "total": "R$ 0,00", "total_centavos": 0, "lancamentos": 0}],
    "registro": [{"tipo": "gasto|evento", "quando": "...", "texto": "Almoço · R$ 47,00 · Nubank", "origem": "whatsapp|mac|null"}]}
   ```
   Na implementação (09/10/2026), `agenda`, `mes` e `faturas` são as saídas de `buscar_eventos`, `resumo_gastos` (de 1º do mês até hoje) e `total_fatura` (sem `maiores_itens`), então já trazem valores e datas formatados ao lado dos centavos, como na conversa. O `texto` do registro é montado no núcleo, com o valor formatado pela mesma função que formata as respostas do bot (a interface não faz conta nem formata dinheiro). Compra parcelada aparece uma vez no registro (só a 1ª parcela), como "3× de R$ 100,00". A origem do gasto vem de `messages.channel` pelo `message_id` (`whatsapp`); gasto sem mensagem veio pelo MCP e vira `mac` (pode ter sido o Jarvis ou o Claude Desktop: o núcleo não distingue, então o painel não finge saber). Eventos não têm `message_id`, então não mostram origem.

3. **Segunda janela Tauri `painel`, pré-criada e escondida.** Mesmo bundle React, com a rota escolhida pelo rótulo da janela (`getCurrentWindow().label`), sem roteador. Pré-criar evita o atraso de carregar o WebView a cada abertura. Tela cheia com `set_simple_fullscreen` (macOS, conferido no tauri 2.12.1 em 09/10/2026: `WebviewWindow::set_simple_fullscreen`), que cobre a tela sem criar um Space novo nem a animação de ~0,7 s do `set_fullscreen`. Alternativa descartada: redimensionar o HUD para a tela toda (misturaria dois layouts e dois comportamentos de foco na mesma janela).

4. **Foco e fechamento.** O painel abre com foco (para o Esc e o campo de texto) e, ao fechar, devolve o foco ao app anterior (com a política `Accessory`, esconder a janela já faz isso). Perder o foco **não** fecha o painel (diferente do HUD): o Kaio pode trocar de app e voltar. Esc ou ⌥⇧Espaço fecham.

5. **Push-to-talk vai para a janela visível.** O Rust já emite `jarvis://ptt` para todas as janelas; agora inclui `target: "painel" | "hud"`, decidido por quem está visível, e não mostra o HUD se o painel estiver aberto. Cada janela só reage ao seu alvo. ⌥Espaço com o painel aberto foca o campo do painel em vez de abrir o HUD.

6. **Uma conexão WebSocket por janela.** O servidor já aceita várias; o histórico é do cérebro, então a conversa continua igual nos dois. O registro "perguntas desta sessão" vem do cérebro (evento `panel` inclui as últimas perguntas do histórico), não do estado da janela.

7. **Atualização.** A interface pede `panel` ao abrir, a cada 60 s enquanto visível (`visibilitychange` + timer) e ao receber `done` de um turno que chamou ferramenta de escrita (o cérebro marca `wrote: true` no `done`). Fechado, o timer para e o laço de animação para (`requestAnimationFrame` só roda com a janela visível; o WebView já pausa quando escondido, mas o timer é parado explicitamente).

8. **Orbe de partículas em Canvas 2D**, ~800 pontos numa esfera com rotação lenta, e anéis/marcações em SVG com CSS. Estados (ocioso, ouvindo, pensando, falando) mudam velocidade, brilho e raio; "ouvindo" usa o nível do microfone que já existe (`levels`). Alternativas: WebGL/three.js (mais bonito, +150 KB e mais GPU; fica para depois se o Canvas não bastar); CSS puro (não chega no efeito de partículas). Com "Reduzir movimento", desenha um quadro estático.

9. **Layout em grade fixa**: topo (marca + relógio/data), esquerda (agenda), centro (orbe, pergunta/resposta, campo), direita (gastos do mês por categoria com barras finas + faturas), rodapé (registro). Valores grandes com algarismos tabulares. Barras de categoria proporcionais ao maior valor do mês: proporção é desenho, não conta de dinheiro, e o número exibido é sempre o do núcleo.

10. **Falhas.** Se `panel` falhar (núcleo ou cérebro fora), as colunas mostram "núcleo indisponível" com o horário da última atualização boa; os dados antigos ficam esmaecidos e marcados, nunca como atuais. Relógio e orbe funcionam sem o cérebro.

## Risks / Trade-offs

- **[Depende do `jarvis-voz`]** O painel usa o push-to-talk (⌘⇧Espaço) e mexe no mesmo `lib.rs`; o `jarvis-voz` ainda não foi arquivado → implementar sobre o código atual (já commitado) e arquivar o `jarvis-voz` antes do `jarvis-painel`, para os deltas entrarem na ordem certa.
- **[`painel` visível no Claude Desktop]** Toda ferramenta do MCP aparece também lá → é só leitura e inofensiva; o custo é um item a mais na lista de ferramentas do Claude Desktop.
- **[Janela escondida sempre carregada]** A janela pré-criada mantém um WebView e uma conexão com o cérebro mesmo sem nunca abrir o painel → medir na tarefa 3.2; se pesar, criar a janela no primeiro uso e mantê-la depois.
- **[Esc devolver o app anterior]** Com a política `Accessory`, esconder a janela deve reativar o app anterior, mas não foi testado com tela cheia → conferir na tarefa 3.1.

- **[Valores na tela inteira]** Painel aberto em reunião ou compartilhamento de tela expõe gastos → sob demanda e Esc rápido; ocultar valores está fora deste change (anotado nos Non-goals).
- **[CPU/bateria no MacBook Air]** Canvas a 60 fps com 800 partículas → medir na tarefa do orbe (meta: < 10% de CPU do processo WebView); se passar, baixar para 30 fps ou menos partículas.
- **[`set_simple_fullscreen` em app `Accessory`]** Comportamento com a barra de menus e o Dock ainda não testado neste app → tarefa de verificação logo no começo; plano B: janela sem bordas do tamanho do monitor com nível acima da barra de menus.
- **[Duas janelas, dois WebViews]** Mais memória (~60–100 MB pelo WebView extra), com o Mac já pressionado de swap → pré-criar só ao primeiro uso se a memória medida incomodar; medir na tarefa da janela.
- **[Atalho ⌥⇧Espaço ocupado]** Algum app pode já usar → o registro do atalho falha com erro no log; o item do menu continua funcionando.

## Migration Plan

Sem migração de banco. Ordem: ferramenta `painel` no núcleo com testes → evento `panel` no cérebro → janela e atalho → layout e orbe → aceite. Reverter é tirar a janela e o atalho; a ferramenta `painel` é somente leitura e pode ficar.

## Open Questions

- Mostrar também as faturas fechadas ainda não pagas (vencimento futuro)? Hoje o núcleo não sabe o que foi pago; a proposta é só a fatura aberta.
- Quantos itens no registro cabem bem na tela do MacBook (10 é a proposta); ajustar no aceite.

## Registro da implementação (09/10/2026)

- `painel` no núcleo responde pelo cérebro em ~0,5 s com dados reais (primeira chamada, núcleo recém-reiniciado), sem chamada ao modelo.
- Memória: a janela `painel` pré-criada acrescenta um processo WebContent de ~45 MB (medido com `ps`, app em release). Aceitável; fica pré-criada.
- Tela cheia, Esc e atalhos conferidos pelo Kaio no Mac ("funcionou", 09/10/2026).
- Layout conferido no navegador (Playwright, 1470×956, casca do Tauri simulada e dados reais do cérebro): colunas, orbe, registro e Esc chamando `hide_panel`.
- **Pendente de verificação com o Kaio** (o macOS não deixa o terminal apertar atalhos nem capturar a tela): `set_simple_fullscreen` no app `Accessory` (tarefa 3.1), atalhos e foco na prática (3.2) e CPU do orbe com o painel aberto (4.3).
- CPU com o painel aberto e parado (soma do app e dos processos do WebKit, amostras a cada 2 s por 30 s): **30% de média** na primeira versão (800 pontos a 60 fps, brilho e anéis redesenhados a cada quadro). Com 500 pontos, 20 fps parado / 30 fps em atividade e brilho e anéis desenhados uma vez e só girados: **9,2% de média** (máximo 20%). Meta (< 10%) atingida.
- Achado fora do escopo: o HUD pequeno aberto e parado gasta ~17% de CPU (anéis do orbe animados por CSS o tempo todo). Fica para um change pequeno de desempenho do HUD.
- Aceite parcial com o Kaio (09/10/2026): gasto lançado pelo WhatsApp apareceu no painel; tela cheia, atalhos e Esc conferidos antes. Falta confirmar a voz com o painel aberto atualizando as colunas.
