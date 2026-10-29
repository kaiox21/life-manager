## MODIFIED Requirements

### Requirement: Recebimento de mídia
O canal SHALL ler áudio, imagem e documento PDF de `data.message.base64` (webhook com `base64: true`) e, se faltar, baixar de novo por `getBase64FromMediaMessage` enviando a mensagem original; áudio acima de 3 min, imagem acima de 10 MB e PDF acima de 10 MB são recusados com resposta curta; o PDF (`documentMessage` com `mimetype` `application/pdf`, legenda como texto) segue para a importação de fatura; vídeo, figurinha e documentos que não são PDF são ignorados.

#### Scenario: Webhook sem o arquivo
- **WHEN** a foto chega sem `base64`
- **THEN** o canal baixa de novo pela Evolution e segue o fluxo

#### Scenario: Fatura anexada
- **WHEN** chega um documento PDF de 300 KB com a legenda "nubank"
- **THEN** o canal entrega o PDF e a legenda à importação de fatura

#### Scenario: Planilha anexada
- **WHEN** chega um documento `.xlsx`
- **THEN** a mensagem é ignorada, sem resposta

### Requirement: Mídia não é guardada
Fotos, áudios e PDFs SHALL ser processados em memória e descartados; `messages.media_path` fica vazio e só a transcrição (áudio) ou a legenda (foto e PDF) fica em `messages.body`.

#### Scenario: Depois de processar
- **WHEN** um áudio é transcrito
- **THEN** não existe arquivo de mídia em disco e o corpo da mensagem é a transcrição

#### Scenario: Depois de ler a fatura
- **WHEN** uma fatura em PDF é lida
- **THEN** não existe o PDF em disco e o corpo da mensagem é só a legenda
