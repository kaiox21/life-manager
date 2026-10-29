## Purpose
Responder "essa compra é segura?" com números calculados no código a partir da renda, das contas fixas, das parcelas já comprometidas e do histórico de gastos, com o modelo só explicando.

## ADDED Requirements

### Requirement: Renda e contas fixas
`gerenciar_renda(name, amount_cents, day, remover?)` e `gerenciar_conta_fixa(name, amount_cents, day, payment_method?, remover?)` SHALL criar ou atualizar pelo nome (sem acento e sem diferenciar maiúsculas), com valor em centavos maior que zero e dia de 1 a 31 (31 = último dia do mês); `remover` aplica exclusão lógica. A resposta SHALL ecoar o que foi gravado e o total mensal de renda e de contas fixas.

#### Scenario: Cadastro da renda
- **WHEN** chega "minha renda é 3.500 todo dia 5"
- **THEN** grava a renda "Salário" de 350000 centavos no dia 5 e responde com o total mensal

#### Scenario: Tirar uma conta
- **WHEN** chega "tira a academia das contas fixas"
- **THEN** a conta "Academia" recebe `deleted_at` e deixa de entrar no conselho

### Requirement: Avaliar compra
`avaliar_compra(amount_cents, description?, payment_method?, installments?)` SHALL projetar, para cada mês que a compra atinge (o mês da fatura de cada parcela no crédito; o mês corrente à vista), em centavos: renda do mês, contas fixas, parcelas já comprometidas naquele mês (gastos ativos parcelados com `statement_month` nesse mês), a média mensal dos gastos avulsos dos 3 meses completos anteriores e a parcela nova; e a sobra = renda − contas fixas − parcelas − média − parcela nova. Gastos cuja descrição contém o nome de uma conta fixa SHALL ficar fora da média, para não contar a mesma conta duas vezes. A resposta SHALL trazer os números de cada mês e o veredito.

#### Scenario: Fone em 4x
- **WHEN** chega "posso comprar um fone de 400 em 4x no nubank?" com renda de R$ 3.500, contas fixas de R$ 1.500, média avulsa de R$ 900 e R$ 300 de parcelas em dezembro
- **THEN** a projeção de dezembro mostra sobra de R$ 700,00 (20%) depois da parcela de R$ 100,00

### Requirement: Veredito fixo
O veredito SHALL ser decidido pelo código: `segura` quando a sobra de todos os meses projetados é pelo menos 20% da renda do mês; `atencao` quando alguma sobra fica entre 0 e 20%; `arriscada` quando alguma sobra é negativa. O mês decisivo é o de menor sobra.

#### Scenario: Mês negativo
- **WHEN** a parcela nova deixa janeiro com sobra de −R$ 50,00
- **THEN** o veredito é `arriscada` e janeiro é o mês decisivo

### Requirement: Sem renda, sem palpite
Sem renda cadastrada, `avaliar_compra` SHALL devolver `erro` pedindo a renda, e o modelo SHALL perguntar em vez de opinar.

#### Scenario: Primeira pergunta
- **WHEN** o Kaio pergunta "posso gastar 200 num tênis?" sem renda cadastrada
- **THEN** a resposta pergunta qual é a renda mensal e o dia em que cai

### Requirement: O modelo só explica
A resposta do conselho SHALL usar apenas os números devolvidos por `avaliar_compra`, citando o veredito, o mês decisivo e a sobra; o modelo SHALL NOT calcular valores novos nem mudar o veredito, e SHALL NOT recomendar investimentos ou crédito. No Jarvis por voz, a resposta segue o limite de duas frases e a tabela mensal vai para o cartão.

#### Scenario: Compra arriscada
- **WHEN** o veredito é `arriscada` com janeiro em −R$ 50,00
- **THEN** a resposta diz que não é seguro, cita janeiro e os −R$ 50,00, e pode sugerir mais parcelas ou esperar, sem inventar valores
