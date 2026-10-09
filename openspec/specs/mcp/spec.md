# mcp Specification

## Purpose
Expor as ferramentas do núcleo para outros clientes (Jarvis, Claude Desktop) sem duplicar regras e sem abrir o núcleo na internet.

## Requirements

### Requirement: Mesmas ferramentas
O servidor MCP (`/mcp`, Streamable HTTP, SDK `mcp` 2.x `MCPServer`) SHALL expor as mesmas ferramentas do agente, com os mesmos nomes, schema gerado dos mesmos modelos Pydantic e revalidação pelo modelo original; confirmações valem igual ao WhatsApp.

#### Scenario: Remoção pelo MCP
- **WHEN** um cliente chama `remover_evento`
- **THEN** recebe `aguardando_confirmacao` e só remove com `confirmar_pendente`

### Requirement: Contexto para clientes externos
A ferramenta `contexto` SHALL devolver os dados do prompt (data, tabela de datas, faturas abertas, cartões, categorias, pessoas, agenda da semana), sem persona nem regras do bot.

#### Scenario: Cliente sem noção de data
- **WHEN** o Claude Desktop precisa de "amanhã"
- **THEN** chama `contexto` e copia a data em vez de calcular

### Requirement: Acesso restrito
O MCP SHALL exigir `Authorization: Bearer MCP_TOKEN` (sem token configurado, fica desligado), SHALL aceitar só os hosts de `MCP_ALLOWED_HOSTS` e SHALL ficar acessível só em `127.0.0.1` ou pelo Tailscale, nunca na internet.

#### Scenario: Sem token
- **WHEN** chega uma requisição a `/mcp` sem o token
- **THEN** a resposta é 401

### Requirement: Registro e efeitos
Cada chamada às ferramentas do agente pelo MCP SHALL gerar `agent_runs` com `channel='desktop'`; erro de domínio volta como resultado; erro de validação volta como erro legível; escritas disparam o sync do Google Calendar. As ferramentas de leitura próprias do MCP, `contexto` e `painel`, SHALL NOT gerar `agent_runs` nem disparar o sync: não são pedidos do usuário ao agente, e o painel as chama a cada minuto.

#### Scenario: Gasto pelo Claude Desktop
- **WHEN** o Claude Desktop lança um gasto pelo MCP
- **THEN** o gasto aparece numa consulta feita pelo WhatsApp

#### Scenario: Painel aberto por uma hora
- **WHEN** o painel fica aberto por uma hora, atualizando a cada 60 s
- **THEN** nenhuma linha nova aparece em `agent_runs` por causa dele

### Requirement: Dados do painel
O MCP SHALL expor a ferramenta somente leitura `painel`, sem argumentos e fora dos grupos do agente do WhatsApp, que devolve em JSON: data e hora atuais; eventos de hoje e dos próximos 7 dias (com recorrências expandidas); gastos do mês corrente por categoria e o total do mês, em centavos; a fatura aberta de cada cartão de crédito (total em centavos, fechamento, vencimento e `mes_vencimento`); e os últimos 10 registros (gastos lançados e eventos criados, por ordem de criação; nos gastos, a origem `whatsapp` quando vieram de uma mensagem ou `mac` quando vieram pelo MCP). Somas e datas de fatura SHALL ser calculadas no núcleo, com a mesma regra da ferramenta `total_fatura`.

#### Scenario: Fatura aberta igual à da conversa
- **WHEN** o Jarvis chama `painel` em 09/10/2026
- **THEN** o total da fatura aberta do Nubank é o mesmo que `total_fatura` devolve para o Nubank com o `mes_vencimento` da fatura aberta

#### Scenario: Sem escrita
- **WHEN** `painel` é chamada
- **THEN** nada é gravado no banco, nem em `agent_runs`, e o sync do Google Calendar não é disparado

#### Scenario: Excluídos não aparecem
- **WHEN** um gasto foi desfeito (`deleted_at` preenchido)
- **THEN** ele não entra nas somas nem no registro do `painel`
