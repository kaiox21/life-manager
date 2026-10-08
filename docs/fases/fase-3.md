# Fase 3 — Agenda + Google Calendar

Status: **concluída em 08/10/2026**. Plano aprovado em 08/10/2026; relatório no fim deste arquivo.

Objetivo (do `SPEC.md`): ferramentas de evento e de pessoa, sync com o Google Calendar.

Critérios de aceite:

1. "aniversário da minha irmã dia 14 de março" cria um evento anual que aparece no Google Calendar.
2. "quando é o aniversário dela?" responde certo.

Também nesta fase:

- A prova volta a avaliar o agente nos 56 casos, com os 16 de agenda incluídos.
- Corrijo o classificador, que confundia "aniversário da minha irmã" com `pessoa` (fase 2).

## Arquivos

```text
app/
  db/models.py                       # + Person, Event
  db/migrations/versions/0003_agenda.py
  domain/recurrence.py               # próxima(s) ocorrência(s) a partir de rrule (python-dateutil)
  agent/tools/agenda.py              # criar_evento, buscar_eventos, atualizar_evento, remover_evento
  agent/tools/pessoas.py             # gerenciar_pessoa + resolução "minha irmã" -> Mariana
  agent/tools/confirmacao.py         # + executor de remover_evento
  agent/prompt.py                    # + tabela de eventos dos próximos 7 dias e pessoas cadastradas
  agent/intent.py                    # exemplos para separar agenda de pessoa
  integrations/gcal.py               # cliente do Calendar + sync banco -> Calendar
  agent/service.py                   # dispara o sync depois do commit
tests/
  unit/test_recurrence.py
  unit/test_tools_agenda.py          # contra o Postgres de teste, clock fixo
  unit/test_gcal_sync.py             # com Calendar falso, sem rede
  eval/test_eval.py                  # agenda passa a ser avaliada no agente; fixtures de pessoas
```

## Decisões

1. **Tabelas `people` e `events`** exatamente como no `SPEC.md` (migração `0003`).
2. **Datas dos eventos.** `starts_at` sempre com fuso. Hora sem fuso vinda do modelo é interpretada como America/Sao_Paulo.
   - **Dia inteiro** (`all_day`, aniversário, prazo sem hora): gravado à meia-noite local. No Calendar vira `start.date`, com fim exclusivo no dia seguinte.
3. **Evento com hora e sem `ends_at`.** No banco o `ends_at` fica vazio; no Calendar vai com 1 h de duração, porque o Calendar exige fim.
4. **Recorrência.** `rrule` é texto como `FREQ=YEARLY`. No Calendar vai como `RRULE:FREQ=YEARLY`, com `timeZone` America/Sao_Paulo.
   - `app/domain/recurrence.py` calcula as ocorrências com `python-dateutil`. Assim, `buscar_eventos` de 14/03 a 14/03 acha um aniversário criado com outro ano, e "quando é o aniversário dela?" responde com a **próxima** data.
   - A fase 5 (lembretes) reaproveita isso.
5. **Ferramentas** com nomes e argumentos do `SPEC.md`:
   - **`criar_evento`**: resolve `person` por nome, `relation` ou `aliases`. Pessoa inexistente devolve erro, e o modelo pergunta o nome (caso a05).
   - **`buscar_eventos`**: devolve até 20 eventos ordenados pela próxima ocorrência, com `id` para o modelo usar depois.
   - **`atualizar_evento`**: recebe `event_id` + `campos`; o modelo busca antes (caso a15).
   - **`remover_evento`**: **sempre** cria pendência; o "sim" faz exclusão lógica e apaga no Calendar.
   - **`gerenciar_pessoa`**: cria ou encontra pela combinação nome + relação.
6. **Sync banco → Calendar, sem perder gravação.**
   - A ferramenta só grava no banco. Depois do commit, uma tarefa em segundo plano sincroniza os eventos com `gcal_synced_at` vazio ou mais antigo que `updated_at`.
   - Se o Calendar falhar, o evento continua no banco e é sincronizado na próxima mensagem ou quando o app subir.
   - `gcal_event_id` guarda o vínculo; exclusão lógica vira `events.delete` no Calendar.
   - Unidirecional, como no `SPEC.md`.
