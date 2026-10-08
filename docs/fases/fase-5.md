# Fase 5 — Lembretes proativos

Status: **concluída em 08/10/2026**. Plano aprovado em 08/10/2026, sem resposta às dúvidas; valem os padrões: resumo vazio não é enviado; fatura avisa mesmo com R$ 0,00; dia inteiro avisa às 09:00 da véspera; antecedência padrão continua 1 dia.

Objetivo (do `SPEC.md`): os três jobs agendados e a tabela `sent_reminders`.

Critério de aceite: um evento criado para daqui a 70 min, com lembrete de 60, dispara **uma vez só**.

## Os três jobs (do `SPEC.md`)

| Job | Quando | O que envia |
| --- | --- | --- |
| Resumo do dia | 07:30, todos os dias | Eventos de hoje e de amanhã; aniversários dos próximos 7 dias |
| Lembrete de evento | a cada 5 min | Eventos cujo `início - remind_minutes` caiu na janela |
| Fechamento de fatura | 09:00, 2 dias antes do fechamento de cada cartão | Total parcial da fatura daquele cartão, com o vencimento |

Mensagens com **template fixo, sem LLM** (custo zero), em português, curtas, registradas em `messages` (`direction='out'`) e com a marca `🤖 ` no modo provisório.

## Arquivos

```text
app/
  scheduler.py                       # APScheduler (AsyncIOScheduler, fuso America/Sao_Paulo) + registro dos jobs
  reminders/
    __init__.py
    jobs.py                          # daily_summary(now), event_reminders(now), statement_alerts(now): funções puras de "o que enviar"
    templates.py                     # textos das mensagens
    delivery.py                      # envia pelo canal, grava em messages e em sent_reminders (idempotente)
  db/models.py                       # + SentReminder
  db/migrations/versions/0004_sent_reminders.py
  main.py                            # liga e desliga o scheduler no lifespan
tests/unit/
  test_reminder_jobs.py              # clock fixo: janelas, recorrência, dia inteiro, fatura (último dia do mês)
  test_reminder_delivery.py          # idempotência: rodar duas vezes não reenvia; falha no envio não marca como enviado
```

## Decisões

1. **APScheduler dentro do processo do FastAPI** (como no `SPEC.md`), em `AsyncIOScheduler` com `timezone=America/Sao_Paulo`.
   - Os jobs só decidem **o que** enviar a partir de um `now` injetado; quem envia é `delivery.py`. Isso deixa tudo testável com clock fixo, sem esperar o relógio.
2. **`sent_reminders` generalizada** para servir aos três jobs, não só a eventos.
   - Colunas: `kind` (`evento`/`resumo`/`fatura`), `ref_id` (evento ou cartão; vazio no resumo), `occurrence_at` (ocorrência do evento, dia do resumo ou fechamento da fatura), `minutes_before` (0 nos outros tipos) e `sent_at`.
   - Chave única em `(kind, ref_id, occurrence_at, minutes_before)`.
   - O `SPEC.md` só cita `(event_id, occurrence_at, minutes_before)`: **proposta de ajuste** registrada lá.
3. **Envio idempotente**: primeiro reserva a linha em `sent_reminders` (`INSERT … ON CONFLICT DO NOTHING`), depois envia.
   - Se o envio falhar, a reserva é desfeita para tentar de novo no próximo ciclo.
   - Dois ciclos sobrepostos nunca mandam duas vezes.
4. **Janela do lembrete de evento**: a cada 5 min, olha os lembretes devidos nas **últimas 6 h** cujo evento **ainda não começou**.
   - Se o Mac dormiu ou o app caiu, o lembrete chega atrasado, mas chega.
   - Lembrete de evento que já passou não é enviado.
   - A deduplicação garante uma vez só.
5. **Recorrência**: as ocorrências vêm de `app/domain/recurrence.py` (a mesma da busca). Aniversário anual gera lembrete todo ano.
6. **Eventos de dia inteiro** (aniversário, prazo): `remind_minutes` conta a partir das **09:00** do dia, não da meia-noite. O padrão de 1 dia avisa às 09:00 da véspera, não à meia-noite (dúvida 2).
7. **Fatura**:
   - O fechamento efetivo vem de `billing.closing_date` (ajuste do último dia do mês: o Nubank fecha 31/10, então o aviso sai em 29/10).
   - O total parcial é somado em SQL, pela mesma consulta de `total_fatura`.
   - Cartão sem gasto na fatura recebe o aviso também, com total R$ 0,00 (dúvida 1).
