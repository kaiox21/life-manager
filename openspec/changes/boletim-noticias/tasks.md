## 1. Base

- [x] 1.1 `app/web/links.py` com `normalize_url`, `search_urls` (também `page_age`) e `verified`; o radar passa a importar daí (testes do radar continuam passando)
- [x] 1.2 Migração `news_items` e `noticias` no CHECK de `sent_reminders.kind`; modelo; `config/noticias.yaml` (fora do git, com a tabela domínio → nome da fonte) e `.example`; `NOTICIAS_*` em `app/config.py` e `.env.example`

## 2. Boletim

- [x] 2.1 `app/noticias/boletim.py`: conversa com `web_search` (allowed_domains) + `registrar_noticias` (título e resumo em português); fonte pelo domínio; filtros (link, domínio, 36 h, URL, título Jaccard ≥ 0,6 com o boletim e os 3 dias anteriores); corte 5 + 3; `agent_runs` canal `noticias`; testes com LLM falso
- [x] 2.2 Texto fixo da mensagem, `deliver_pending` e checagem a cada 30 min (07:30–22:00, uma rodada sem erro por dia, até 2 tentativas); job no scheduler; testes com relógio fixo

## 3. Jarvis

- [x] 3.1 `noticias` no `painel` (edição mais recente com a data) e cartão "Notícias" ("de hoje"/"de ontem, DD/MM", futebol em subgrupo, links no navegador); testes
- [x] 3.2 `briefing.compose` com as 3 primeiras manchetes (da edição mais recente, dizendo "de ontem" quando não é a de hoje; ~70 caracteres cada) depois da agenda; testes

## 4. Fechamento

- [x] 4.1 `uv run pytest`, ruff, `openspec validate --all --strict`; reconstruir o núcleo e instalar o Jarvis
- [ ] 4.2 Primeiro boletim real com o Kaio (custo anotado), ajuste de temas e fontes
- [ ] 4.3 `SPEC.md` e `/opsx:archive`, **depois** do arquivamento do `radar-vagas` (mesmo requisito do painel)
