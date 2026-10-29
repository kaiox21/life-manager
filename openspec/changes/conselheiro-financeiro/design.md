## Context

- Os gastos já têm tudo de que a importação precisa:
  - `expenses` guarda centavos, `statement_month`, as parcelas (`installment_no`, `installment_total`, `purchase_group`), `source` e `deleted_at`;
  - a regra da fatura está em `app/domain/billing.py`;
  - `lancar_gasto` usa pendências (`pending_actions`, que expiram em 30 min) e a resolução de meio (`app/agent/tools/resolve.py`);
  - a foto de recibo já percorre o caminho "mídia → modelo → pendência → sim".
- O canal (`app/channel/evolution.py`) lê só `audioMessage` e `imageMessage`. Documento é ignorado.
- O Jarvis só fala com o núcleo pelo MCP. O núcleo roda no Docker, então ele não enxerga `~/Downloads`: quem lê o arquivo é o Jarvis, que manda os bytes ao núcleo.
- `expenses` tem os checks `amount_cents > 0` e `source in ('texto','audio','foto')`.
- Meios reais (07/10/2026): Nubank (crédito, fecha no último dia, vence dia 8), Inter Crédito (fecha dia 12, vence dia 18) e Inter Débito.
- **Ainda não temos nenhum PDF de fatura** do Kaio para testar. A tarefa 1.1 pede um de cada cartão. Os testes usam textos fictícios, porque o repositório é público.

## Goals / Non-Goals

**Goals:**
- uma fatura vira gastos corretos com dois toques ("manda o PDF" e "sim");
- o código confere a soma;
- nenhuma duplicata, nem na reimportação;
- o conselho sai de números calculados, com o veredito decidido no código;
- o custo é de centavos por fatura.

**Non-Goals:** ver a proposta.

## Decisions

1. **Extração com `pypdf`** (conferido em 29/10/2026: pypdf 6.21.4 tem `PdfReader.is_encrypted` e `decrypt`, e `PageObject.extract_text(extraction_mode="layout")` preserva as colunas):
   - é Python puro, sem binário no Docker, e o `pdfplumber` não traz ganho para texto corrido;
   - usa `layout` porque fatura é tabela, e `plain` mistura as colunas;
   - um PDF criptografado é recusado, mesmo que `decrypt("")` funcione, e a mensagem pede o PDF sem senha. Guardar a senha (normalmente o CPF) no `.env` foi rejeitado: seria mais um segredo por um ganho pequeno;
   - um PDF com menos de 200 caracteres de texto é tratado como escaneado.
   - *Alternativa rejeitada:* um leitor fixo por banco, que custa zero mas quebra a cada mudança de layout (decisão do Kaio).

2. **Mascaramento** (`app/statements/mask.py`):
   - o regex `(?<!\d)(?:\d[ .-]?){12,18}\d(?!\d)` encontra a sequência, e o código troca por `****` mais os 4 últimos dígitos;
   - roda antes de qualquer chamada ao modelo e antes de qualquer log.

3. **Transcrição numa chamada forçada** (`registrar_fatura`, argumentos em Pydantic com `extra=forbid`):
   - o modelo é o `MODEL_PRIMARY`; a validação e a escalada são as do agente (argumento inválido volta uma vez; no segundo fracasso, `MODEL_ESCALATION`);
   - campos: `emissor`, `final_cartao`, `vencimento` (AAAA-MM-DD), `total_impresso`, `saldo_anterior`, `pagamentos` e `itens[]` (`data`, `descricao`, `valor` como texto impresso, `parcela` "k/N" ou nulo, `tipo`, `categoria`);
   - **o valor fica como texto** de propósito: quem converte para centavos é o `parse_brl` do código, que aceita "R$ 1.234,56", "1234,56", "-45,90" e "45,90-". Assim o modelo não converte nem soma.
   - A data do item pode vir sem ano ("16 OUT", que o modelo escreve "16/10"). O ano é o do vencimento; se a data cairia depois do vencimento, é o ano anterior (parcela de compra feita no ano passado).
   - Linhas de valor zero ("IOF 0,00") são descartadas na conversão: não pesam no total e o check `amount_cents <> 0` as recusaria (achado nos testes em 29/10/2026).
   - Uma fatura longa (mais de ~60 mil caracteres) é dividida por página em chamadas separadas, e os itens se juntam no código. Os totais vêm da primeira página que os trouxer.

4. **Conferência da soma** (`app/domain/statement.py`, função pura):
   - a fórmula é `saldo_anterior − pagamentos + Σcompras + Σencargos − Σestornos == total_impresso`, em centavos e sem tolerância;
   - o resultado é `diferenca_cents`. Quando ela não é zero, o resumo leva o aviso, mas o "sim" ainda vale, porque o Kaio pode conferir no app;
   - o sinal dos estornos e pagamentos vem do `tipo`, não do sinal impresso, porque cada banco imprime de um jeito.

