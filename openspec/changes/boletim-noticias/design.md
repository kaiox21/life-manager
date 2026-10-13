## Context

- **O radar de vagas** (`app/vagas/`, change `radar-vagas`) já tem:
  - busca pela Anthropic com `server_tool`;
  - `normalize_url`, `search_urls` e `verified` (link tem que ter vindo da busca);
  - checagem periódica com até 2 tentativas por dia, contada por `agent_runs`;
  - `deliver` idempotente pelo `sent_reminders`;
  - campo no `painel` e cartão no Jarvis.
- **O resumo do "Hey Jarvis"** (`jarvis/briefing.py`) é texto fixo montado no cérebro com dados do `painel`.
- **A busca da Anthropic aceita `allowed_domains`** (documentação conferida em 13/10/2026: lista de domínios sem esquema; não dá para usar `allowed_domains` e `blocked_domains` juntos). Os resultados trazem `url`, `title` e `page_age` (texto, por exemplo "April 30, 2025"; às vezes ausente).
- **Conferido na 1ª rodada real (13/10/2026):** se um domínio de `allowed_domains` bloqueia o robô da Anthropic, a API recusa o pedido inteiro com 400 ("The following domains are not accessible to our user agent: [...]"), antes de buscar e sem custo. Bloqueados nesse dia: BBC (inclusive /portuguese), Reuters, AP, NYT, Guardian, El País, DW, Wired, UOL, Estadão, The Verge, Ars Technica, Marca, AS, Mundo Deportivo e Sport. A lista inicial do perfil foi trocada por 31 fontes aceitas (conferidas com um pedido de `max_tokens=1`).

## Goals / Non-Goals

**Goals:** um boletim por dia, curto, de fontes grandes, sem inventar e sem repetir, com futebol à parte.

**Non-Goals:** ver a proposta.

## Decisions

1. **Peças comuns.** `normalize_url`, `search_urls` e `verified` saem de `app/vagas/radar.py` para `app/web/links.py`, e o radar passa a importá-las dali. Assim as duas funções usam a mesma verificação.

2. **Uma conversa por boletim:**
   - `web_search` com `allowed_domains` = as fontes do perfil, `max_uses` = `NOTICIAS_MAX_BUSCAS` (8) e local BR;
   - `registrar_noticias(gerais: [...até 8], futebol: [...até 5])`, cada item com titulo, resumo (≤ 200), fonte, url, publicada (opcional) e tema (`tecnologia`, `direito`, `brasil`, `mundo`, `futebol`);
   - o prompt pede o que saiu nas últimas 24 h, um fato por notícia (agrupando fontes), Flamengo e Barcelona primeiro no futebol, e **título e resumo em português** (tradução quando a fonte é estrangeira; sem isso a deduplicação por título não funciona entre idiomas);
   - **a fonte sai do domínio** do link, por uma tabela `fontes` no perfil (domínio ou domínio/caminho → nome: `g1.globo.com` → G1, `ge.globo.com` → ge, `bbc.com` → BBC…). O campo `fonte` do modelo é ignorado; domínio sem nome na tabela usa o próprio domínio;
   - o prompt pede 6 a 8 gerais (pelo menos uma por tema) e 3 a 5 de futebol: na 1ª rodada real o modelo registrou só 3 com o pedido de "até 8";
   - o código corta para 5 gerais e 3 de futebol depois de verificar, para sobrar margem para os descartes;
   - **fonte que passa a bloquear o robô:** a rodada lê os domínios do erro 400, tenta de novo uma vez sem eles e avisa no log para tirá-los do perfil. Sem isso, um site sozinho derrubaria o boletim do dia.

