## MODIFIED Requirements

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