7. **Lembretes do Calendar desligados** (`reminders.useDefault=false`): quem avisa é o bot (fase 5), e assim não chega aviso em dobro (dúvida 2).
8. **Credencial do Google como variável de ambiente.** `GOOGLE_SERVICE_ACCOUNT_JSON` leva o JSON em base64 dentro do `.env`. É desvio do `.env.example`, que previa `GOOGLE_SERVICE_ACCOUNT_FILE`: o Docker Desktop não monta arquivos de `~/Downloads` (o mesmo problema da fase 1). O arquivo continua aceito se você mover o projeto ou liberar a pasta.
9. **Cliente**: `google-api-python-client` + `google-auth` (do stack do `SPEC.md`), chamado via `asyncio.to_thread` porque o cliente é síncrono. Só `app/integrations/gcal.py` conhece a API do Google.
10. **Prompt** ganha a lista de eventos dos próximos 7 dias (o `SPEC.md` pede) e as pessoas cadastradas com relação ("Mariana (irmã)").
11. **Classificador**: exemplos explícitos.
    - "aniversário da minha irmã é dia 14 de março" → `agenda`.
    - `pessoa` só para cadastrar ou corrigir uma pessoa **sem** data ou evento.
    - "manda mensagem pro Carlos" → `fora_do_escopo`.
12. **Prova**: o agente passa a rodar nos 56 casos; as fixtures de pessoas (Mariana irmã, Carlos chefe) entram no banco de teste. O critério de 90% vale sobre os 56. Rodo com o `gpt-5-nano` (o modelo atual).

## Testes

- `recurrence`: ocorrências anuais com virada de ano, 29/02 em ano não bissexto (o `dateutil` pula o ano; testado e registrado), evento sem `rrule`.
- Ferramentas contra o Postgres de teste:
  - "minha irmã" resolve Mariana; "minha mãe" sem cadastro devolve erro.
  - Busca por período acha aniversário recorrente.
  - Remoção só depois de confirmar.
  - Atualizar marca o evento para novo sync.
- Sync com Calendar falso:
  - mapeamento de dia inteiro, hora com fuso e `RRULE`;
  - falha do Calendar não perde o evento e tenta de novo depois;
  - exclusão lógica apaga no Calendar.
- `uv run pytest -m eval` com os 56 casos.
- Aceite real pelo WhatsApp e conferência no app do Google Calendar.

## O que você precisa fazer (passo a passo detalhado no fim da fase)

1. No Google Cloud Console: criar (ou usar) um projeto, ativar a **Google Calendar API**, criar uma **service account** e baixar a chave JSON.
2. No Google Calendar: compartilhar o calendário escolhido (dúvida 1) com o e-mail da service account, com permissão **"Fazer alterações nos eventos"**.
3. Me passar o ID do calendário. A chave JSON vai direto para o `.env`, sem colar na conversa; deixo um comando pronto para isso.

## Dúvidas para você

1. **Qual calendário recebe o espelho** (questão em aberto do `SPEC.md`):
   - **Calendário dedicado "Assistente" (recomendado)**: dá para esconder, mudar a cor ou apagar tudo de uma vez, sem misturar com o resto.
   - **Principal**: os eventos aparecem junto com os seus.
2. **Avisos do Calendar**: desligo (decisão 7) e deixo os avisos só para o bot na fase 5? Ou prefere também a notificação do Google no celular?
3. **`gerenciar_pessoa` também no grupo `agenda`?** Hoje o `SPEC.md` a põe só no grupo `pessoa`. Numa frase como "minha mãe se chama Ana e faz aniversário 2 de maio", o agente de agenda precisaria cadastrar a pessoa e criar o evento na mesma conversa. Proposta: incluir no grupo `agenda` também (mudança pequena no `SPEC.md`).
4. **Pessoas reais**: o aceite usa a sua irmã de verdade. Nome e relação ficam só no banco local, como os cartões. A prova pública continua com Mariana e Carlos fictícios. Ok?

