## Why

O Kaio gosta de notícias e quer que o Jarvis mande todo dia as mais relevantes (pedido de 13/10/2026), sem ele precisar abrir vários sites. O radar de vagas deixou pronta a peça difícil: busca na internet pelo núcleo com link verificado, agendamento que aguenta o Mac dormindo, entrega no WhatsApp e cartão no painel.

## What Changes

- **Boletim diário às 07:30**, montado pelo núcleo:
  - **5 manchetes gerais** dos temas do Kaio: tecnologia e IA, direito e Judiciário, Brasil e política, mundo;
  - **seção de futebol com até 3 notícias**, com prioridade para **Flamengo e Barcelona** (resultado, próximo jogo, contratações). Sem notícia deles, entra o principal do futebol brasileiro;
  - cada notícia vem com título, uma linha de resumo, fonte e link, e o mesmo fato aparece uma vez só, mesmo vindo de vários jornais;
  - **só fontes grandes:** a busca fica restrita a uma lista de domínios (G1, Folha, Estadão, UOL, Valor, CNN Brasil, Agência Brasil, BBC, Reuters, The Verge, ConJur, Migalhas, JOTA, ge, ESPN, Mundo Deportivo, Sport e outros), editável;
  - **só o que é das últimas ~24 h**, e nada que já tenha saído num boletim dos 3 dias anteriores.
- **Nada inventado:** como nas vagas, só entra notícia cujo link veio dos resultados da própria busca.
- **Entrega:**
  - uma mensagem no **WhatsApp**, com texto fixo montado pelo código;
  - o cartão **"Notícias"** no painel do Jarvis;
  - as **3 primeiras manchetes faladas** no "Hey Jarvis" da manhã (só os títulos, depois do clima e da agenda).
- **Agenda tolerante:** checagem a cada 30 min, das 07:30 às 22:00. Roda se o boletim de hoje ainda não saiu, com até 2 tentativas no dia, e se o Mac estava dormindo às 07:30, sai quando ele acordar.
- **Perfil editável** em `config/noticias.yaml` (temas, times, fontes), fora do git como o das vagas. `NOTICIAS_ATIVO=false` desliga.

## Non-goals

- Conversar sobre as notícias pelo WhatsApp ("me fala mais da 2"). No Jarvis isso já funciona com a internet; no WhatsApp fica para depois.
- Notícias em tempo real ou alerta de "urgente".
- Opinião, análise ou resumo longo. É manchete com uma linha.
- Placar ao vivo.

## Capabilities

### New Capabilities
- `noticias`: boletim diário com perfil, fontes restritas, link verificado, sem repetição, seção de futebol e entrega.

### Modified Capabilities
- `mcp`: a ferramenta `painel` passa a trazer o boletim do dia.

## Impact

- **Núcleo:**
  - `app/noticias/` (busca, verificação, texto da mensagem e agenda);
  - job no `app/scheduler.py`;
  - campo `noticias` no `painel`.
- **Banco:** tabela `news_items` (migração Alembic) e `noticias` no CHECK de `sent_reminders.kind`.
- **Configuração:** `config/noticias.yaml` (fora do git) e `config/noticias.example.yaml`; `NOTICIAS_ATIVO`, `NOTICIAS_MODELO` e `NOTICIAS_MAX_BUSCAS` no `.env`.
- **Jarvis:** cartão "Notícias" no painel e manchetes no resumo do dia (`jarvis/briefing.py`).
- **Reaproveita do radar de vagas:** normalização e verificação de links e a entrega idempotente. Depende de `feat/radar-vagas`.
- **Custo:** ~8 buscas por dia (~US$ 0,08), mais tokens, ou seja, **~US$ 2,50 por mês**.