5. **Casamento** (função pura, testada com casos fictícios):
   - candidatos são os gastos ativos do cartão com `installment_no/total` iguais, `amount_cents` igual ao da parcela (até 1 centavo de diferença em parcelado: `lancar_gasto` põe a sobra do rateio na 1ª parcela, o banco pode pôr em outra) e `|spent_on − data| ≤ 3 dias`;
   - para uma parcela k > 1 lançada à mão com a data da compra original, a data comparada é a de compra impressa;
   - o desempate é a menor distância em dias e depois a maior semelhança de descrição (`difflib.SequenceMatcher` sobre o texto normalizado sem acento);
   - cada gasto casa com um item no máximo, num casamento guloso em ordem de data;
   - "fora da fatura" são os gastos ativos do cartão com `statement_month` igual ao ciclo que não casaram.

6. **Parcelas futuras:** "k/N" gera as parcelas k a N.
   - O valor de cada parcela é o impresso, sem rateio de sobra, porque o banco já dividiu.
   - Antes de gravar as parcelas futuras, o código procura um `purchase_group` já existente que casou na parcela k e só completa as que faltam.
   - As parcelas anteriores a k não são criadas: ficaram em faturas passadas.

7. **Estorno negativo:**
   - a migração troca os checks para `amount_cents <> 0 AND (amount_cents > 0 OR source = 'fatura')` e `source in ('texto','audio','foto','fatura')`;
   - `lancar_gasto` continua exigindo `gt=0`;
   - as somas em SQL (`total_fatura`, `resumo_gastos`, `painel`) já fazem `SUM` e passam a descontar o estorno sem mudar nada.

8. **Pendência e gravação:**
   - a `PendingAction` tem `tool_name='gravar_fatura'` e os `args` com o cartão, o ciclo, a impressão digital (sha256 do PDF), os itens novos já em centavos e os ids casados;
   - `confirmar_pendente` chama o executor numa transação única;
   - antes de gravar, o executor confere de novo que os gastos casados continuam ativos. Se algum foi desfeito no meio-tempo, a gravação segue e o eco avisa.
   - O resumo é texto fixo montado no código, com a lista dos novos limitada a 15 linhas e "+N itens".
   - `desfazer_ultimo` depois de importar desfaz só a compra mais recente, como hoje. Desfazer a importação inteira fica fora: dá para recusar no "não" antes.

9. **Tabela `statement_imports`:**
   - colunas `id`, `payment_method_id`, `statement_month`, `printed_total_cents`, `file_sha256`, `items_count`, `created_cents`, `created_at`;
   - é gravada no "sim";
   - a reimportação passa pelo pipeline inteiro (a transcrição custa ~US$ 0,003): assim, um gasto desfeito depois da importação volta a aparecer como novo. O sha256 ou o mesmo cartão e ciclo só servem para o resumo dizer "já importada em <data>"; sem nada novo, não há pendência.

10. **Entrada pelo WhatsApp:**
    - o `_extract_media` passa a aceitar `documentMessage` com `mimetype` `application/pdf`, e a legenda vem de `documentMessage.caption`;
    - o tamanho é limitado a 10 MB pelos bytes decodificados;
    - o handler manda o PDF para `app/statements/service.py` em vez do agente;
    - a origem da mensagem é `fatura`, e uma pergunta sobre o cartão ("qual cartão?") herda essa origem pela regra existente de origem herdada, que vale 15 min;
    - o canal aceita `documentMessage` e o `documentWithCaptionMessage.message.documentMessage` (PDF com legenda); o formato exato do webhook é conferido com um envio real no aceite;
    - cartão não resolvido: a resposta lista os cartões e pede o PDF de novo com o cartão na legenda (o PDF não fica guardado para uma segunda pergunta).

11. **Entrada pelo Jarvis:**
    - a ação local `importar_fatura(arquivo?, cartao?)` valida o caminho com `resolve()` dentro de `~`, a extensão `.pdf` e o tamanho de até 10 MB;
    - sem `arquivo`, usa o `.pdf` mais novo de `~/Downloads` modificado nos últimos 7 dias;
    - chama a ferramenta MCP `importar_fatura_pdf(pdf_base64, cartao?)`. O nome é outro porque o Jarvis junta as ferramentas locais e as do núcleo numa lista só, e ela fica em `HIDDEN_CORE_TOOLS` para o modelo nunca mandar base64; a ação local devolve `_core`/`_core_args`, e o cérebro faz a chamada e a confirmação como em qualquer ferramenta do núcleo;
    - a resposta tem o mesmo resumo e o id da pendência, e a interface usa o cartão de confirmação que já existe (como `remover_evento`);
    - a ação nunca move nem apaga o arquivo.

