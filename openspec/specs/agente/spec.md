# agente Specification

## Purpose
Entender a mensagem do dono e agir pelas ferramentas certas, com modelos baratos compensados por roteamento por intenção, validação, escalada e uma prova de acerto.

## Requirements

### Requirement: Modelos por configuração
O sistema SHALL acessar os modelos pelo cliente `openai` com `base_url` do Vercel AI Gateway e SHALL ler os nomes só de `MODEL_CLASSIFIER`, `MODEL_PRIMARY` e `MODEL_ESCALATION`; `ALLOWED_PROVIDERS` vira `providerOptions.gateway.only` e `REASONING_EFFORT` (opcional) é repassado. Nenhum nome de modelo fica fixo no código.

#### Scenario: Troca de modelo
- **WHEN** `MODEL_PRIMARY` muda no `.env`
- **THEN** o app passa a usar o novo modelo após reiniciar, sem mudança de código

### Requirement: Classificação de intenção
Cada mensagem de texto SHALL ser classificada numa de `gasto`, `consulta_gasto`, `agenda`, `pessoa`, `confirmacao`, `fora_do_escopo` por uma chamada de ferramenta forçada (`classificar`, com enum); resposta fora da lista vale `fora_do_escopo`. Foto não passa pelo classificador e vai direto a `gasto`.

#### Scenario: Aniversário citando pessoa
- **WHEN** chega "aniversário da minha irmã é 14 de março"
- **THEN** a intenção é `agenda`, não `pessoa`

### Requirement: Ferramentas por grupo
O agente SHALL receber só as ferramentas do grupo da intenção (uma ferramenta pode pertencer a mais de um grupo: `gerenciar_pessoa` está em `pessoa` e `agenda`); `fora_do_escopo` não recebe ferramentas.

#### Scenario: Consulta de gasto
- **WHEN** a intenção é `consulta_gasto`
- **THEN** só `buscar_gastos`, `total_fatura` e `resumo_gastos` são oferecidas

### Requirement: Validação, escalada e desistência
Argumentos inválidos (JSON, Pydantic com `extra=forbid`, ferramenta fora do grupo) SHALL voltar ao modelo como `erro_validacao` uma vez; o segundo fracasso, ou uma resposta sem ferramenta quando a intenção exigia (`consulta_gasto`, `confirmacao` e `agenda` sem pergunta; `gasto` afirmando ter gravado), SHALL escalar para `MODEL_ESCALATION`; se a escalada falhar, o usuário recebe "Não consegui entender. Pode reformular?". Cada tentativa roda num savepoint: o que a tentativa anterior gravou é desfeito na escalada. Limite de 6 iterações.

#### Scenario: Erro de domínio não é falha
- **WHEN** a ferramenta devolve `erro` com `opcoes` (ex.: meio ambíguo)
- **THEN** o resultado volta ao modelo como resposta normal e ele pergunta ao usuário, sem escalar

### Requirement: Prompt montado a cada mensagem
O prompt SHALL trazer data e hora, a tabela de datas (hoje, ontem, amanhã, dias anteriores, próximos 7 dias, últimos 7 dias incluindo hoje, este mês, mês passado, semanas), meios de pagamento, faturas abertas por cartão (`mes_vencimento` pronto para copiar), categorias, agenda dos próximos 7 dias, pessoas cadastradas, pendência aberta e as regras do `SPEC.md` mais as regras extras (perguntar diante de `opcoes`, não perguntar o que dá para deduzir, consultar a agenda sempre, nunca mostrar ids). As últimas 10 mensagens entram como histórico, sem o prefixo do modo provisório.

#### Scenario: Fatura atual
- **WHEN** o usuário pergunta "quanto tá a fatura do nubank?"
- **THEN** o modelo copia `mes_vencimento` da tabela de faturas em vez de calcular

### Requirement: Confirmação sem LLM
Com uma pendência aberta, "sim"/"não" e variações SHALL ser resolvidos direto por `confirmar_pendente`, sem chamar o modelo.

#### Scenario: Sim depois de pendência
- **WHEN** há pendência e o usuário manda "Sim!"
- **THEN** a ação é executada e a resposta ecoa o que foi gravado, sem chamada ao LLM

### Requirement: Registro de execuções
Toda mensagem processada SHALL gerar uma linha em `agent_runs` com intenção, modelo que respondeu, escalada, ferramentas chamadas (nome, argumentos, sucesso ou erro, etapas como `transcricao`), tokens, custo em USD (tokens × preço do catálogo do gateway), latência e erro.

#### Scenario: Falha do modelo
- **WHEN** o gateway falha
- **THEN** o usuário recebe "Tive um problema para responder agora..." e `agent_runs.error` registra a causa

### Requirement: Prova de acerto
A prova (`tests/eval/casos.yaml`, somente leitura) SHALL rodar com `uv run pytest -m eval` num banco de teste, comparar a primeira chamada de ferramenta válida (com `payment_method` e `person` comparados depois da resolução, e `spent_on` omitido valendo hoje), imprimir placar por grupo e custo, e SHALL ser executada a cada mudança de prompt, ferramenta ou modelo; o mínimo para uso é 90%.

#### Scenario: Erro do fornecedor
- **WHEN** um caso falha por erro do gateway
- **THEN** o caso conta como falha no placar em vez de derrubar a rodada
