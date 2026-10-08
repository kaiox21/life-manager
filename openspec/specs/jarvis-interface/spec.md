# jarvis-interface Specification

## Purpose
Interface do Jarvis (Tauri + React): chamar de qualquer app com ⌥Espaço e ver os passos e as respostas em cartões, num HUD holográfico, com confirmação explícita das ações sensíveis.

## Requirements

### Requirement: Chamada rápida
O Jarvis SHALL ficar como ícone na barra de menus e abrir o HUD com o atalho global ⌥Espaço (configurável) sobre qualquer app; Esc fecha.

#### Scenario: Abrir sobre outro app
- **WHEN** o Kaio aperta ⌥Espaço com o Safari em primeiro plano
- **THEN** o HUD aparece embaixo e no centro, com a caixa de texto focada

### Requirement: Estados visíveis
O HUD SHALL mostrar os estados digitando, pensando (orbe pulsando e passos como "consultando a agenda…") e respondendo, recebidos por streaming do cérebro.

#### Scenario: Consulta à agenda
- **WHEN** o agente chama `buscar_eventos`
- **THEN** o passo "consultando a agenda…" aparece antes da resposta

### Requirement: Respostas em cartões
Resultados das ferramentas SHALL aparecer como cartões tipados (agenda, gastos, fatura, gráfico, arquivos, texto), desenhados com os números vindos das ferramentas, nunca calculados pela interface nem pelo modelo.

#### Scenario: Fatura
- **WHEN** a resposta usa `total_fatura`
- **THEN** o HUD mostra um cartão com total, vencimento, fechamento e maiores itens

### Requirement: Confirmação na interface
Pendências do núcleo e a leitura da área de transferência SHALL pedir confirmação explícita no HUD antes de seguir.

#### Scenario: Gasto acima de R$ 500
- **WHEN** o núcleo devolve `aguardando_confirmacao`
- **THEN** o HUD mostra o resumo com botões Confirmar e Cancelar