8. **Resumo do dia**: hoje e amanhã (com hora), mais aniversários dos próximos 7 dias. Dia sem nada: dúvida 1.
9. **Um processo só**: o uvicorn continua com 1 worker. Com mais de um, cada worker teria o seu scheduler; a deduplicação seguraria, mas não vale a pena.
10. **No modo provisório (`SELF_CHAT_MODE`)**, os lembretes chegam na conversa consigo mesmo e **não fazem o celular tocar**. É o risco já aceito no `SPEC.md`; com o chip dedicado, isso se resolve.
11. **Enquanto o bot roda no Mac** (até a fase 6), lembrete só sai com o Mac ligado. Atrasos de até 6 h são recuperados (decisão 4).

## Testes

- Jobs com clock fixo:
  - evento às 15:10 com lembrete de 60 → devido às 14:10: não envia às 14:05, envia às 14:10, não reenvia às 14:15;
  - evento que já começou não envia;
  - aniversário anual na véspera às 09:00;
  - lembretes múltiplos (`[1440, 60]`);
  - evento excluído não envia.
- Fatura:
  - o Nubank (fecha no último dia) avisa em 29/10 e em 28/11 (novembro tem 30 dias);
  - o cartão que fecha dia 10 avisa no dia 8;
  - o total bate com a soma em SQL e ignora gastos desfeitos.
- Resumo: formato com hoje, amanhã e aniversários; dia vazio conforme a dúvida 1.
- Entrega: reserva → envio → registro em `messages`; falha no envio libera a reserva; dois ciclos simultâneos mandam uma vez só.
- **Aceite real**: pelo WhatsApp, "me lembra de X daqui a 70 minutos, com aviso 1 hora antes". O lembrete deve chegar uma vez, ~10 min depois; confiro `sent_reminders`.

## Dúvidas para você

1. **Dia sem nada**: o resumo das 07:30 manda "Nada na agenda hoje" ou fica em silêncio? E cartão sem gasto, avisa o fechamento mesmo assim?
2. **Eventos de dia inteiro**: avisar às 09:00 da véspera (proposta) ou outro horário?
3. **Antecedência padrão**: hoje todo evento nasce com aviso de 1 dia antes. Para compromisso com hora, prefere **1 dia + 1 hora antes**?

---

# Relatório da fase 5

## O que foi feito

- Migração `0004`: `sent_reminders` generalizada (`kind`, `ref_id`, `occurrence_at`, `minutes_before`) com chave única. `SPEC.md` atualizado.
- `app/reminders/jobs.py`: `event_reminders`, `daily_summary`, `statement_alerts`, funções puras de "o que enviar" a partir de um `now`.
- `app/reminders/templates.py`: textos fixos, sem LLM.
- `app/reminders/delivery.py`: reserva (`ON CONFLICT DO NOTHING`), envia, registra em `messages`; se o envio falha, libera a reserva.
- `app/scheduler.py`: APScheduler `AsyncIOScheduler` (America/Sao_Paulo); resumo 07:30, lembretes a cada 5 min (primeiro ciclo logo na subida), fatura 09:00; `coalesce`, `max_instances=1`. Desligável por `SCHEDULER_ENABLED`.
- Padrões aplicados (dúvidas sem resposta):
  - resumo vazio não é enviado;
  - fatura avisa mesmo com R$ 0,00;
  - dia inteiro conta a partir das 09:00 (véspera às 09:00);
  - antecedência padrão continua 1 dia.
- 212 testes unitários: janela, atraso de até 6 h, evento já começado, várias antecedências, aniversário anual, excluído, resumo, Nubank no último dia (31/10 → aviso 29/10; 30/11 → aviso 28/11), desfeitos fora da soma, entrega uma vez só (inclusive 5 ciclos simultâneos) e falha no envio.

## Critério de aceite

| Critério | Resultado |
| --- | --- |
| Evento com lembrete dispara uma vez só | **ok** em 08/10. O Kaio pediu "me lembre em 5 minutos de beber água" às 14:26; o bot criou o evento às 14:31 com `remind_minutes={0}` (também foi ao Google Calendar). O aviso "⏰ Beber água: hoje às 14:31." saiu às 14:34:47, com uma única linha em `sent_reminders`. O formato diferiu do roteiro (5 min com aviso na hora, em vez de 70 min com aviso de 60), mas exercita a mesma regra. |

## Observações

- **Precisão**: com o ciclo de 5 min do `SPEC.md`, o aviso pode chegar até 5 min atrasado (aqui, 3m47s). Proposta pendente: ciclo de 1 min.
- **Modo provisório**: os avisos chegam na conversa consigo mesmo e não fazem o celular tocar.
- **Mac ligado**: até a fase 6, lembrete só sai com o Mac ligado (atrasos de até 6 h são recuperados).
