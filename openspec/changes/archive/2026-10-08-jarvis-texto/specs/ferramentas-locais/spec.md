## ADDED Requirements

### Requirement: Ações permitidas
O Jarvis SHALL oferecer só estas ações locais: `abrir_app(nome)`, `buscar_arquivo(texto)` (Spotlight, na pasta pessoal, até 20 resultados), `rodar_atalho(nome)` (só da lista permitida), `controlar_musica(acao)` (tocar, pausar, próxima, no Spotify), `timer(minutos, texto)` (notificação do Mac) e `area_transferencia(acao)` (ler pede confirmação).

#### Scenario: Atalho fora da lista
- **WHEN** o modelo pede `rodar_atalho("Apagar tudo")` e ele não está na lista permitida
- **THEN** a ação é recusada e o motivo volta ao modelo

### Requirement: Sem shell livre
As ações locais SHALL executar comandos fixos com argumentos validados (sem `shell=True`), e nenhuma SHALL apagar arquivos, enviar mensagens ou executar comandos arbitrários.

#### Scenario: Argumento malicioso
- **WHEN** `abrir_app` recebe `Safari; rm -rf ~`
- **THEN** o nome é recusado na validação e nenhum comando é executado
