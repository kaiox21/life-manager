# Fase 4 — Áudio e foto

Status: **implementada e em uso; aceite parcial** (08/10/2026). Plano aprovado em 08/10/2026. O teste real da foto ficou para depois, por decisão do Kaio; o áudio fica como está.

Objetivo (do `SPEC.md`): download de mídia, transcrição, recibo por visão e fluxo de confirmação.

Critérios de aceite:

1. Foto de cupom gera um resumo e só grava depois do "sim".
2. Áudio de gasto grava depois da confirmação.

## Fatos conferidos (08/10/2026)

- **Mídia no webhook**: com `base64: true` (já ligado na instância desde a fase 1), a Evolution 2.3.7 manda o arquivo em `data.message.base64`. Se faltar (download falhou), existe `POST /chat/getBase64FromMediaMessage/{instance}`.
- **`faster-whisper` 1.2.1** roda em arm64: o `ctranslate2` 4.8.2 tem wheel `manylinux aarch64` para Python 3.12. Funciona no Mac (Docker) e no VPS Oracle ARM.
- **Visão**: o `gpt-5-nano` aceita imagem no catálogo do gateway (`vision`). A imagem vai como `image_url` com data URI base64, no formato da API da OpenAI.

## Arquivos

```text
app/
  types.py                     # IncomingMessage ganha media: Media | None (bytes, mimetype, segundos)
  channel/evolution.py         # extrai base64/mimetype/duração; fallback getBase64FromMediaMessage
  media.py                     # grava o arquivo em /data/media, limites de tamanho e duração
  integrations/transcribe.py   # interface Transcriber + FasterWhisper (modelo carregado uma vez)
  agent/service.py             # áudio -> transcrição -> fluxo normal (source='audio');
                               # foto -> grupo gasto com bloco de imagem (source='foto')
  agent/llm.py                 # mensagens com conteúdo multimodal
  handler.py / main.py         # aceita audio e image; transcriber no lifespan
  db/repo.py                   # messages.media_path e body = transcrição/legenda
docker-compose.yml             # volume "media" e cache do modelo do whisper
tests/
  fixtures/evolution/          # áudio e imagem com base64 pequeno (gerados, sem dado real)
  unit/test_media.py           # parse de mídia, limites, fallback, gravação
  unit/test_audio_foto.py      # fluxo com Transcriber falso e LLM falso: pendência e "sim"
```

## Decisões

1. **Áudio**:
   - Transcrevo e sigo o fluxo normal (classificador e agente) com `source='audio'`, o que já faz `lancar_gasto` e `criar_evento` virarem pendência.
   - A resposta começa com o que entendi: `🎙️ "paguei 120 de gasolina no pix"`. Assim dá para ver um erro de transcrição antes do "sim".
2. **Foto**:
   - Vai direto ao grupo `gasto` (recibo), sem classificador, com o bloco de imagem e a legenda, se houver. `source='foto'`, então `lancar_gasto` vira pendência.
   - O prompt pede para extrair estabelecimento, valor total, data e meio de pagamento, se aparecer no cupom.
   - Imagem que não é recibo: o modelo responde que só lê recibos.
3. **Confirmação continua valendo depois de uma pergunta.** Se o cupom não diz o cartão, o bot pergunta, e a resposta ("nubank") chega como texto. Sem cuidado, esse texto gravaria direto, sem o "sim" exigido para foto e áudio.
   - Regra: se a mensagem anterior do dono, de até 15 min atrás, foi foto ou áudio, e a última resposta do bot foi uma pergunta, a mensagem atual herda `source` (`foto`/`audio`).
   - No histórico, a foto aparece como `[foto de recibo]` mais a legenda, e o áudio como a transcrição. A resposta do bot (com os valores lidos) também está lá, então o modelo não perde os dados.
4. **Transcrição local com `faster-whisper`** (questão em aberto do `SPEC.md` para a fase 4; o `.env.example` já trazia `TRANSCRIBE_BACKEND=faster-whisper`).
   - Modelo `small`, `int8`, `language="pt"`, com VAD ligado. É grátis e o áudio não sai da máquina.
   - O modelo (~0,5 GB) baixa uma vez para um volume Docker.
   - Configurável por `.env`: `WHISPER_MODEL=small|medium`.
   - Roda em thread para não travar o servidor.
5. **Limites**:
   - áudio até 3 min;
   - imagem até 10 MB;
   - acima disso, resposta curta pedindo algo menor.
   - Vídeo, documento e figurinha continuam ignorados.
6. **Arquivos**: guardados em `/data/media/AAAA-MM/<id>.<ext>` num volume, com `messages.media_path` apontando para ele. A retenção depende da dúvida 2.
7. **Fallback de download**: sem `base64` no webhook, peço à Evolution pela rota `getBase64FromMediaMessage`. Só `app/channel/` conhece essa rota.
8. **`agent_runs`** registra também a transcrição (tempo e modelo do whisper no campo `tools_called`, como etapa `transcricao`).

## Testes

- Unitários, sem rede e sem whisper de verdade (`Transcriber` falso):
  - parse de áudio e imagem com base64;
  - fallback;
  - limites;
  - gravação do arquivo;
  - áudio → transcrição → pendência → "sim" → gravado;
  - foto → bloco de imagem chega ao LLM → pendência;
  - pergunta do bot no meio herda `source`.
