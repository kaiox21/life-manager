## ADDED Requirements

### Requirement: Terminais compartilhados
Cada terminal aberto pelo Jarvis ou numa janela nova do Terminal.app SHALL ser uma sessão compartilhada, que o Terminal.app e o Jarvis podem mostrar ao mesmo tempo, com o que se digita num lado aparecendo no outro. Cada uma SHALL receber o menor número livre ("Terminal 1", "Terminal 2"…), na mesma numeração das sessões do Claude Code de fora (VS Code, janelas antigas), e SHALL mostrar a pasta e se é um shell ou um Claude Code. Fechar a janela do Terminal.app SHALL encerrar a sessão, a não ser que ela esteja aberta numa aba do Jarvis.

#### Scenario: Janela nova do Terminal.app
- **WHEN** o Kaio abre uma janela nova no Terminal.app e entra em `life-manager`
- **THEN** o Jarvis lista "Terminal 3 · life-manager · shell", e abrir a aba dele mostra a mesma tela da janela

#### Scenario: Digitar nos dois lados
- **WHEN** o Terminal 3 está aberto no Terminal.app e numa aba do Jarvis, e o Kaio digita `git status` na aba
- **THEN** o comando aparece e roda nas duas telas

#### Scenario: Fechar a janela
- **WHEN** o Kaio fecha a janela do Terminal 3 no Terminal.app e ele não está aberto numa aba
- **THEN** a sessão acaba e o Terminal 3 sai da lista

#### Scenario: Claude Code dentro de um terminal
- **WHEN** o Kaio roda `claude` no Terminal 3
- **THEN** o Terminal 3 passa a aparecer como Claude Code, com o estado da sessão (trabalhando, pedindo permissão, esperando você)

### Requirement: Terminal.app no tmux
O instalador SHALL fazer toda janela nova do Terminal.app abrir dentro do terminal compartilhado, sem mexer em terminais de outros apps (VS Code) nem nas janelas já abertas. SHALL guardar um backup do `~/.zshrc`, SHALL permitir desligar numa janela (`JARVIS_SEM_TMUX=1`) ou de vez (`install_mac.sh --sem-tmux`), e uma falha do tmux SHALL deixar a janela num shell normal, nunca fechada.

#### Scenario: tmux ausente
- **WHEN** o tmux foi desinstalado e o Kaio abre uma janela nova
- **THEN** a janela abre num shell normal

#### Scenario: Desligar
- **WHEN** o Kaio roda `install_mac.sh --sem-tmux`
- **THEN** o bloco do Jarvis sai do `~/.zshrc`, o resto do arquivo fica igual e as janelas novas abrem normais

### Requirement: Abas de terminal
O painel SHALL ter abas de terminal, uma para cada terminal compartilhado que o Kaio abrir nele, cada uma com a mesma tela, cores e teclas do Terminal.app, em que ele vê a saída ao vivo e digita direto. A aba SHALL mostrar o número, a pasta e o estado. Fechar a aba ou o painel SHALL NOT encerrar o terminal; ao reabrir, a aba SHALL mostrar a tela atual.

#### Scenario: Abrir um terminal do Terminal.app numa aba
- **WHEN** o Kaio escolhe o Terminal 3 na lista do painel
- **THEN** abre a aba "Terminal 3 · life-manager" com a tela atual, e o que ele digita ali vai para o terminal

#### Scenario: Painel fechado e reaberto
- **WHEN** o Kaio fecha o painel com um terminal trabalhando e o reabre um minuto depois
- **THEN** a aba continua lá, com a tela atual

