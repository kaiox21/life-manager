## MODIFIED Requirements

### Requirement: Sem shell livre
As ações locais SHALL executar comandos fixos com argumentos validados (sem `shell=True`), e nenhuma SHALL apagar arquivos, enviar mensagens ou executar comandos arbitrários. Única exceção: as ferramentas de terminal (`abrir_terminal`, `mandar_terminal`, `fechar_terminal`) SHALL poder abrir o `claude` numa pasta permitida, escrever texto puro numa sessão aberta pelo Jarvis e encerrá-la; escrever e encerrar SHALL pedir confirmação do Kaio na interface, e nenhuma delas SHALL abrir outro programa, escrever teclas de controle ou responder a pedidos de permissão.

#### Scenario: Argumento malicioso
- **WHEN** `abrir_app` recebe `Safari; rm -rf ~`
- **THEN** o nome é recusado na validação e nenhum comando é executado

#### Scenario: Texto com teclas de controle
- **WHEN** o modelo chama `mandar_terminal` com um texto que contém Ctrl-C ou Esc
- **THEN** as teclas de controle são removidas e o cartão de confirmação mostra só o texto que será enviado

#### Scenario: Mensagem sem confirmação
- **WHEN** o modelo chama `mandar_terminal` e o Kaio cancela o cartão
- **THEN** nada é escrito na sessão
