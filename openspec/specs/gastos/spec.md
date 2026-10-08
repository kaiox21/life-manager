# gastos Specification

## Purpose
Lançar e consultar gastos com o menor atrito possível, ecoando sempre o que foi gravado, sem que o LLM faça contas.

## Requirements

### Requirement: Lançar gasto
`lancar_gasto(amount_cents, description, payment_method, category?, spent_on?, installments?, merchant?)` SHALL gravar em centavos, com `spent_on` padrão hoje (data futura é recusada), categoria padrão "Outros" e parcelamento só no crédito; a resposta SHALL ecoar valor, meio, categoria, data e o vencimento da fatura.

#### Scenario: Gasto simples no crédito
- **WHEN** o usuário manda "gastei 47,90 no almoço no nubank"
- **THEN** grava 4790 centavos no Nubank, em Alimentação, hoje, e responde com o resumo e o vencimento da fatura

### Requirement: Confirmação obrigatória
`lancar_gasto` SHALL criar uma pendência em vez de gravar quando o total passa de R$ 500,00 (`amount_cents > 50000`) ou quando a origem é áudio ou foto; pendências expiram em 30 minutos e são resolvidas por `confirmar_pendente(pending_id?, decisao)`.

#### Scenario: Tênis de 600 em 3x
- **WHEN** chega "comprei um tênis de 600 em 3x no itaú crédito"
- **THEN** nada é gravado até o "sim", que grava 3 parcelas de R$ 200,00

### Requirement: Resolução de meio de pagamento
O meio SHALL ser resolvido sem acento e sem diferenciar maiúsculas, por nome, apelidos e tipo; crédito e débito do mesmo banco sem especificar contam como ambíguos; inexistente ou ambíguo devolve `erro` com `opcoes` para o modelo perguntar.

#### Scenario: Banco com crédito e débito
- **WHEN** chega "padaria 12 no itaú" havendo Itaú Crédito e Itaú Débito
- **THEN** o bot pergunta qual dos dois

#### Scenario: Único débito
- **WHEN** chega "café 9,50 no débito" havendo um único débito
- **THEN** resolve direto para ele

### Requirement: Desfazer
`desfazer_ultimo` SHALL aplicar exclusão lógica (`deleted_at`) à compra mais recente ainda ativa, com todas as parcelas do mesmo `purchase_group`.

#### Scenario: Desfazer parcelado
- **WHEN** o último lançamento foi em 3x e o usuário manda "desfaz"
- **THEN** as 3 parcelas somem das consultas, mas continuam no banco

### Requirement: Meios de pagamento
`gerenciar_meio_pagamento(name, kind, closing_day?, due_day?)` SHALL criar ou atualizar pelo nome; crédito exige `closing_day` e `due_day` (31 = último dia do mês) e os demais tipos não aceitam esses campos. Os meios reais ficam em `data/meios_pagamento.yaml` (fora do git) e entram pela seed.

#### Scenario: Cadastro de cartão
- **WHEN** chega "cadastra meu cartão c6, crédito, fecha dia 5 e vence dia 15"
- **THEN** o C6 é criado como crédito com fechamento 5 e vencimento 15

### Requirement: Consultas calculadas em SQL
`buscar_gastos(de?, ate?, category?, payment_method?, query?, limite?)`, `total_fatura(payment_method, mes_vencimento)` e `resumo_gastos(de, ate, agrupar_por)` SHALL calcular somas e agrupamentos no banco, ignorando gastos desfeitos; a busca por texto ignora acento e maiúsculas; o limite da lista não afeta a soma; `total_fatura` só considera meios de crédito e informa vencimento, fechamento e se a fatura está aberta.

#### Scenario: Fatura do Nubank
- **WHEN** o usuário pede "total da fatura do nubank de novembro"
- **THEN** o total vem de `SUM(amount_cents)` dos lançamentos com `statement_month = 2026-11-01`
