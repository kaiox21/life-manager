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
   - O prompt traz o perfil do `config/vagas.yaml`, a data de hoje e as consultas sugeridas, e manda terminar chamando `registrar_vagas` uma vez.
   - **Perfil fora do git:** o repositório é público (o `casos.yaml` já usa cartões fictícios por isso). `config/vagas.yaml` entra no `.gitignore`; só `config/vagas.example.yaml`, genérico, é versionado. Sem o arquivo, o radar não roda e registra o motivo no log.
   - **Horário:** só descarta vaga que informa horário noturno ou em conflito com o curso; sem horário informado, passa (a maioria não informa). Exemplos de consulta: "estágio desenvolvimento Brasília", "estágio remoto programação", "PIBIC UnB edital", "bolsa iniciação científica computação", "desenvolvedor júnior remoto Python", "monitoria computação UnB".
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

4. **Tabela `job_leads`:** id, `codigo` (único, "V" + sequência: V1, V2…, estável para mensagem, lista, painel e dispensa), `url` (única), título, organização, tipo, local, prazo (date, nulo), resumo, pontuação, `found_at`, `sent_at` (nulo), `dismissed_at` (nulo) e `run_id` (a rodada em `agent_runs`).
   - **Pontuação** (no código, sem LLM): +3 se a área é IA/dados, +2 web, +2 direito+tecnologia (por palavras no título e no resumo); +1 se o prazo é em até 7 dias.
   - A ordem da mensagem é pontuação decrescente e prazo crescente.

5. **Quando rodar** (corrigido na análise crítica de 13/10/2026):
   - checagem a cada hora (APScheduler `interval`), só entre 08:00 e 22:00, e na subida do app;
   - roda se a última rodada **sem erro** (a última linha de `agent_runs` com canal `vagas` e `error` nulo) tiver sido há 72 horas ou mais, e se hoje ainda houve menos de 2 tentativas;
   - um job diário às 08:00 não bastava: o APScheduler desiste de um job atrasado mais de 1 h (`misfire_grace_time`), e com o Mac dormindo às 08:00 a rodada ficaria para o dia seguinte;
   - não há estado novo: o próprio `agent_runs` diz quando foi a última rodada e quantas tentativas houve hoje.

6. **Entrega pelo WhatsApp:** texto fixo em `app/vagas/templates.py`.

   ```
   🔎 3 vagas novas
   V12 · Estágio em Desenvolvimento — Empresa X (Brasília, híbrido)
      estágio · prazo 20/10 · gupy.io/…
   …
   Responda "não tenho interesse na V12" para esconder uma vaga.
   ```

   - Sai pelo mesmo `deliver` dos lembretes, com reserva em `sent_reminders` (`kind='vagas'`, `ref_id` = a rodada), para não repetir.
   - Isso exige acrescentar `vagas` ao CHECK de `sent_reminders.kind` (na mesma migração).
   - Depois de enviar, marca `sent_at` nas vagas.

7. **Ferramentas de conversa** (grupo `consulta_gasto` não serve; o grupo novo é `vagas` no classificador):
   - `listar_vagas()` traz as dos últimos 14 dias não dispensadas, com o mesmo código da mensagem (V12). Antes era a numeração da rodada, mas o "2" da mensagem não seria o "2" da lista de 14 dias, que junta várias rodadas;
   - `dispensar_vaga(codigo | titulo)` preenche `dismissed_at`. Se o título bate com mais de uma vaga, volta as opções sem dispensar.
   - O classificador ganha a intenção `vagas` ("quais vagas?", "não tenho interesse na 2"). A prova ganha 3 casos.
   - **No Jarvis:** as ferramentas vêm pelo MCP, como as outras do núcleo.

8. **Painel:** o `painel` traz `vagas` (até 8). O Jarvis desenha um cartão "Vagas" com título, organização, prazo e link (abre no navegador, como o cartão de fontes). No HUD, ele entra na coluna da direita, abaixo de Projetos.

## Risks / Trade-offs

- **[A busca acha página de listagem, não a vaga]** → só entram links que apareceram nos resultados. Uma vaga que existe só dentro de uma listagem (as vagas de uma empresa no Gupy, por exemplo) chega com o link da listagem, e o resumo diz o que é. É a troca escolhida: algumas vagas menos diretas pela garantia de não inventar. Dá para dispensar o que não serve.
- **[Vaga inventada]** → a regra do link verificado. Os testes cobrem URL fora dos resultados.
- **[Repetição com URLs diferentes da mesma vaga]** (Gupy com parâmetros, por exemplo) → a normalização. Se ainda repetir, a próxima versão compara título e organização.
- **[Custo fora do previsto]** → `max_uses`, `agent_runs` com o custo e `VAGAS_ATIVO`.
- **[Mensagem longa no WhatsApp]** → no máximo 8 vagas e uma linha de detalhe cada.
- **[Classificador confunde "vagas" com outra intenção]** → casos novos na prova antes do aceite.

## Open Questions

- Nenhuma. O perfil inicial vai em `config/vagas.yaml`, e o Kaio ajusta depois das primeiras rodadas.

## Registro da implementação (13/10/2026)

- **Prova** depois da intenção `vagas` no classificador: 56/56 no classificador e 55/56 no agente (a mesma falha conhecida, `a10`), US$ 0,023. Os 3 casos de vagas não entraram: `casos.yaml` é somente leitura.
- **1ª rodada real:** 9 buscas, 85 resultados, 7 vagas novas e nenhuma descartada, US$ 0,093. Qualidade:
  - 4 páginas de vaga do Programathor, duas de IA/Python remotas (as melhores);
  - 3 páginas de **resultado de busca** do Indeed e do Infojobs, não vagas;
  - nenhuma bolsa ou monitoria;
  - números baixos no Programathor (5087, 9224) sugerem anúncio antigo.
- **Entrega que falhou esperava 72 h:** o WhatsApp recusou (Evolution 428 "Connection Closed"), e como a rodada deu certo a próxima só sairia em 3 dias. Agora toda checagem manda as vagas registradas e não enviadas (`deliver_pending`).
- **WhatsApp morto com estado "open":** a Evolution dizia `open`, mas todo envio voltava 428. Provável queda da conexão do WhatsApp Web com o Mac dormindo; o monitor de queda confia no estado e não percebeu. `docker compose restart evolution-api` reconectou sem QR. Isso fica fora deste change e foi anotado para o canal do WhatsApp.
