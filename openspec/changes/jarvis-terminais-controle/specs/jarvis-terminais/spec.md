## ADDED Requirements

### Requirement: Abas de terminal
O painel SHALL ter abas de terminal, uma por sessão do Claude Code aberta pelo Jarvis, cada uma com um terminal real rodando o `claude` (mesma tela, cores e teclas do Terminal.app), em que o Kaio vê a saída e a conversa ao vivo e digita direto. A aba SHALL mostrar o número do terminal, a pasta e o estado. Fechar o painel SHALL NOT fechar as sessões; ao reabrir, cada aba SHALL mostrar a tela atual da sessão.

#### Scenario: Digitar na aba
- **WHEN** o Kaio clica na aba "Terminal 3 · life-manager" e digita "roda os testes" e Enter
- **THEN** a sessão recebe a mensagem como se fosse digitada no Terminal.app e a resposta aparece na aba

#### Scenario: Painel fechado e reaberto
- **WHEN** o Kaio fecha o painel com uma sessão trabalhando e o reabre um minuto depois
- **THEN** a aba continua lá, com a tela atual da sessão

### Requirement: Abrir e fechar sessões
O Kaio SHALL poder abrir uma sessão do Claude Code pelo botão "+" do painel, por texto ou por voz ("abre um Claude Code no life-manager"), numa pasta da lista permitida; a sessão nova SHALL receber o menor número livre (a mesma numeração das sessões de fora do Jarvis) e abrir a aba dela. O Jarvis SHALL abrir o `claude` no modo de permissão padrão do Kaio e SHALL NOT abrir sessões com as permissões desligadas. Fechar SHALL encerrar o `claude` da aba; se a sessão estiver trabalhando ou pedindo permissão, SHALL pedir confirmação antes.

#### Scenario: Abrir por voz
- **WHEN** há os Terminais 1 e 2 e o Kaio diz "abre um Claude Code no life-manager"
- **THEN** abre a aba "Terminal 3 · life-manager" com o `claude` rodando nessa pasta

#### Scenario: Pasta fora da lista
- **WHEN** o modelo pede para abrir uma sessão em `/` ou numa pasta fora da lista permitida
- **THEN** o Jarvis recusa, diz o motivo e nada é aberto

#### Scenario: Fechar sessão trabalhando
- **WHEN** o Kaio pede para fechar o Terminal 3 enquanto ele está trabalhando
- **THEN** o Jarvis pede confirmação e só encerra a sessão se o Kaio confirmar

### Requirement: Limite de sessões
O Jarvis SHALL manter no máximo 4 sessões abertas por ele ao mesmo tempo (ajustável em configuração) e SHALL recusar abrir uma nova quando a memória livre do Mac estiver abaixo do limiar configurado, dizendo o motivo. Sessões abertas fora do Jarvis SHALL NOT contar para esse limite.

#### Scenario: Quinta sessão
- **WHEN** já há 4 sessões abertas pelo Jarvis e o Kaio pede outra
- **THEN** o Jarvis recusa e sugere fechar uma das abas

#### Scenario: Pouca memória
- **WHEN** a memória livre do Mac está abaixo do limiar e o Kaio pede uma sessão nova
- **THEN** o Jarvis recusa e diz que o Mac está com pouca memória

### Requirement: Aprovar e negar pelo Jarvis
Quando uma sessão aberta pelo Jarvis pedir permissão, o aviso (no HUD e no painel) SHALL ter os botões Permitir e Negar, e o diálogo de permissão SHALL continuar aparecendo na aba; vale a primeira resposta, dada pelo botão ou na aba, e a outra deixa de valer. O aviso com os botões SHALL ficar até o pedido ser resolvido (sem o prazo de 20 s das sessões de fora), e os botões SHALL sumir assim que o Kaio digitar qualquer coisa na aba daquela sessão enquanto o pedido estiver aberto. Permitir e Negar SHALL valer só para aquele pedido (sem "sempre permitir"). A resposta pelo Jarvis SHALL vir só de um clique ou tecla do Kaio na interface; o modelo de linguagem e a voz SHALL NOT aprovar nem negar. Se o Jarvis não responder (cérebro parado ou erro), o pedido SHALL seguir no diálogo da aba, sem ser aprovado nem negado sozinho. Sessões abertas fora do Jarvis SHALL continuar só com o aviso, sem botões.