12. **Conselho:**
    - **Tabela `budget_items`:** colunas `id`, `kind` (`renda` ou `fixa`), `name`, `amount_cents > 0`, `day` 1–31, `payment_method_id` (nulo), `created_at` e `deleted_at`; o nome é único entre os ativos do mesmo tipo pelo código (comparação sem acento e sem maiúsculas), porque `unaccent` não é IMMUTABLE e não entra num índice do Postgres.
    - **Projeção** (`app/domain/budget.py`, pura, `clock` injetável):
      - os meses são, no crédito, os `statement_month` de cada parcela pela regra de `billing.py`, e, à vista, o mês corrente; parcelado sem cartão dito começa no mês que vem;
      - a parcela nova vem do mesmo rateio de `lancar_gasto` (sobra na primeira);
      - "parcelas comprometidas" são os gastos ativos com `installment_total > 1` e `statement_month` naquele mês;
      - a "média avulsa" usa os gastos ativos com `installment_total = 1` dos 3 meses completos anteriores, sem os de descrição que contém o nome de uma conta fixa; a soma é dividida por 3 e arredondada para baixo em centavos;
      - com menos de 3 meses de histórico, divide pelos meses que existem, e a resposta avisa "com N mês(es) de histórico".
    - **Veredito:** `segura` quando sobra ≥ 20% da renda, `atencao` entre 0 e 20%, e `arriscada` abaixo de 0.
      - O limite de 20% fica no `.env` (`CONSELHO_FOLGA_PCT=20`), porque o Kaio pode querer mudar sem mexer no código; sem o `.env` completo (CI), vale 20.
      - A comparação é em inteiros: `sobra * 100 >= renda * pct`.
    - **Grupo `conselho`:** `avaliar_compra`, `gerenciar_renda`, `gerenciar_conta_fixa` e `resumo_gastos`.
      - O prompt do grupo pede para citar veredito, mês decisivo e sobra, e proíbe calcular ou recomendar investimento ou crédito.
      - Uma resposta sem ferramenta numa pergunta de conselho escala, como em `consulta_gasto`.

13. **Classificador:**
    - entra `conselho` com exemplos ("posso comprar…?", "cabe no orçamento…?", "é seguro gastar…?", "minha renda é…", "aluguel 900 dia 10");
    - o tempo verbal separa de `gasto`: "comprei" é gasto, e "posso comprar" ou "vale a pena comprar" é conselho;
    - a lista de intenções da spec ganha `vagas`, que o código já tinha.

14. **Prova:**
    - o `tests/eval/casos.yaml` é somente leitura. Os casos novos (cerca de 6 de `conselho`, 2 de "comprei" contra "posso comprar" e 2 de renda e conta fixa) ficam escritos num rascunho em `tests/eval/casos_conselho.rascunho.yaml` e só vão ao `casos.yaml` com a autorização do Kaio (tarefa 6.2);
    - **resultado (29/10/2026):** com os 10 casos autorizados pelo Kaio, 65 de 66; só falhou a `a10` (agenda, `kind` não preenchido), a mesma falha conhecida de antes desta change;
    - a importação de fatura não passa pela prova, porque não tem classificador nem escolha de ferramenta. Ela é testada com textos fictícios e com a transcrição simulada nos testes unitários, e com as faturas reais no aceite.

15. **Ordem de arquivamento:**
    - os deltas de `agente` e `ferramentas-locais` foram escritos sobre as specs da `main`;
    - se `jarvis-estudo` ou `jarvis-projetos`, que também mexem em "Ações permitidas", forem arquivados antes, o delta de `ferramentas-locais` precisa ser refeito sobre o texto novo antes de arquivar este.

## Risks / Trade-offs

- **O modelo pula ou inventa um item.** A conferência da soma pega a omissão. Dois erros que se anulam passam, mas são improváveis, e o resumo lista os itens novos para o Kaio bater o olho.
- **Um layout que o `layout` do pypdf embaralha.** Os PDFs reais de Nubank e Inter entram no aceite (tarefa 7.1). Se um falhar, a alternativa é mandar o PDF direto ao modelo como documento, o que custa mais e só entraria com uma nova decisão.
- **Casamento errado.** Duas compras de mesmo valor na mesma semana podem trocar de par. Isso não muda o total; só a descrição do gasto manual fica valendo.
- **Conta fixa paga no cartão.** A Netflix já aparece nas faturas, então ela é descontada da média pelo nome. Se a descrição na fatura for diferente do nome cadastrado ("NETFLIX.COM" contra "streaming"), conta duas vezes. A resposta mostra as contas fixas e a média, e o Kaio vê.
- **Renda variável.** A projeção supõe a mesma renda todo mês, e isso fica dito no texto.
- **Dados financeiros na API.** O texto da fatura, já mascarado, vai à Anthropic, como as fotos de recibo. Nada da fatura vai para logs ou para o banco além dos gastos gravados.
- **Custo.** Cerca de US$ 0,003 por fatura com o Haiku, e uma escalada ao Sonnet custa uns 10× isso. Tudo fica em `agent_runs`.
