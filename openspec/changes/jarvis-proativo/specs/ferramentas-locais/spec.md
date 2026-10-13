## MODIFIED Requirements

### Requirement: Ações permitidas
O Jarvis SHALL oferecer só estas ações locais: `abrir_app(nome)`, `buscar_arquivo(texto)` (Spotlight, na pasta pessoal, até 20 resultados), `rodar_atalho(nome)` (só da lista permitida), `controlar_musica(acao)` (tocar, pausar, próxima, anterior, aleatório, repetir e volume de 0 a 100, no Spotify), `tocar_musica(pedido, tipo)` (busca e toca no Spotify deste Mac uma música, artista, álbum, playlist do catálogo ou playlist do Kaio), `timer(minutos, texto)` (notificação do Mac), `silenciar_avisos(acao, minutos)` (pausa ou retoma só os avisos falados do próprio Jarvis, sem confirmação) e `area_transferencia(acao)` (ler pede confirmação), além das ferramentas de terminal, que seguem o requisito "Sem shell livre".

#### Scenario: Atalho fora da lista
- **WHEN** o modelo pede `rodar_atalho("Apagar tudo")` e ele não está na lista permitida
- **THEN** a ação é recusada e o motivo volta ao modelo

#### Scenario: Volume fora da faixa
- **WHEN** o modelo pede `controlar_musica` com volume 150
- **THEN** a ação é recusada e o motivo volta ao modelo

#### Scenario: Pausa dos avisos sem confirmação
- **WHEN** o modelo chama `silenciar_avisos(acao="pausar", minutos=60)`
- **THEN** os avisos falados param por uma hora sem cartão de confirmação, e o WhatsApp continua recebendo os avisos