- Um teste de integração opcional (marcador `whisper`, fora do padrão) que transcreve um áudio curto gerado com `say` do macOS. Ele confirma que o modelo carrega e entende português.
- A prova roda de novo (o prompt muda), com o critério de 90%.
- Aceite real: foto de um cupom e um áudio de gasto pelo WhatsApp.

## Dúvidas para você

1. **Transcrição local (recomendado) ou por API?**
   - Local (`faster-whisper`): grátis e privada, cerca de 2–5 s para 10 s de áudio no Mac e um pouco mais no VPS.
   - API (ex.: OpenAI `gpt-4o-mini-transcribe`): mais rápida, mas precisa de outra chave e o áudio sai da máquina.
2. **Guardar as fotos e os áudios?**
   - Apagar o arquivo depois de processar e guardar só o texto (transcrição e o que foi lido do cupom).
   - Guardar por 30 dias (dá para conferir depois).
   - Guardar sempre.
3. **Comprovante de Pix (print da tela)** também vale como "recibo"? Proposta: sim, mesmo fluxo da foto.

## Respostas (08/10/2026)

1. Transcrição **local** (`faster-whisper`).
2. Mídia **não é guardada**: processada em memória e descartada; `media_path` fica vazio.
3. Print de comprovante de Pix vale como recibo.

`SPEC.md` atualizado com as três decisões.

---

# Relatório da fase 4

## O que foi feito

- `app/channel/evolution.py`: lê áudio e imagem (`data.message.base64`, mimetype, duração). Quando o webhook vem sem o arquivo, baixa de novo por `getBase64FromMediaMessage`, mandando a mensagem original (a Evolution não guarda mensagens: `DATABASE_SAVE_DATA_NEW_MESSAGE=false`).
- `app/integrations/transcribe.py`: `faster-whisper` `small` int8, `language=pt`, VAD, carregado em segundo plano quando o app sobe.
  - O vocabulário de dicas inclui termos fixos ("Pix", "fatura"...) e os nomes cadastrados (meios e pessoas), lidos do banco na hora, sem dado real no código.
  - Sem as dicas, "Pix" saía "PICS".
- **Áudio** → transcrição → fluxo normal com `source='audio'`. A resposta começa com `🎙️ "<transcrição>"`, e a transcrição vira o corpo da mensagem.
- **Foto** → grupo `gasto` direto, com bloco de imagem e `source='foto'`. O prompt ganhou regras para recibo e comprovante de Pix.
- **Origem herdada**: resposta a uma pergunta do bot sobre foto ou áudio dos últimos 15 min herda `source`, então a confirmação continua obrigatória.
- Limites: áudio ≤ 3 min, imagem ≤ 10 MB; vídeo, documento e figurinha são ignorados.
- `agent_runs` registra a etapa `transcricao` (modelo e ms).
- Docker: volume `whisper_models` (o modelo baixa uma vez); imagem do app ~1,8 GB.
- `av` fixado em `<17`: o `faster-whisper` 1.2.1 chama `av.open(..., metadata_errors=...)`, que o PyAV 19 removeu.
- 198 testes unitários com transcrição e LLM falsos. Mais o teste `-m whisper`: áudio gerado com `say` transcrito como "Paguei 120 reais de gasolina no Pix." em 2,1 s, com o modelo carregado.

## Critérios de aceite

| Critério | Resultado |
| --- | --- |
| Foto de cupom gera resumo e só grava depois do "sim" | **coberto por teste unitário** (`test_foto_vai_como_imagem_ao_grupo_gasto_e_vira_pendencia`, `test_resposta_a_pergunta_sobre_foto_continua_exigindo_confirmacao`). Teste real adiado pelo Kaio. |
| Áudio de gasto grava depois da confirmação | **parcial no uso real** (08/10 13:41–13:53): dois áudios transcritos em ~2 s; o bot respondeu com o eco 🎙️ e perguntou o cartão e depois o valor. O whisper ouviu "44 créditos" em vez de "44 reais", então nada foi gravado. O fluxo completo (pendência → "sim" → gravado com `source='audio'`) está coberto por `test_audio_de_gasto_pede_confirmacao_e_grava_no_sim`. O Kaio disse que quase não vai usar áudio e preferiu deixar como está. |

## Prova (08/10/2026, depois das regras de recibo, "não pergunte o que dá para deduzir" e da correção "Carlos (chefe)")

| Grupo | Classificador | Agente |
| --- | --- | --- |
| agenda | 16/16 | 13/16 |
| gasto | 24/24 | 24/24 |
| consulta_gasto | 10/10 | 10/10 |
| confirmacao | 2/2 | 2/2 |
| fora_do_escopo | 3/4 | 4/4 |
| **total** | 55/56 | **53/56 (95%)** |

Custo US$ 0,04. A rodada anterior, sem essas correções, deu 88%.

As 3 falhas de agenda são perguntas demais: o ano do aniversário (a03), a duração da reunião (a06) e o mês do "dia 31" (a07). Próximo ajuste de prompt: data sem mês = mês atual (ou o próximo, se já passou); aniversário = próxima ocorrência; reunião sem fim = sem `ends_at`.

## Fica para depois

- Teste real da foto.
- Se o áudio for usado com frequência: `WHISPER_MODEL=medium` (erra menos, ~2–3× mais lento).
