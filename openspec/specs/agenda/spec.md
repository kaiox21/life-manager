# agenda Specification

## Purpose
Guardar compromissos, provas, aniversários, prazos e lembretes no banco (fonte de verdade), resolver referências a pessoas e espelhar tudo no Google Calendar.

## Requirements

### Requirement: Criar evento
`criar_evento(title, kind, starts_at, ends_at?, all_day?, rrule?, person?, remind_minutes?, location?, notes?)` SHALL gravar com fuso (hora sem fuso é America/Sao_Paulo); `kind` é `compromisso`, `prova`, `aniversario`, `prazo` ou `lembrete`; aniversário vira dia inteiro com `FREQ=YEARLY`; dia inteiro é gravado à meia-noite local; antecedência padrão de lembrete é 1 dia; origem áudio ou foto exige confirmação.

#### Scenario: Dentista na sexta
- **WHEN** chega "coloca na agenda dentista sexta às 14h"
- **THEN** cria um compromisso em 09/10/2026 às 14:00 e responde com título, data e hora

### Requirement: Pessoas
`gerenciar_pessoa(name, relation?, aliases?)` SHALL criar ou atualizar pelo nome; referências como "minha irmã" SHALL ser resolvidas por nome, apelidos ou relação (ignorando "(relação)" copiado do prompt); pessoa inexistente devolve erro para o modelo perguntar o nome antes de criar o evento. Pessoas reais ficam só no banco local.

#### Scenario: Mãe não cadastrada
- **WHEN** chega "aniversário da minha mãe é 2 de maio" sem mãe cadastrada
- **THEN** o bot pergunta o nome, cadastra e só então cria o evento

### Requirement: Buscar eventos
`buscar_eventos(query?, kind?, de?, ate?, person?)` SHALL considerar as ocorrências de eventos recorrentes (`app/domain/recurrence.py`); sem período, devolve a próxima ocorrência, com os eventos únicos já passados no fim; no máximo 20 itens, com `id` para atualizar ou remover. Perguntas sobre agenda sempre passam por essa ferramenta.

#### Scenario: Quando é o aniversário
- **WHEN** chega "quando é o aniversário dela?" depois de um aniversário em 31/10
- **THEN** a resposta usa `buscar_eventos` e informa a próxima ocorrência

### Requirement: Atualizar e remover
`atualizar_evento(event_id, campos)` SHALL alterar só os campos enviados e marcar o evento para novo sync; `remover_evento(event_id)` SHALL sempre criar uma pendência e, confirmada, aplicar exclusão lógica.

#### Scenario: Cancelar reunião
- **WHEN** chega "cancela a reunião com o Carlos"
- **THEN** o bot busca primeiro, pede confirmação e só remove depois do "sim"

### Requirement: Espelho no Google Calendar
Eventos com `gcal_synced_at` vazio ou anterior a `updated_at` SHALL ser sincronizados banco → Calendar (unidirecional) depois de cada resposta e na subida do app, um por transação com `SKIP LOCKED`; dia inteiro vira `start.date` com fim exclusivo; evento com hora sem fim vai com 1 h; `rrule` vira `RRULE:`; avisos do Google ficam desligados; exclusão lógica apaga no Calendar; evento apagado à mão no Calendar é recriado; falha do Calendar não perde o evento. A conta é uma service account com o calendário principal compartilhado ("fazer alterações nos eventos"), chave em base64 no `.env`.

#### Scenario: Calendar fora do ar
- **WHEN** a criação no Calendar falha
- **THEN** o evento fica no banco e é sincronizado no próximo ciclo
