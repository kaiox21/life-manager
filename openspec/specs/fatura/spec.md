# fatura Specification

## Purpose
Decidir em que fatura cada compra no crédito cai, inclusive parcelas, de forma determinística e testada (`app/domain/billing.py`), nunca pelo LLM.

## Requirements

### Requirement: Fatura de uma compra
Uma compra feita antes do fechamento efetivo do mês SHALL entrar na fatura que fecha nesse mês; no dia do fechamento ou depois, na que fecha no mês seguinte. A fatura vence no mesmo mês do fechamento se `due_day > closing_day`; senão, no mês seguinte. `statement_month` é o dia 1 do mês de vencimento.

#### Scenario: Cartão que fecha dia 25 e vence dia 5
- **WHEN** a compra é em 07/10/2026
- **THEN** a fatura vence em 05/11/2026

#### Scenario: Compra no dia do fechamento
- **WHEN** a compra é no próprio dia do fechamento
- **THEN** vai para a fatura seguinte

### Requirement: Fechamento no último dia do mês
`closing_day` ou `due_day` maior que o último dia do mês SHALL valer o último dia: "fecha no último dia" é gravado como `closing_day = 31`.

#### Scenario: Fevereiro
- **WHEN** um cartão com `closing_day = 31` tem compra em 28/02/2027
- **THEN** a compra está no dia do fechamento e vai para a fatura seguinte

### Requirement: Parcelas
Uma compra em N parcelas SHALL gerar N linhas com o mesmo `purchase_group`, `statement_month` avançando um mês cada (virando o ano quando preciso), valores inteiros em centavos cuja soma é exatamente o total, com a sobra na primeira parcela; parcelamento só no crédito.

#### Scenario: R$ 100,00 em 3x
- **WHEN** a compra é parcelada em 3
- **THEN** as parcelas são 33,34 + 33,33 + 33,33

### Requirement: Fatura aberta
A fatura aberta hoje SHALL ser a mesma em que uma compra feita hoje entraria; ela é exibida pronta no prompt para o modelo copiar.

#### Scenario: Antes do fechamento
- **WHEN** hoje é 07/10/2026 e o cartão fecha no último dia e vence dia 8
- **THEN** a fatura aberta vence em 08/11/2026
