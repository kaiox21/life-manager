## Context

- O núcleo tem o APScheduler (`app/scheduler.py`) com os jobs de lembretes, a entrega pelo WhatsApp (`app/reminders/delivery.py`, reserva em `sent_reminders`) e o registro de execuções (`agent_runs`).
- O adaptador da Anthropic ganhou ferramentas de servidor no `feat/jarvis-internet`: `server_tool(...)`, os blocos originais em `Completion.raw` e o custo por busca.
- Perfil do Kaio (13/10/2026):
  - **tipos:** estágio, bolsa de pesquisa, monitoria e ensino, júnior/trainee;
  - **local:** Brasília (presencial ou híbrido) ou remoto;
  - **áreas:** IA e dados, desenvolvimento web, direito + tecnologia;
  - **entrega:** WhatsApp e painel;
  - **restrição:** curso noturno, então a vaga tem que ser de dia, com até ~30 h por semana no estágio.

## Goals / Non-Goals

**Goals:** encontrar sem inventar, não repetir, custo baixo e previsível, texto da entrega sem LLM.

**Non-Goals:** ver a proposta.

## Decisions

1. **Uma rodada = uma conversa com o modelo e duas ferramentas:**
   - `web_search` (servidor; `max_uses` = `VAGAS_MAX_BUSCAS`, padrão 12; local Brasília/BR);
   - `registrar_vagas` (cliente; argumentos validados por Pydantic): uma lista com título, organização, tipo, local, prazo (AAAA-MM-DD ou nulo), url e resumo.
   - O prompt traz o perfil do `config/vagas.yaml`, a data de hoje e as consultas sugeridas, e manda terminar chamando `registrar_vagas` uma vez. Exemplos de consulta: "estágio desenvolvimento Brasília", "estágio remoto programação", "PIBIC UnB edital", "bolsa iniciação científica computação", "desenvolvedor júnior remoto Python", "monitoria computação UnB".
   - **Modelo:** `VAGAS_MODELO` (padrão `MODEL_PRIMARY`, o Haiku). Ler uns 10 resultados e filtrar é tarefa de leitura; o Haiku dá conta e custa centavos.

2. **Verificação do link (anti-invenção).**
   - As URLs permitidas são as dos blocos `web_search_tool_result` da própria rodada (`Completion.raw`).
   - Uma vaga só entra se a URL dela, normalizada, estiver nesse conjunto ou começar com uma delas (a página da vaga dentro de uma listagem conta).
   - O que não bate é descartado e contado no log.

3. **Normalização da URL:**
   - minúsculas no domínio, sem `www.` e sem fragmento;
   - sem parâmetros de rastreio (`utm_*`, `gclid`, `fbclid`, `ref`, `trk`);
   - sem barra final.
   - É a chave única de `job_leads`.

4. **Tabela `job_leads`:** id, `url` (única), título, organização, tipo, local, prazo (date, nulo), resumo, pontuação, `found_at`, `sent_at` (nulo), `dismissed_at` (nulo) e `run_id` (a rodada em `agent_runs`).
   - **Pontuação** (no código, sem LLM): +3 se a área é IA/dados, +2 web, +2 direito+tecnologia (por palavras no título e no resumo); +1 se o prazo é em até 7 dias.
   - A ordem da mensagem é pontuação decrescente e prazo crescente.

5. **Quando rodar:**
   - job diário às 08:00 que só executa se a última rodada (a última linha de `agent_runs` com canal `vagas`) tiver sido há 72 horas ou mais;
   - na subida do app, a mesma checagem (recupera a rodada perdida).
   - Assim não há estado novo: o próprio `agent_runs` diz quando foi a última.

6. **Entrega pelo WhatsApp:** texto fixo em `app/vagas/templates.py`.

   ```
   🔎 3 vagas novas
   1. Estágio em Desenvolvimento — Empresa X (Brasília, híbrido)
      estágio · prazo 20/10 · gupy.io/…
   …
   Responda "não tenho interesse na 2" para esconder uma vaga.
   ```

   - Sai pelo mesmo `deliver` dos lembretes, com reserva em `sent_reminders` (`kind='vagas'`, `ref_id` = a rodada), para não repetir.
   - Isso exige acrescentar `vagas` ao CHECK de `sent_reminders.kind` (na mesma migração).
   - Depois de enviar, marca `sent_at` nas vagas.

7. **Ferramentas de conversa** (grupo `consulta_gasto` não serve; o grupo novo é `vagas` no classificador):
   - `listar_vagas()` traz as dos últimos 14 dias não dispensadas, numeradas como na mensagem;
   - `dispensar_vaga(numero | url)` preenche `dismissed_at`.
   - O classificador ganha a intenção `vagas` ("quais vagas?", "não tenho interesse na 2"). A prova ganha 3 casos.
   - **No Jarvis:** as ferramentas vêm pelo MCP, como as outras do núcleo.

8. **Painel:** o `painel` traz `vagas` (até 8). O Jarvis desenha um cartão "Vagas" com título, organização, prazo e link (abre no navegador, como o cartão de fontes). No HUD, ele entra na coluna da direita, abaixo de Projetos.

## Risks / Trade-offs

- **[A busca acha página de listagem, não a vaga]** → a verificação aceita uma URL que começa com a da listagem, e o resumo diz o que é. Dá para dispensar o que não serve.
- **[Vaga inventada]** → a regra do link verificado. Os testes cobrem URL fora dos resultados.
- **[Repetição com URLs diferentes da mesma vaga]** (Gupy com parâmetros, por exemplo) → a normalização. Se ainda repetir, a próxima versão compara título e organização.
- **[Custo fora do previsto]** → `max_uses`, `agent_runs` com o custo e `VAGAS_ATIVO`.
- **[Mensagem longa no WhatsApp]** → no máximo 8 vagas e uma linha de detalhe cada.
- **[Classificador confunde "vagas" com outra intenção]** → casos novos na prova antes do aceite.

## Open Questions

- Nenhuma. O perfil inicial vai em `config/vagas.yaml`, e o Kaio ajusta depois das primeiras rodadas.
