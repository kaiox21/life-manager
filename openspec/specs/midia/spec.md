# midia Specification

## Purpose
Aceitar áudio e foto de recibo como entrada, sem guardar os arquivos e sem abrir mão da confirmação.

## Requirements

### Requirement: Recebimento de mídia
O canal SHALL ler áudio e imagem de `data.message.base64` (webhook com `base64: true`) e, se faltar, baixar de novo por `getBase64FromMediaMessage` enviando a mensagem original; áudio acima de 3 min e imagem acima de 10 MB são recusados com resposta curta; vídeo, documento e figurinha são ignorados.

#### Scenario: Webhook sem o arquivo
- **WHEN** a foto chega sem `base64`
- **THEN** o canal baixa de novo pela Evolution e segue o fluxo

### Requirement: Mídia não é guardada
Fotos e áudios SHALL ser processados em memória e descartados; `messages.media_path` fica vazio e só a transcrição (áudio) ou a legenda (foto) fica em `messages.body`.

#### Scenario: Depois de processar
- **WHEN** um áudio é transcrito
- **THEN** não existe arquivo de mídia em disco e o corpo da mensagem é a transcrição

### Requirement: Áudio
O áudio SHALL ser transcrito localmente pelo `faster-whisper` (`WHISPER_MODEL`, padrão `small`, int8, `pt`, VAD), carregado em segundo plano na subida, com vocabulário de dicas (termos fixos mais nomes de meios e pessoas lidos do banco), e SHALL seguir o fluxo normal com `source='audio'`; a resposta começa com `🎙️ "<transcrição>"`.

#### Scenario: Gasto por áudio
- **WHEN** chega o áudio "paguei 120 de gasolina no pix"
- **THEN** a resposta mostra a transcrição, pede confirmação e só grava depois do "sim"

### Requirement: Foto de recibo
A foto SHALL ir ao grupo `gasto` como bloco de imagem (`image_url` com data URI), sem classificador, com `source='foto'`; recibo, cupom fiscal e print de comprovante de Pix valem; o modelo extrai estabelecimento, valor total, data e meio, e pergunta o meio quando não está claro.

#### Scenario: Cupom fiscal
- **WHEN** chega a foto de um cupom
- **THEN** o bot mostra o resumo e só grava depois do "sim"

### Requirement: Origem herdada
Uma mensagem de texto que responde a uma pergunta do bot sobre foto ou áudio dos últimos 15 minutos SHALL herdar a origem (`foto` ou `audio`), mantendo a confirmação obrigatória.

#### Scenario: Cartão informado depois da foto
- **WHEN** o bot pergunta "Qual cartão?" sobre um cupom e o usuário responde "nubank"
- **THEN** o lançamento vira pendência em vez de gravar direto
