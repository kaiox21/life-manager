## Why

O HUD responde bem a uma pergunta de cada vez, mas não dá uma visão geral: para saber como está a semana e o mês, o Kaio precisa perguntar várias coisas. O pedido de 08/10/2026 (`SPEC.md`, questões em aberto) é um painel "central de comando" no estilo holográfico da referência visual (`jarvis-ui/referencias-visuais/01-print-2026-10-08-18.07.png`): orbe no centro e, em volta, agenda, gastos, relógio e um registro do que aconteceu. Com o texto e a voz prontos, é a próxima peça do Jarvis.

## What Changes

- **Painel em tela cheia, sob demanda**: abre com **⌥⇧Espaço** ou pelo item **"Painel"** no menu da barra; fecha com **Esc** ou com o mesmo atalho. Não fica ligado o tempo todo.
- **Layout da referência**, adaptado à tela do MacBook:
  - centro: o orbe de partículas, que mostra os estados (ocioso, ouvindo, pensando, falando) e onde aparecem a pergunta e a resposta da conversa em andamento;
  - esquerda: **agenda** de hoje e dos próximos 7 dias;
  - direita: **gastos do mês** por categoria e **faturas abertas** de cada cartão de crédito (total, fechamento e vencimento);
  - topo: **relógio** e data;
  - rodapé: **registro de atividade** (últimos lançamentos e eventos criados, venham do WhatsApp ou do Jarvis, e as perguntas feitas ao Jarvis nesta sessão).
- **Conversa dentro do painel**: campo de texto embaixo do orbe; segurar ⌘⇧Espaço com o painel aberto fala com o Jarvis ali mesmo (o HUD pequeno não aparece por cima).
- **Dados prontos do núcleo**: uma nova ferramenta MCP somente leitura, `painel`, devolve tudo já calculado (agenda, somas por categoria, faturas abertas, últimos registros). O cérebro chama essa ferramenta direto, **sem passar pelo modelo**: abrir o painel não custa tokens.
- **Atualização**: ao abrir, a cada 60 s enquanto estiver aberto e logo depois de um turno que gravou algo.

## Non-goals

- Painel sempre ligado ou num monitor externo dedicado (decisão do Kaio em 09/10/2026: sob demanda).
- Abrir o painel pedindo ao Jarvis ("abre o painel"); fica para depois, se fizer falta.
- Gráficos históricos (meses anteriores, tendências), metas e orçamento (fora do escopo do `SPEC.md`).
- Sessões do Claude Code no painel (change próprio, já previsto no `SPEC.md`).
- Editar dados direto no painel (clicar para apagar um gasto, arrastar evento). Escritas continuam pelas ferramentas, pela conversa.
- Ocultar valores para compartilhar a tela.

## Capabilities

### New Capabilities
- `jarvis-painel`: painel "central de comando" do Jarvis em tela cheia: como abrir e fechar, o que mostra, de onde vêm os números, quando atualiza e a conversa dentro dele.

### Modified Capabilities
- `mcp`: nova ferramenta somente leitura `painel`, só no MCP (como `contexto`), com os dados do painel já calculados no núcleo.

## Impact

- **Núcleo**: `app/mcp_server.py` ganha a ferramenta `painel`; a montagem dos dados reusa as consultas e a regra da fatura que já existem (`app/domain/billing.py`, `open_statement_month`). Não muda o agente do WhatsApp nem os grupos de ferramentas.
- **Cérebro do Jarvis**: nova mensagem do protocolo (`panel`), que chama `painel` pelo MCP e devolve o resultado; o registro de atividade da sessão vem do histórico do próprio cérebro.
- **Interface**: segunda janela Tauri (`painel`) em tela cheia, novos componentes (orbe de partículas, colunas de agenda e gastos, registro), novo atalho global ⌥⇧Espaço, item "Painel" no menu da barra; o push-to-talk passa a ir para a janela visível.
- **Decisões do `SPEC.md`**: fecha a questão em aberto "Painel central de comando"; não altera decisões existentes.
- **Custo**: nenhum token para abrir ou atualizar o painel; só a conversa usa o modelo, como hoje.
