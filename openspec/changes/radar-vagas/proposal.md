## Why

O Kaio quer achar oportunidades sem procurar todo dia: estágio, bolsa de pesquisa, monitoria e vaga de dev júnior (pedido de 13/10/2026). Ele cursa Licenciatura em Computação na UnB à noite, então só serve o que cabe durante o dia, em Brasília ou remoto. Com a busca na internet que o Jarvis ganhou (branch `feat/jarvis-internet`), o núcleo pode fazer essa procura sozinho e mandar só o que é novo.

## What Changes

- **Radar de vagas a cada 3 dias**, rodado pelo núcleo: uma checagem por hora, das 08:00 às 22:00, roda a pesquisa quando a última rodada bem-sucedida tiver sido há 72 h ou mais. Assim, o Mac dormindo às 08:00 não atrasa um dia, e uma rodada que falha tenta de novo (no máximo 2 vezes por dia).
  - pesquisa na internet com o perfil do Kaio:
    - **tipos:** estágio, bolsa de pesquisa (PIBIC, PIBITI, iniciação científica, editais da UnB, do CNPq e da FAP-DF), monitoria e ensino, dev júnior e trainee;
    - **local:** Brasília (presencial ou híbrido) ou 100% remoto;
    - **áreas que sobem na ordem:** IA e dados, desenvolvimento web, direito + tecnologia;
  - **só entra vaga cujo link veio da própria busca.** Vaga sem link verificável é descartada, para o modelo não inventar oportunidade;
  - **vaga já mostrada não volta** (registro no banco pela URL normalizada);
  - o perfil fica num arquivo editável (`config/vagas.yaml`, fora do git, porque o repositório é público), sem mexer no código. Só um `config/vagas.example.yaml` genérico vai para o git.
- **Entrega:**
  - uma mensagem no **WhatsApp** com até 8 vagas novas (título, onde, tipo, prazo e link), em texto fixo montado pelo código;
  - rodada sem nada novo não manda mensagem;
  - um cartão **"Vagas"** no painel do Jarvis com as dos últimos 14 dias.
- **Consulta por conversa:** "quais vagas novas?" (WhatsApp ou Jarvis) lista as recentes. Cada vaga tem um código curto e estável (V12), usado na mensagem, na lista e no painel: "não tenho interesse na V12" esconde a vaga (o título também serve).
- **Custo controlado:**
  - no máximo 12 buscas por rodada (~US$ 0,12, mais tokens);
  - o custo vai para `agent_runs` (canal `vagas`);
  - `VAGAS_ATIVO=false` desliga.

## Non-goals

- Candidatar-se ou preencher formulário. O radar só encontra e avisa.
- Entrar em sites com login (LinkedIn, por exemplo). Vagas de lá só aparecem pelo que a busca mostra.
- Alertas em tempo real. O intervalo é de 3 dias, e a vaga pode chegar com até 3 dias de atraso.
- Montar currículo ou carta de apresentação.

## Capabilities

### New Capabilities
- `vagas`: radar periódico, perfil, verificação dos links, histórico sem repetição, entrega, consulta e "não tenho interesse".

### Modified Capabilities
- `mcp`: a ferramenta `painel` passa a trazer as vagas recentes.

## Impact

- **Núcleo:**
  - `app/vagas/` (busca, verificação e montagem do texto);
  - job no `app/scheduler.py`;
  - ferramentas `listar_vagas` e `dispensar_vaga` no grupo de consultas;
  - campo `vagas` no `painel`.
- **Banco:** tabela `job_leads` (migração Alembic).
- **Configuração:** `config/vagas.yaml` (perfil, no `.gitignore`), `config/vagas.example.yaml` e `VAGAS_ATIVO`, `VAGAS_MODELO` e `VAGAS_MAX_BUSCAS` no `.env`.
- **Jarvis:** cartão "Vagas" no painel.
- **Depende de** `feat/jarvis-internet` (ferramentas de servidor no adaptador da Anthropic).
- **Custo:** ~US$ 0,10 a 0,15 por rodada, ~US$ 1,50 por mês.