## Respostas (08/10/2026)

1. Calendário: **principal** (o pessoal). Registrado no `SPEC.md`.
2. Avisos do Google desligados nos eventos do bot (padrão do plano).
3. `gerenciar_pessoa` também no grupo `agenda` (padrão do plano; `SPEC.md` atualizado).
4. Pessoas reais só no banco local.

---

# Relatório da fase 3

## O que foi feito

- Migração `0003`: `people` e `events`.
- `app/domain/recurrence.py`: ocorrências e próxima ocorrência via `python-dateutil`.
- Ferramentas `criar_evento`, `buscar_eventos`, `atualizar_evento`, `remover_evento` (sempre com confirmação) e `gerenciar_pessoa` (grupos `pessoa` e `agenda`). Uma ferramenta passou a poder pertencer a mais de um grupo.
- `app/integrations/gcal.py`: sync banco → Calendar depois de cada resposta e quando o app sobe. Uma transação por evento, com `SKIP LOCKED`; falha não perde o evento; evento apagado à mão no Calendar é recriado.
- `app/integrations/gcal_setup.py`: grava a chave (base64) e o calendário no `.env` só depois de criar e apagar um evento de teste.
- Prompt com a agenda dos próximos 7 dias e as pessoas cadastradas. Regras novas:
  - pergunta sobre agenda sempre consulta `buscar_eventos`;
  - nunca mostrar ids.
- Laço: na intenção `agenda`, resposta sem ferramenta e sem pergunta conta como falha (como em `consulta_gasto`).
- Classificador com exemplos que separam `agenda` de `pessoa` e mandam "avisar alguém" para `fora_do_escopo`.
- Prova: o agente roda nos 56 casos; `person` é comparado depois da resolução, como `payment_method`.
- 188 testes unitários, sem rede.

## Critérios de aceite

| Critério | Resultado |
| --- | --- |
| Aniversário da irmã cria evento anual que aparece no Google Calendar | **ok** em 08/10 11:34–11:39. Como não havia irmã cadastrada, o bot perguntou o nome. Depois cadastrou a pessoa e criou o evento de dia inteiro com `FREQ=YEARLY`. Log: `calendar: 1 criados, 0 falhas`; o Kaio conferiu no Google Calendar. |
| "quando é o aniversário dela?" responde certo | **ok**. 11:42: resposta certa, mas tirada do histórico sem ferramenta, o que motivou a regra nova. 11:47, depois do ajuste: chamou `buscar_eventos` e respondeu 31/10/2026 (sábado). |

## Prova (gpt-5-nano em classificador, principal e escalada)

| Grupo | Classificador | Agente |
| --- | --- | --- |
| agenda | 16/16 | 14/16 |
| gasto | 24/24 | 23/24 |
| consulta_gasto | 10/10 | 9/10 |
| confirmacao | 2/2 | 2/2 |
| fora_do_escopo | 3/4 | 4/4 |
| **total** | 55/56 | **52/56 (93%)** |

Rodada de 08/10, antes do último ajuste de prompt; custo US$ 0,04; ~40 s por caso.

A rodada depois do ajuste caiu por falha de conexão a partir do 9º caso (instabilidade de rede no Mac; o gateway e o saldo estavam ok). Está sendo refeita, e o placar entra aqui quando terminar.

## Desvios

1. Chave do Google no `.env` em base64 (`GOOGLE_SERVICE_ACCOUNT_JSON`), porque o Docker Desktop não monta arquivos de `~/Downloads`.
2. Evento com hora e sem fim vai ao Calendar com 1 h.
3. `gerenciar_pessoa` também no grupo `agenda` (`SPEC.md` atualizado).

## Fica para depois

- **Latência**: 20–40 s por resposta (93 s num caso, com a rede instável). Testar `REASONING_EFFORT=minimal` com a prova.
- **a12**: o modelo responde "tenho algo na sexta?" pela tabela de 7 dias do prompt; com a regra nova deve passar a consultar. Confirmar no próximo placar.
- O bot ofereceu "Quer que eu coloque um lembrete?"; lembretes chegam na fase 5.
