## MODIFIED Requirements

### Requirement: Uma vez só
Cada aviso SHALL ser reservado em `sent_reminders (kind, ref_id, occurrence_at, minutes_before)` com chave única antes do envio; falha no envio libera a reserva para o próximo ciclo; o envio é registrado em `messages` com o tipo `aviso_<kind>` (por exemplo `aviso_evento`, `aviso_fatura`, `aviso_vagas`) e o texto enviado.

#### Scenario: Ciclos simultâneos
- **WHEN** dois ciclos tentam enviar o mesmo aviso
- **THEN** só um envia

#### Scenario: Registro do envio
- **WHEN** um lembrete de evento é enviado
- **THEN** `messages` ganha uma linha de saída com o tipo `aviso_evento` e o texto do lembrete
