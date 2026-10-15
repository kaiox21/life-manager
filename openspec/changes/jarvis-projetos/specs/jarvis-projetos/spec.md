## Purpose

Abrir um projeto pelo nome (editor de código e terminal na pasta) e produzir rascunhos de e-mail e mensagem que ficam na área de transferência e no painel, sem nunca enviar nada.

## ADDED Requirements

### Requirement: Abrir projeto
O Kaio SHALL poder pedir, por texto ou voz, para abrir um projeto pelo nome ("abre o NC Barber"). O Jarvis SHALL abrir a pasta no editor de código configurado e um terminal do Jarvis nessa pasta, reaproveitando um terminal de shell livre que já esteja nela em vez de abrir outro; com "com um Claude Code", o terminal SHALL abrir já rodando o Claude Code, nas mesmas condições do requisito "Abrir e fechar terminais". Só pastas da lista permitida dos terminais SHALL ser abertas. O nome SHALL ser casado ignorando maiúsculas, acentos, espaços, hífens e sublinhados; com mais de uma pasta candidata, o Jarvis SHALL perguntar qual; sem nenhuma, SHALL dizer que não achou. Sem o editor instalado, SHALL abrir só o terminal e dizer o motivo. Abrir um projeto SHALL NOT rodar nenhum comando além do próprio editor e do terminal.

#### Scenario: Abrir pelo nome falado
- **WHEN** o Kaio diz "Jarvis, abre o NC Barber" e existe `~/Projetos pessoais/NC-BARBER` na lista permitida
- **THEN** o VS Code abre nessa pasta, uma aba "Terminal N · NC-BARBER" abre no painel e o Jarvis responde em uma frase que o projeto está aberto

#### Scenario: Terminal já aberto na pasta
- **WHEN** já existe o Terminal 2, um shell livre em `life-manager`, e o Kaio pede "abre o life-manager"
- **THEN** o editor abre e a aba do Terminal 2 é mostrada, sem abrir um terminal novo

#### Scenario: Nome com grafia diferente da pasta
- **WHEN** a pasta se chama `plataforma-estudos` e o Kaio diz "abre a plataforma de estudos" ou "abre o Plataforma Estudos"
- **THEN** a pasta é encontrada pelo nome normalizado e o projeto abre

#### Scenario: Mais de uma pasta com o nome
- **WHEN** há `~/AmicusIA/sisdec` e `~/Projetos pessoais/sisdec`
- **THEN** o Jarvis pergunta qual das duas e nada abre até a resposta

#### Scenario: Pasta fora da lista
- **WHEN** o modelo pede para abrir `/` ou uma pasta fora das raízes permitidas
- **THEN** o Jarvis recusa, diz o motivo e nada abre

#### Scenario: Editor ausente
- **WHEN** o app do editor configurado não está instalado
- **THEN** o terminal abre na pasta e o Jarvis diz que o editor não foi encontrado

### Requirement: Rascunhos
O Kaio SHALL poder pedir um rascunho de e-mail, mensagem ou texto ("escreve um e-mail pro professor pedindo…", "faz uma mensagem pro Netto avisando…"). O texto SHALL ser escrito em nome do Kaio, em português do Brasil, no tom pedido, sem a persona do Jarvis (nada de "senhor" nem assinatura do Jarvis). O Jarvis SHALL copiar o corpo do texto para a área de transferência, mostrar um cartão no painel com tipo, destinatário, assunto (se houver) e o texto completo, com um botão Copiar que copia o corpo de novo, e guardar o rascunho num arquivo local (os 50 mais recentes). Por voz, o Jarvis SHALL responder em uma frase que o rascunho está pronto e onde está, e SHALL NOT ler o texto. Rascunhos com mais de 6.000 caracteres SHALL ser recusados.

#### Scenario: E-mail para o professor
- **WHEN** o Kaio diz "escreve um e-mail pro professor de redes pedindo a prova de segunda chamada, que eu estava doente"
- **THEN** o painel mostra o cartão "Rascunho · e-mail para o professor de redes" com assunto e texto assinado pelo Kaio, o corpo está na área de transferência e o Jarvis diz algo como "Rascunho pronto no painel e na área de transferência, senhor."

#### Scenario: Mensagem curta
- **WHEN** o Kaio diz "faz uma mensagem pro Netto avisando que o site volta amanhã de manhã"
- **THEN** o cartão mostra a mensagem sem assunto, o texto está na área de transferência e nada é enviado

#### Scenario: Copiar de novo
- **WHEN** a área de transferência já foi usada para outra coisa e o Kaio clica Copiar no cartão
- **THEN** o corpo do rascunho volta para a área de transferência

#### Scenario: Texto longo demais
- **WHEN** o modelo chama `rascunho` com mais de 6.000 caracteres
- **THEN** a ação é recusada e o motivo volta ao modelo

### Requirement: Nunca envia
O Jarvis SHALL NOT enviar e-mail, mensagem ou qualquer texto a terceiros: não existe ação de envio, e nenhum pedido ("manda esse e-mail", "envia pro Netto") SHALL resultar em envio. O envio é sempre um ato do Kaio no app dele.

#### Scenario: Pedido de envio
- **WHEN** depois do rascunho o Kaio diz "manda esse e-mail"
- **THEN** o Jarvis responde que não envia nada e que o texto está na área de transferência para colar no app de e-mail