### Requirement: Abrir e fechar terminais
O Kaio SHALL poder abrir um terminal pelo botão "+" do painel, por texto ou por voz, numa pasta da lista permitida, como shell ("abre um terminal no life-manager") ou já rodando o Claude Code ("abre um Claude Code no life-manager"). O terminal novo SHALL receber o menor número livre e abrir a aba dele. O Jarvis SHALL abrir o Claude Code no modo de permissão padrão do Kaio e SHALL NOT abri-lo com as permissões desligadas. Fechar SHALL encerrar o terminal e o que roda nele; se houver algo rodando (Claude Code trabalhando ou pedindo permissão, ou um comando em execução no shell), SHALL pedir confirmação antes.

#### Scenario: Abrir por voz
- **WHEN** há os Terminais 1 e 2 e o Kaio diz "abre um Claude Code no life-manager"
- **THEN** abre a aba "Terminal 3 · life-manager" com o Claude Code rodando nessa pasta

#### Scenario: Só um terminal
- **WHEN** o Kaio clica "+", escolhe "Terminal" e a pasta `sisdec`
- **THEN** abre uma aba com um shell em `sisdec`

#### Scenario: Pasta fora da lista
- **WHEN** o modelo pede para abrir um terminal em `/` ou numa pasta fora da lista permitida
- **THEN** o Jarvis recusa, diz o motivo e nada é aberto

#### Scenario: Fechar com algo rodando
- **WHEN** o Kaio pede para fechar o Terminal 3 enquanto um `npm test` roda nele
- **THEN** o Jarvis pede confirmação e só encerra se o Kaio confirmar

### Requirement: Limite de sessões
O Jarvis SHALL recusar abrir um terminal novo quando a memória livre do Mac estiver abaixo do limiar configurado e SHALL manter no máximo 4 Claude Code abertos por ele ao mesmo tempo (ajustável em configuração), dizendo o motivo. Terminais abertos no Terminal.app SHALL NOT ser bloqueados.

#### Scenario: Quinto Claude Code
- **WHEN** já há 4 Claude Code abertos pelo Jarvis e o Kaio pede outro
- **THEN** o Jarvis recusa e sugere fechar um deles

#### Scenario: Pouca memória
- **WHEN** a memória livre do Mac está abaixo do limiar e o Kaio pede um terminal novo
- **THEN** o Jarvis recusa e diz que o Mac está com pouca memória

### Requirement: Aprovar e negar pelo Jarvis
Quando um Claude Code rodando num terminal compartilhado pedir permissão, o aviso (no HUD e no painel) SHALL ter os botões Permitir e Negar. O diálogo de permissão SHALL continuar aparecendo no terminal, e vale a primeira resposta: a dada pelo botão ou a dada no terminal. Permitir e Negar SHALL valer só para aquele pedido (sem "sempre permitir"). O aviso com os botões SHALL ficar até o pedido ser resolvido, e os botões SHALL sumir assim que o Kaio digitar na aba daquele terminal ou a sessão der o próximo sinal. A resposta pelo Jarvis SHALL vir só de um clique do Kaio na interface; o modelo de linguagem e a voz SHALL NOT aprovar nem negar. Se o Jarvis não responder (cérebro parado ou erro), o pedido SHALL seguir no diálogo do terminal, sem ser aprovado nem negado sozinho. Sessões de fora dos terminais compartilhados SHALL continuar só com o aviso, sem botões.

#### Scenario: Permitir pelo HUD
- **WHEN** o Terminal 3 pede para rodar `npm test` e o Kaio clica Permitir no HUD
- **THEN** o comando roda, o aviso some e o terminal mostra que foi permitido pelo hook

#### Scenario: Negar
- **WHEN** o Kaio clica Negar
- **THEN** o comando não roda e a sessão é avisada de que o Kaio negou pelo Jarvis

#### Scenario: Respondido na aba
- **WHEN** o Kaio responde ao diálogo direto na aba antes de clicar no aviso
- **THEN** vale a resposta da aba e os botões somem sem fazer mais nada

#### Scenario: Terminal do Terminal.app
- **WHEN** um Claude Code rodando numa janela do Terminal.app (dentro do tmux) pede permissão
- **THEN** o aviso tem os botões Permitir e Negar

