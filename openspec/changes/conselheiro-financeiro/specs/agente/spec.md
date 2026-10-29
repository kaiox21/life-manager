## MODIFIED Requirements

### Requirement: Classificação de intenção
Cada mensagem de texto SHALL ser classificada numa de `gasto`, `consulta_gasto`, `conselho`, `agenda`, `pessoa`, `confirmacao`, `vagas`, `fora_do_escopo` por uma chamada de ferramenta forçada (`classificar`, com enum); resposta fora da lista vale `fora_do_escopo`. `conselho` cobre perguntar se uma compra cabe ou é segura e cadastrar, mudar ou tirar renda e contas fixas. Foto não passa pelo classificador e vai direto a `gasto`; documento PDF não passa pelo classificador e vai direto à importação de fatura.

#### Scenario: Aniversário citando pessoa
- **WHEN** chega "aniversário da minha irmã é 14 de março"
- **THEN** a intenção é `agenda`, não `pessoa`

#### Scenario: Pergunta de conselho
- **WHEN** chega "posso comprar um fone de 400 em 4x?"
- **THEN** a intenção é `conselho`, não `gasto`

#### Scenario: Compra já feita
- **WHEN** chega "comprei um fone de 400 em 4x no nubank"
- **THEN** a intenção é `gasto`

### Requirement: Ferramentas por grupo
O agente SHALL receber só as ferramentas do grupo da intenção (uma ferramenta pode pertencer a mais de um grupo: `gerenciar_pessoa` está em `pessoa` e `agenda`); `fora_do_escopo` não recebe ferramentas. O grupo `conselho` recebe `avaliar_compra`, `gerenciar_renda`, `gerenciar_conta_fixa` e `resumo_gastos`.

#### Scenario: Consulta de gasto
- **WHEN** a intenção é `consulta_gasto`
- **THEN** só `buscar_gastos`, `total_fatura` e `resumo_gastos` são oferecidas

#### Scenario: Conselho
- **WHEN** a intenção é `conselho`
- **THEN** só `avaliar_compra`, `gerenciar_renda`, `gerenciar_conta_fixa` e `resumo_gastos` são oferecidas
