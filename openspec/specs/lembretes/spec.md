# lembretes Specification

## Purpose
Avisar o dono sem que ele pergunte (resumo do dia, lembretes de eventos e fechamento de fatura), com textos fixos, sem LLM e sem repetir.

## Requirements

### Requirement: Jobs agendados
O APScheduler, no mesmo processo do FastAPI e no fuso America/Sao_Paulo, SHALL rodar o resumo do dia às 07:30, os lembretes de evento a cada 5 minutos (e logo na subida) e o alerta de fatura às 09:00; os jobs decidem o que enviar a partir de um `now` injetado.

#### Scenario: App sobe
- **WHEN** o app inicia
- **THEN** o ciclo de lembretes roda imediatamente para recuperar atrasos

### Requirement: Lembrete de evento
Para cada antecedência em `remind_minutes`, o aviso SHALL sair quando `início - antecedência` já passou há no máximo 6 h e o evento não começou há mais de 5 min; eventos de dia inteiro contam a partir das 09:00 do dia; recorrentes geram aviso a cada ocorrência; excluídos não avisam.

#### Scenario: Aniversário
- **WHEN** há um aniversário anual em 14/03 com antecedência de 1 dia
- **THEN** "🎂 Amanhã é aniversário: Mariana (14/03)." sai em 13/03 às 09:00 de todo ano

### Requirement: Resumo do dia
Às 07:30 o sistema SHALL enviar os eventos de hoje e de amanhã e os aniversários dos próximos 7 dias; dia sem nada não gera mensagem.

#### Scenario: Dia vazio
- **WHEN** não há eventos nem aniversários
- **THEN** nada é enviado

### Requirement: Fechamento de fatura
Dois dias antes do fechamento efetivo de cada cartão de crédito, às 09:00, o sistema SHALL enviar o total parcial (somado em SQL, sem desfeitos), o número de lançamentos e o vencimento, mesmo com total zero.

#### Scenario: Cartão que fecha no último dia
- **WHEN** o cartão fecha no último dia do mês
- **THEN** o aviso de outubro sai em 29/10 e o de novembro em 28/11

### Requirement: Uma vez só
Cada aviso SHALL ser reservado em `sent_reminders (kind, ref_id, occurrence_at, minutes_before)` com chave única antes do envio; falha no envio libera a reserva para o próximo ciclo; o envio é registrado em `messages`.

#### Scenario: Ciclos simultâneos
- **WHEN** dois ciclos tentam enviar o mesmo aviso
- **THEN** só um envia