#### Scenario: Pedido por voz
- **WHEN** o Kaio diz "Jarvis, permite o terminal 3"
- **THEN** o Jarvis não aprova e lembra que permissões só se respondem pelo botão ou no terminal

#### Scenario: Sessão de fora
- **WHEN** uma sessão do Claude Code no terminal do VS Code pede permissão
- **THEN** o aviso aparece como antes, sem os botões

### Requirement: Mandar mensagens e comandos
O Kaio SHALL poder mandar texto a um terminal compartilhado digitando na aba ou pedindo ao Jarvis por texto ou voz. Pelo Jarvis, num terminal com Claude Code o texto SHALL ir como mensagem ("Terminal 2, roda os testes"), e num shell SHALL ir como um comando de uma linha ("Terminal 3, roda npm test"). Em ambos os casos o Jarvis SHALL mostrar um cartão com o destino, o tipo (mensagem ou comando) e o texto exato, e SHALL enviar só depois de o Kaio confirmar. O texto SHALL ir sem teclas de controle, e o comando de shell SHALL ter uma linha só. Mandar para uma sessão de fora dos terminais compartilhados SHALL ser recusado com o motivo.

#### Scenario: Recado para o Claude Code
- **WHEN** o Kaio diz "Terminal 2, roda os testes" e o Terminal 2 roda o Claude Code
- **THEN** o Jarvis mostra "Mensagem para o Terminal 2 (sisdec): roda os testes" e envia ao confirmar

#### Scenario: Comando no shell
- **WHEN** o Kaio diz "Terminal 3, roda npm test" e o Terminal 3 é um shell
- **THEN** o Jarvis mostra "Comando no Terminal 3 (life-manager): npm test" e só roda depois do clique em Confirmar

#### Scenario: Comando com várias linhas
- **WHEN** o modelo tenta mandar ao shell um texto com quebra de linha
- **THEN** o Jarvis recusa e pede um comando de uma linha

#### Scenario: Sessão de fora
- **WHEN** o Kaio pede para mandar algo a um Claude Code que roda no VS Code
- **THEN** o Jarvis diz que só escreve nos terminais compartilhados

### Requirement: Terminais sobrevivem ao reinício
Reiniciar o cérebro ou a interface do Jarvis SHALL NOT encerrar os terminais compartilhados nem o que roda neles; depois do reinício, a lista e as abas SHALL voltar com os mesmos números.

#### Scenario: Reinício do cérebro
- **WHEN** o cérebro do Jarvis reinicia com o Claude Code trabalhando no Terminal 3
- **THEN** o Claude Code continua trabalhando, e o Terminal 3 volta à lista e à aba com o mesmo número

## MODIFIED Requirements

### Requirement: Aviso de permissão
Quando uma sessão pedir permissão para usar uma ferramenta, o Jarvis SHALL mostrar na hora, sem roubar o foco do app em uso e com um toque curto, um aviso com o número do terminal, a pasta, a ferramenta e um resumo do pedido (comando, arquivo ou URL, cortado em 120 caracteres). Nos terminais compartilhados, o aviso SHALL ter os botões do requisito "Aprovar e negar pelo Jarvis"; nas sessões de fora, o Jarvis SHALL NOT aprovar nem negar.

#### Scenario: Comando no terminal
- **WHEN** a sessão do Terminal 1, em `life-manager`, pede permissão para rodar `npm test`
- **THEN** o HUD aparece com "Terminal 1 (life-manager) está pedindo para rodar `npm test`" e o foco continua no app em uso

#### Scenario: Pedido respondido no terminal
- **WHEN** o Kaio responde à permissão no próprio terminal
- **THEN** o aviso some no próximo sinal da sessão ou, numa sessão de fora dos terminais compartilhados, no máximo 20 s depois, e o Terminal 1 volta a "trabalhando"