#### Scenario: Permitir pelo HUD
- **WHEN** o Terminal 3 pede para rodar `npm test` e o Kaio clica Permitir no HUD
- **THEN** o comando roda, o aviso some e a aba mostra que foi permitido pelo Jarvis

#### Scenario: Negar
- **WHEN** o Kaio clica Negar
- **THEN** o comando não roda e a sessão é avisada de que o Kaio negou pelo Jarvis

#### Scenario: Respondido na aba
- **WHEN** o Kaio responde ao diálogo direto na aba antes de clicar no aviso
- **THEN** vale a resposta da aba e o aviso some sem que os botões façam mais nada

#### Scenario: Comando demorado aprovado na aba
- **WHEN** o Kaio aprova na aba um `npm test` que leva 5 minutos
- **THEN** os botões somem quando ele aperta a tecla na aba, e não 5 minutos depois

#### Scenario: Pedido por voz
- **WHEN** o Kaio diz "Jarvis, permite o terminal 3"
- **THEN** o Jarvis não aprova e lembra que permissões só se respondem pelo botão ou na aba

#### Scenario: Sessão do Terminal.app
- **WHEN** uma sessão aberta no Terminal.app pede permissão
- **THEN** o aviso aparece como antes, sem os botões Permitir e Negar

### Requirement: Mandar mensagens
O Kaio SHALL poder mandar uma mensagem a uma sessão aberta pelo Jarvis digitando na aba ou pedindo ao Jarvis por texto ou voz ("Terminal 2, roda os testes"). Pelo Jarvis, a mensagem SHALL aparecer num cartão com o destino e o texto exato, e SHALL ser enviada só depois de o Kaio confirmar; o texto SHALL ir como texto puro seguido de Enter, sem teclas de controle. Mandar para uma sessão de fora do Jarvis SHALL ser recusado com o motivo.

#### Scenario: Recado por voz
- **WHEN** o Kaio diz "Terminal 2, roda os testes"
- **THEN** o Jarvis mostra "Mandar para o Terminal 2 (sisdec): roda os testes" e envia ao confirmar

#### Scenario: Sessão de fora
- **WHEN** o Kaio pede para mandar algo ao Terminal 1, que está no Terminal.app
- **THEN** o Jarvis diz que só escreve nas sessões abertas por ele

### Requirement: Sessão encerrada pelo reinício
Quando o cérebro do Jarvis reiniciar, as sessões abertas por ele SHALL ser encerradas, e cada uma SHALL aparecer no painel como encerrada, com a opção de retomar a mesma conversa numa sessão nova.

#### Scenario: Retomar depois do reinício
- **WHEN** o cérebro reinicia com o Terminal 3 aberto e o Kaio clica "Retomar" na aba
- **THEN** abre uma sessão nova na mesma pasta, continuando a conversa anterior

## MODIFIED Requirements

### Requirement: Aviso de permissão
Quando uma sessão pedir permissão para usar uma ferramenta, o Jarvis SHALL mostrar na hora, sem roubar o foco do app em uso e com um toque curto, um aviso com o número do terminal, a pasta, a ferramenta e um resumo do pedido (comando, arquivo ou URL, cortado em 120 caracteres). Nas sessões abertas pelo Jarvis, o aviso SHALL ter os botões do requisito "Aprovar e negar pelo Jarvis"; nas de fora, o Jarvis SHALL NOT aprovar nem negar.

#### Scenario: Comando no terminal
- **WHEN** a sessão do Terminal 1, em `life-manager`, pede permissão para rodar `npm test`
- **THEN** o HUD aparece com "Terminal 1 (life-manager) está pedindo para rodar `npm test`" e o foco continua no app em uso

#### Scenario: Pedido respondido no terminal
- **WHEN** o Kaio responde à permissão no próprio terminal
- **THEN** o aviso some no próximo sinal da sessão ou, numa sessão de fora do Jarvis, no máximo 20 s depois, e o Terminal 1 volta a "trabalhando"
