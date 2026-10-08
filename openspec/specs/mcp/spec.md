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
Cada chamada SHALL gerar `agent_runs` com `channel='desktop'`; erro de domínio volta como resultado; erro de validação volta como erro legível; escritas disparam o sync do Google Calendar.

#### Scenario: Gasto pelo Claude Desktop
- **WHEN** o Claude Desktop lança um gasto pelo MCP
- **THEN** o gasto aparece numa consulta feita pelo WhatsApp
