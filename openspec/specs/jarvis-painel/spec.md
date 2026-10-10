# jarvis-painel Specification

## Purpose
Painel "central de comando" do Jarvis em tela cheia, aberto sob demanda: visão geral da agenda, dos gastos do mês, das faturas abertas e da atividade recente, com o orbe e a conversa no centro, no estilo holográfico do HUD.

## Requirements

### Requirement: Abrir e fechar sob demanda
O painel SHALL abrir em tela cheia, no monitor em uso, com o atalho global ⌥⇧Espaço ou pelo item "Painel" no menu da barra, e SHALL fechar com o mesmo atalho ou com Esc. Com o foco numa aba de terminal, o Esc SHALL ir para a sessão (o Claude Code o usa para interromper) e SHALL NOT fechar o painel. O painel SHALL NOT ficar aberto sozinho nem abrir ao iniciar o Mac.

#### Scenario: Abrir pelo atalho
- **WHEN** o Kaio aperta ⌥⇧Espaço com qualquer app em primeiro plano
- **THEN** o painel cobre a tela com o relógio, a agenda, os gastos, as faturas, o registro e o orbe

#### Scenario: Fechar
- **WHEN** o painel está aberto, sem foco numa aba de terminal, e o Kaio aperta Esc
- **THEN** o painel fecha e o app que estava em uso volta ao primeiro plano

#### Scenario: Esc numa aba de terminal
- **WHEN** o foco está na aba do Terminal 3 e o Kaio aperta Esc
- **THEN** o Esc vai para o Claude Code e o painel continua aberto

#### Scenario: Abrir pelo menu
- **WHEN** o Kaio escolhe "Painel" no ícone do Jarvis na barra de menus
- **THEN** o painel abre em tela cheia

### Requirement: Conteúdo do painel
O painel SHALL mostrar: relógio e data; compromissos de hoje e dos próximos 7 dias; gastos do mês corrente por categoria, com o total do mês; a fatura aberta de cada cartão de crédito, com total, data de fechamento e de vencimento; e um registro com os últimos lançamentos e eventos criados (por qualquer canal) e as perguntas feitas ao Jarvis na sessão.

#### Scenario: Gasto lançado pelo WhatsApp
- **WHEN** o Kaio lança "47 no almoço no Nubank" pelo WhatsApp e depois abre o painel
- **THEN** o gasto aparece no registro, a categoria Alimentação e o total do mês incluem o valor, e a fatura aberta do Nubank também

#### Scenario: Dia sem compromissos
- **WHEN** não há eventos hoje
- **THEN** a coluna da agenda diz que o dia está livre e mostra os próximos compromissos da semana

### Requirement: Números vindos do núcleo
Todos os valores, somas, datas de fatura e listas do painel SHALL vir prontos do núcleo pelo MCP; nem a interface nem o modelo SHALL calcular totais, e abrir ou atualizar o painel SHALL NOT chamar o modelo de linguagem.

#### Scenario: Abrir sem custo
- **WHEN** o Kaio abre o painel
- **THEN** os dados chegam sem nenhuma chamada ao LLM (nenhum token gasto)

### Requirement: Atualização
O painel SHALL buscar os dados ao abrir, a cada 60 segundos enquanto estiver aberto e logo depois de um turno do Jarvis que gravou algo; fechado, SHALL NOT buscar nada nem animar.

#### Scenario: Lançar pelo painel
- **WHEN** com o painel aberto o Kaio diz "gastei 30 de Uber no Nubank"
- **THEN** depois da resposta, Transporte, o total do mês, a fatura do Nubank e o registro já mostram o gasto

### Requirement: Conversa no painel
O painel SHALL ter campo de texto sob o orbe e SHALL aceitar o push-to-talk (⌘⇧Espaço) enquanto estiver aberto, mostrando ali a pergunta, os passos, a resposta e os cartões; com o painel aberto, o HUD pequeno SHALL NOT aparecer por cima.

#### Scenario: Voz com o painel aberto
- **WHEN** o painel está aberto e o Kaio segura ⌘⇧Espaço e pergunta "quanto gastei com mercado esse mês?"
- **THEN** o orbe do painel mostra "ouvindo" e depois responde, sem abrir o HUD pequeno

### Requirement: Núcleo indisponível
Se o cérebro ou o núcleo não responder, o painel SHALL abrir mesmo assim, com relógio e orbe, e SHALL mostrar nas colunas que os dados estão indisponíveis, sem valores antigos apresentados como atuais.

#### Scenario: Docker parado
- **WHEN** o núcleo está fora do ar e o Kaio abre o painel
- **THEN** as colunas de agenda e gastos mostram "núcleo indisponível" e o horário da última atualização bem-sucedida, se houver

### Requirement: Movimento acessível
As animações do painel (orbe de partículas, anéis, varredura) SHALL respeitar a preferência "Reduzir movimento" do macOS e SHALL parar quando o painel fechar.

#### Scenario: Reduzir movimento ligado
- **WHEN** "Reduzir movimento" está ligado no macOS
- **THEN** o orbe aparece estático e as transições são só de opacidade
