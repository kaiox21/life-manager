## MODIFIED Requirements

### Requirement: Ações permitidas
O Jarvis SHALL oferecer só estas ações locais: `abrir_app(nome)`, `buscar_arquivo(texto)` (Spotlight, na pasta pessoal, até 20 resultados), `rodar_atalho(nome)` (só da lista permitida), `controlar_musica(acao)` (tocar, pausar, próxima, no Spotify), `timer(minutos, texto)` (notificação do Mac), `area_transferencia(acao)` (ler pede confirmação) e `importar_fatura(arquivo, cartao?)` (lê um `.pdf` de até 10 MB dentro da pasta pessoal e o entrega ao núcleo pelo MCP; sem `arquivo`, usa o PDF mais recente da pasta Downloads dos últimos 7 dias; não apaga nem move o arquivo).

#### Scenario: Atalho fora da lista
- **WHEN** o modelo pede `rodar_atalho("Apagar tudo")` e ele não está na lista permitida
- **THEN** a ação é recusada e o motivo volta ao modelo

#### Scenario: Fatura baixada
- **WHEN** o Kaio diz "lê a fatura do nubank que eu baixei"
- **THEN** o Jarvis entrega o PDF mais recente de Downloads ao núcleo e mostra o cartão com o resumo e a confirmação

#### Scenario: Arquivo fora da pasta pessoal
- **WHEN** o modelo pede `importar_fatura("/etc/passwd")`
- **THEN** a ação é recusada e o motivo volta ao modelo
