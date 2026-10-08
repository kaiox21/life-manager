# canal-whatsapp Specification

## Purpose
Receber e enviar mensagens de WhatsApp pela Evolution API v2 (Baileys) com segurança e sem duplicar respostas, mantendo a Evolution isolada em `app/channel/` para que a troca pela API oficial não toque no agente.

## Requirements

### Requirement: Isolamento do canal
Apenas `app/channel/` SHALL conhecer o formato e as rotas da Evolution API; o resto do código SHALL usar os tipos próprios `IncomingMessage`, `OutgoingMessage` e `Media`.

#### Scenario: Troca de integração
- **WHEN** a integração Baileys é trocada pela Cloud API oficial
- **THEN** só `app/channel/` muda; agente, ferramentas e banco ficam intactos

### Requirement: Webhook autenticado
O endpoint `POST /webhook/evolution` SHALL exigir o header `X-Webhook-Secret` igual a `WEBHOOK_SECRET`, comparado em tempo constante, e SHALL responder 401 sem ele. O webhook é configurado por instância (o global não envia headers) e trafega só pela rede interna do Docker.

#### Scenario: Segredo errado
- **WHEN** chega um webhook sem o header ou com valor diferente
- **THEN** a resposta é 401 e nada é processado

### Requirement: Allowlist do dono
O sistema SHALL processar só mensagens do número em `OWNER_PHONE`, aceitando-o com e sem o nono dígito, e SHALL ignorar sem responder grupos, status, newsletters, broadcasts e outros remetentes. Com endereçamento LID, o número real vem de `remoteJidAlt`.

#### Scenario: Outro número
- **WHEN** um terceiro manda mensagem para o número do bot
- **THEN** o webhook responde 200 com `ignored/not_owner` e nada é gravado nem respondido

### Requirement: Modo provisório conversa-comigo-mesmo
Com `SELF_CHAT_MODE=true` (instância conectada ao número do próprio dono), o sistema SHALL aceitar `fromMe` só na conversa do dono consigo mesmo, SHALL prefixar as respostas com `🤖 ` e SHALL descartar mensagens com esse prefixo; mensagens do dono para terceiros e de terceiros para o dono continuam ignoradas. Fora desse modo, `fromMe` é sempre ignorado.

#### Scenario: Resposta do bot voltando pelo webhook
- **WHEN** a resposta "🤖 ..." volta como `messages.upsert` com `fromMe`
- **THEN** é ignorada com `bot_reply`, sem gerar laço

### Requirement: Idempotência
O sistema SHALL gravar cada mensagem recebida em `messages` com `INSERT ... ON CONFLICT (wa_message_id) DO NOTHING` e SHALL processar só quando a linha foi inserida, respondendo 200 imediatamente e processando em background.

#### Scenario: Webhook repetido ou simultâneo
- **WHEN** o mesmo `wa_message_id` chega duas ou mais vezes, inclusive ao mesmo tempo
- **THEN** só uma resposta é enviada

### Requirement: Envio restrito ao dono
A função de envio SHALL aceitar apenas `OWNER_PHONE` como destino, e toda mensagem enviada SHALL ser registrada em `messages` com `direction='out'`.

#### Scenario: Destino diferente
- **WHEN** algum código tenta enviar para outro número
- **THEN** `ForbiddenDestinationError` é levantado e nada sai

### Requirement: Instância e QR
`python -m app.channel.setup` SHALL criar a instância com o webhook interno, o header secreto, `base64: true` e os eventos `MESSAGES_UPSERT` e `CONNECTION_UPDATE`, e SHALL salvar o QR em `data/qrcode.png`.

#### Scenario: Instância já conectada
- **WHEN** o comando roda com a instância em estado `open`
- **THEN** informa que já está conectada e não altera nada
