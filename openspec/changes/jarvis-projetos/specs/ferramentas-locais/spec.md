## MODIFIED Requirements

### Requirement: Ações permitidas
O Jarvis SHALL oferecer só estas ações locais: `abrir_app(nome)`, `buscar_arquivo(texto)` (Spotlight, na pasta pessoal, até 20 resultados), `rodar_atalho(nome)` (só da lista permitida), `controlar_musica(acao)` (tocar, pausar, próxima, anterior, aleatório, repetir e volume de 0 a 100, no Spotify), `tocar_musica(pedido, tipo)` (busca e toca no Spotify deste Mac uma música, artista, álbum, playlist do catálogo ou playlist do Kaio), `timer(minutos, texto)` (notificação do Mac), `silenciar_avisos(acao, minutos)` (pausa ou retoma só os avisos falados do próprio Jarvis, sem confirmação), `modo_estudo(acao, minutos, pausa)` (inicia, encerra ou consulta o modo estudo: Foco pelos atalhos configurados, playlist de estudo e avisos retidos; sem confirmação), `abrir_projeto(nome, claude)` (abre a pasta no editor configurado e um terminal do Jarvis nela, só em pastas da lista permitida dos terminais; sem confirmação), `rascunho(tipo, para, assunto, texto)` (copia o texto para a área de transferência, mostra no painel e guarda em arquivo local; sem confirmação; nunca envia) e `area_transferencia(acao)` (ler pede confirmação), além das ferramentas de terminal, que seguem o requisito "Sem shell livre". O Foco SHALL ser ligado e desligado só por atalhos cujo nome está configurado e existe no app Atalhos; o Jarvis SHALL NOT criar nem alterar atalhos.

#### Scenario: Atalho fora da lista
- **WHEN** o modelo pede `rodar_atalho("Apagar tudo")` e ele não está na lista permitida
- **THEN** a ação é recusada e o motivo volta ao modelo

#### Scenario: Volume fora da faixa
- **WHEN** o modelo pede `controlar_musica` com volume 150
- **THEN** a ação é recusada e o motivo volta ao modelo

#### Scenario: Pausa dos avisos sem confirmação
- **WHEN** o modelo chama `silenciar_avisos(acao="pausar", minutos=60)`
- **THEN** os avisos falados param por uma hora sem cartão de confirmação, e o WhatsApp continua recebendo os avisos

#### Scenario: Minutos fora da faixa
- **WHEN** o modelo chama `modo_estudo(acao="iniciar", minutos=600)`
- **THEN** a ação é recusada e o motivo volta ao modelo

#### Scenario: Atalho do Foco inexistente
- **WHEN** o atalho configurado para ligar o Foco não está no app Atalhos
- **THEN** nada é executado para o Foco, e o modo começa sem ele dizendo o motivo

#### Scenario: Projeto fora da lista
- **WHEN** o modelo chama `abrir_projeto(nome="/")` ou com uma pasta fora das raízes permitidas
- **THEN** a ação é recusada com o motivo e a lista de raízes permitidas, e nada abre

#### Scenario: Rascunho grande demais
- **WHEN** o modelo chama `rascunho` com um texto de mais de 6.000 caracteres
- **THEN** a ação é recusada e o motivo volta ao modelo
