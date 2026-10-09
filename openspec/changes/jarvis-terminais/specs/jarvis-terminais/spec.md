## Purpose
Gerenciador de terminais do Jarvis: cada sessão do Claude Code aberta neste Mac vira um terminal numerado, e o Jarvis avisa na hora quando uma pede permissão ou fica esperando o Kaio, sem ler o conteúdo das conversas.

## ADDED Requirements

### Requirement: Terminais numerados
Cada Claude Code aberto neste Mac (um processo, numa janela ou aba de terminal) SHALL receber o menor número livre ("Terminal 1", "Terminal 2"…) quando o Jarvis o vê pela primeira vez e SHALL manter esse número até o processo fechar, mesmo que a conversa dentro dele recomece (`/clear`, retomada); o número vem sempre acompanhado do nome da pasta e da hora em que foi visto pela primeira vez.

#### Scenario: Duas sessões
- **WHEN** o Kaio abre o Claude Code em `life-manager` e depois em `sisdec`
- **THEN** o Jarvis mostra "Terminal 1 · life-manager" e "Terminal 2 · sisdec"

#### Scenario: Conversa recomeçada
- **WHEN** o Kaio usa `/clear` no Terminal 1
- **THEN** ele continua sendo o Terminal 1

#### Scenario: Número liberado
- **WHEN** o Terminal 1 fecha e uma sessão nova abre
- **THEN** a nova vira "Terminal 1" e o Terminal 2 continua com o mesmo número

### Requirement: Aviso de permissão
Quando uma sessão pedir permissão para usar uma ferramenta, o Jarvis SHALL mostrar na hora, sem roubar o foco do app em uso e com um toque curto, um aviso com o número do terminal, a pasta, a ferramenta e um resumo do pedido (comando, arquivo ou URL, cortado em 120 caracteres). O Jarvis SHALL NOT aprovar nem negar o pedido.

#### Scenario: Comando no terminal
- **WHEN** a sessão do Terminal 1, em `life-manager`, pede permissão para rodar `npm test`
- **THEN** o HUD aparece com "Terminal 1 (life-manager) está pedindo para rodar `npm test`" e o foco continua no app em uso

#### Scenario: Pedido respondido no terminal
- **WHEN** o Kaio responde à permissão no próprio terminal
- **THEN** o aviso some no próximo sinal da sessão ou, no máximo, 20 s depois, e o Terminal 1 volta a "trabalhando"

### Requirement: Espera e término
O Jarvis SHALL avisar quando uma sessão ficar parada esperando o Kaio e SHALL marcar, sem tirar o HUD do lugar, quando uma sessão terminar uma tarefa.

#### Scenario: Sessão esperando resposta
- **WHEN** o Terminal 2 fica parado esperando o Kaio
- **THEN** o HUD aparece com "Terminal 2 (sisdec) está esperando você"

### Requirement: Lista de terminais
O painel SHALL ter uma coluna "Terminais" com número, pasta e estado de cada sessão aberta (trabalhando, pedindo permissão, esperando você, terminou), e o Jarvis SHALL responder "como estão meus terminais?" com a mesma lista.

#### Scenario: Pergunta ao Jarvis
- **WHEN** o Kaio pergunta "como estão meus terminais?"
- **THEN** o Jarvis responde com a lista e mostra um cartão com os terminais

### Requirement: Privacidade dos hooks
Os hooks SHALL só anotar, num arquivo local do Jarvis com permissão 600, o evento, o processo, a sessão, a pasta e o resumo do pedido de permissão; SHALL NOT anotar o texto das mensagens, o conteúdo de arquivos nem a saída de comandos, e os hooks não enviam nada para fora do Mac. O resumo do pedido SHALL NOT ir para o modelo de linguagem (nem quando o Kaio pergunta pelos terminais: ele aparece só no cartão). Os hooks SHALL NOT poder bloquear, aprovar, negar ou escrever na conversa de nenhuma sessão, mesmo quando falham. Instalar os hooks SHALL preservar os outros ajustes do `~/.claude/settings.json`, com backup, e SHALL ser reversível.

#### Scenario: Mensagem do Kaio
- **WHEN** o Kaio envia uma mensagem numa sessão
- **THEN** o arquivo do Jarvis registra só que a sessão voltou a trabalhar, sem o texto da mensagem

#### Scenario: Hook quebrado
- **WHEN** o script do hook some ou dá erro
- **THEN** as sessões do Claude Code seguem normais, sem mensagem de erro na conversa e sem permissão negada

#### Scenario: Remover
- **WHEN** o Kaio roda `install_mac.sh --sem-terminais`
- **THEN** os hooks do Jarvis saem do `~/.claude/settings.json` e o resto do arquivo fica igual
