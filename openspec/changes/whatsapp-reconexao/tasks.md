## 1. Implementação

- [x] 1.1 `EvolutionClient`: `restart()`, detecção de conexão morta (428 / "Connection Closed"), espera do `open` e nova tentativa única, com intervalo mínimo de 5 min entre reinícios; testes com `httpx.MockTransport`
- [x] 1.2 `ConnectionMonitor.observe_send(ok)` ligado ao cliente; alerta após 2 min de falhas mesmo com o estado `open`; testes

## 2. Fechamento

- [x] 2.1 `uv run pytest`, `uv run ruff check . && uv run ruff format .`, `openspec validate --all --strict`; reconstruir o `app`
- [ ] 2.2 `/opsx:archive` depois de uma semana sem queda silenciosa