3. **Filtros no código, em ordem:**
   1. link fora da busca;
   2. domínio fora da lista;
   - **título de outra página** (desde a 1ª rodada real, 13/10/2026: o modelo pôs "Marco da IA segue sem data" no link de uma coluna sobre sertanejos): o título do modelo precisa ter ao menos uma palavra (pelo começo, 4 letras) em comum com o título do resultado ou com o endereço da página. Nomes próprios batem mesmo em fonte estrangeira;
   3. velha, se a data de publicação (do modelo ou o `page_age` do resultado) passa de 36 h;
   4. repetida por URL (`news_items.url` única);
   5. repetida por título: Jaccard ≥ 0,6 entre os conjuntos de palavras normalizadas (sem acento e sem palavras vazias), comparando com as notícias do boletim e com as enviadas nos 3 dias anteriores.
   - `page_age` é lido por um parser tolerante (data em inglês ou em português, "X hours/days ago"); sem data, a notícia não é descartada por idade.

4. **Tabela `news_items`:** id, `url` (única), titulo, resumo, fonte, tema, `futebol` (bool), posicao, `run_id`, `edition` (date do boletim, no fuso de Brasília), `found_at` e `sent_at`.
   - O boletim do dia é `edition = hoje`.

5. **Agenda:** checagem a cada 30 min, das 07:30 às 22:00, e na subida.
   - **Roda se:** não houve rodada sem erro hoje (canal `noticias` em `agent_runs`) e houve menos de 2 tentativas hoje.
   - **Entrega:** as notícias de hoje ainda não enviadas saem em toda checagem, como no radar (`deliver_pending`).

6. **Mensagem (texto fixo, `app/noticias/templates.py`):**

   ```
   📰 Notícias de segunda, 13/10
   1. Título — resumo de uma linha
      Fonte · g1.globo.com/…
   …
   ⚽ Futebol
   • Flamengo vence o Palmeiras por 2 a 1 — …
     ge · ge.globo.com/…
   ```

   - O WhatsApp tem limite de tamanho, e 8 itens com uma linha cada cabem com folga.

7. **Jarvis:**
   - o `painel` traz `noticias` = a edição mais recente (`{"data": "AAAA-MM-DD", "itens": [...]}`); de madrugada, a de ontem. O cartão mostra "Notícias de hoje" ou "Notícias de ontem, 13/10";
   - o cartão "Notícias" fica na coluna da direita, com as de futebol num subgrupo, e os links abrem no navegador;
   - `briefing.compose` recebe as manchetes **só se a edição é de hoje** e, depois da agenda e das faturas, fala "Nas notícias: …" com os títulos das 3 primeiras gerais, cada um cortado em ~70 caracteres numa fronteira de palavra. O aceite mede o resumo inteiro (teto de ~30 s).

8. **Perfil (`config/noticias.yaml`, fora do git; `config/noticias.example.yaml` versionado):** temas (com descrição para o modelo), times (Flamengo e Barcelona) e fontes (domínios). O perfil inicial vem das respostas do Kaio.

9. **Ordem de arquivamento:** o `radar-vagas` e este change alteram o mesmo requisito ("Dados do painel"), e este delta parte do texto do radar. O `radar-vagas` tem que ser arquivado antes deste; se fosse depois, o arquivamento do boletim apagaria as vagas da spec.

## Risks / Trade-offs

- **[Lista de domínios corta fonte boa]** → a lista é editável. Começa larga, com ~25 domínios.
- **[Repetição com títulos diferentes do mesmo fato]** → o modelo agrupa e o Jaccard pega títulos parecidos. Pode escapar um ou outro; o custo é uma linha a mais.
- **[Notícia velha que a busca acha]** → instrução de 24 h, `page_age` quando houver e o histórico de 3 dias.
- **[Futebol sem notícia de Flamengo/Barcelona no dia]** → entra o principal do futebol brasileiro, ou a seção sai vazia e não aparece.
- **[Custo]** → 8 buscas por dia (US$ 0,08) mais tokens. O `agent_runs` mostra o custo, e `NOTICIAS_ATIVO=false` desliga.

## Open Questions

- Nenhuma.
