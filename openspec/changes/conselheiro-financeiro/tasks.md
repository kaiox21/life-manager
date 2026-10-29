## 1. Preparação

- [ ] 1.1 Pedir ao Kaio uma fatura em PDF de cada cartão (Nubank e Inter Crédito) para o aceite. As faturas ficam fora do git, em `data/faturas/`, que entra no `.gitignore`. Conferir à mão que o `pypdf` (modo `layout`) extrai os itens e os totais de cada uma.
- [x] 1.2 Criar o branch `feat/conselheiro-financeiro` a partir de `main`, adicionar o `pypdf` ao `pyproject.toml` e rodar `uv sync`.
- [x] 1.3 Migração Alembic:
  - tabelas `statement_imports` e `budget_items`;
  - checks de `expenses` (`source` com `fatura`, e valor negativo só com `source='fatura'`);
  - modelos SQLAlchemy;
  - `CONSELHO_FOLGA_PCT` em `app/config.py` e no `.env.example`.

## 2. Leitura da fatura (núcleo)

- [ ] 2.1 (29/10: código e testes prontos, inclusive PDF com legenda em `documentWithCaptionMessage`; falta o envio real) Ler `documentMessage` com PDF no canal: `mimetype`, legenda e tamanho até 10 MB, com o mesmo download de reserva das outras mídias. Conferir o formato com um envio real. Testes do parsing do webhook (PDF, `.xlsx` ignorado, acima de 10 MB).
- [x] 2.2 `app/statements/extract.py` (extração com `pypdf`; recusa PDF com senha ou escaneado) e `mask.py` (número de cartão). Testes com PDFs fictícios gerados no teste.
- [x] 2.3 `app/domain/statement.py`, todo puro:
  - `parse_brl`;
  - ano da data do item;
  - conferência da soma;
  - casamento;
  - parcelas k a N;
  - resumo em texto fixo.
  - Testes: milhar, sinal à direita, estorno, pagamento, soma divergente, parcela já lançada, virada de ano, dois candidatos, "fora da fatura".
- [x] 2.4 `app/statements/service.py`:
  - transcrição forçada `registrar_fatura` (Pydantic, validação e escalada, divisão por página);
  - resolução do cartão (só crédito; `opcoes` quando ambíguo);
  - reimportação por sha256 e por ciclo;
  - pendência `gravar_fatura`;
  - linha em `agent_runs` sem o conteúdo.
  - Testes com LLM falso.
- [x] 2.5 Executor `gravar_fatura` no `confirmar_pendente`:
  - transação única;
  - nova conferência dos gastos casados;
  - `statement_imports`;
  - eco.
  - Testes: sim, não, expirada, reimportação sem pendência.
- [x] 2.6 Ferramenta MCP `importar_fatura(pdf_base64, cartao?)` com o mesmo serviço e `agent_runs` com `channel='desktop'`. Teste pelo cliente MCP de teste.

## 3. Conselho (núcleo)

- [x] 3.1 `gerenciar_renda` e `gerenciar_conta_fixa`: criar ou atualizar pelo nome, `remover` com exclusão lógica e eco com os totais mensais. Testes.
- [x] 3.2 `app/domain/budget.py`:
  - projeção por mês, à vista e no crédito pela regra de `billing.py`;
  - parcelas comprometidas;
  - média avulsa sem as contas fixas, com menos de 3 meses de histórico;
  - veredito com folga configurável e mês decisivo.
  - Testes com `clock` fixo, incluindo o cenário do fone em 4x e o mês negativo.
- [x] 3.3 `avaliar_compra`: resolução do meio, erro sem renda e números em centavos mais o texto formatado. Testes.
- [x] 3.4 Intenção `conselho` no classificador (exemplos e "comprei" contra "posso comprar"), grupo `conselho`, regras do prompt do grupo e escalada quando a resposta vem sem ferramenta. Testes do roteamento.

## 4. Jarvis

- [x] 4.1 Ação local `importar_fatura(arquivo?, cartao?)`:
  - caminho dentro de `~`, `.pdf` e até 10 MB;
  - sem `arquivo`, o PDF mais novo de Downloads em 7 dias;
  - chamada MCP.
  - Testes: fora de `~`, não PDF, nada em Downloads.
- [x] 4.2 Cartões no Jarvis:
  - resumo da fatura com a confirmação que já existe;
  - cartão do conselho com a tabela por mês e o veredito;
  - em voz, duas frases.
  - Teste do cartão no cérebro.

## 5. Documentação

- [x] 5.1 `SPEC.md`:
  - "Dentro" e "Fora (por ora)";
  - a linha "Entrada de gastos";
  - nova decisão "Conselheiro financeiro" (transcrição pelo modelo e soma no código, casamento, veredito fixo, privacidade e custo);
  - mapa das capacidades com `importacao-fatura` e `conselho-financeiro`.
- [x] 5.2 README: uma linha na lista de capacidades.

## 6. Verificação

- [x] 6.1 `uv run pytest`, `uv run ruff check . && uv run ruff format .`, `uv run alembic upgrade head` e `openspec validate --all --strict`.
- [x] 6.2 (29/10: autorizado pelo Kaio; 10 casos no `casos.yaml`; prova 65/66, só a falha conhecida `a10`) Escrever os casos novos da prova em `tests/eval/casos_conselho.rascunho.yaml` e **pedir a autorização do Kaio** para levá-los ao `casos.yaml`. Depois, rodar a prova (`uv run pytest -m eval`; avisar o custo antes, que deve ficar em poucos centavos de dólar). O mínimo é 90%.

## 7. Aceite e arquivo

- [ ] 7.1 Aceite real com o Kaio:
  - a fatura do Nubank pelo WhatsApp e a do Inter pelo Jarvis, com a soma conferindo, os casamentos certos e as parcelas futuras;
  - reimportar uma delas sem duplicar;
  - cadastrar renda e contas fixas;
  - perguntar "posso comprar…?" em texto e em voz;
  - conferir o custo em `agent_runs`.
- [ ] 7.2 Atualizar os deltas se o aceite mudar algo, refazer o delta de `ferramentas-locais` se outra change mexeu em "Ações permitidas" antes, e rodar `/opsx:archive`.
