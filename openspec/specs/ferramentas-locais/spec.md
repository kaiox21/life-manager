# ferramentas-locais Specification

## Purpose
Ações seguras no macOS para o Jarvis, com comandos fixos e argumentos validados, sem shell livre, sem apagar arquivos e sem mandar mensagens.

## Requirements

### Requirement: Ações permitidas
O Jarvis SHALL oferecer só estas ações locais: `abrir_app(nome)`, `buscar_arquivo(texto)` (Spotlight, na pasta pessoal, até 20 resultados), `rodar_atalho(nome)` (só da lista permitida), `controlar_musica(acao)` (tocar, pausar, próxima, no Spotify), `timer(minutos, texto)` (notificação do Mac) e `area_transferencia(acao)` (ler pede confirmação).

#### Scenario: Atalho fora da lista
- **WHEN** o modelo pede `rodar_atalho("Apagar tudo")` e ele não está na lista permitida
- **THEN** a ação é recusada e o motivo volta ao modelo

### Requirement: Sem shell livre
As ações locais SHALL executar comandos fixos com argumentos validados (sem `shell=True`), e nenhuma SHALL apagar arquivos, enviar mensagens ou executar comandos arbitrários. Única exceção: as ferramentas de terminal (`abrir_terminal`, `mandar_terminal`, `fechar_terminal`) SHALL poder abrir um shell ou o Claude Code numa pasta permitida, mandar a um terminal compartilhado uma mensagem (Claude Code) ou um comando de uma linha (shell), e encerrar um terminal. Mandar SHALL pedir sempre a confirmação do Kaio na interface, com o texto exato, e SHALL acontecer só com o Claude Code parado esperando o Kaio ou com o shell livre (sem programa em primeiro plano); encerrar SHALL pedir confirmação quando houver algo rodando; e nenhuma delas SHALL repassar teclas de controle vindas do modelo (o Jarvis usa por conta própria só a limpeza da linha do prompt e o Enter), mandar comando de várias linhas ou responder a pedidos de permissão.

#### Scenario: Argumento malicioso
- **WHEN** `abrir_app` recebe `Safari; rm -rf ~`
- **THEN** o nome é recusado na validação e nenhum comando é executado

#### Scenario: Texto com teclas de controle
- **WHEN** o modelo chama `mandar_terminal` com um texto que contém Ctrl-C ou Esc
- **THEN** as teclas de controle são removidas e o cartão de confirmação mostra só o texto que será enviado

#### Scenario: Mensagem com diálogo na tela
- **WHEN** o modelo chama `mandar_terminal` para um Claude Code que está pedindo permissão
- **THEN** nada é escrito e o modelo recebe o motivo

#### Scenario: Comando sem confirmação
- **WHEN** o modelo chama `mandar_terminal` para um shell e o Kaio cancela o cartão
- **THEN** nada é escrito no terminal e nenhum comando roda

### Requirement: Listar terminais
O Jarvis SHALL ter a ferramenta local somente leitura `listar_terminais`, que devolve os terminais abertos (número, pasta, estado e, se houver, a ferramenta do pedido de permissão pendente), sem executar nada; o resumo do pedido vai só para o cartão na tela, não para o modelo.

#### Scenario: Nenhum terminal
- **WHEN** não há sessão do Claude Code aberta
- **THEN** `listar_terminais` devolve a lista vazia e o Jarvis diz que não há terminais abertos
