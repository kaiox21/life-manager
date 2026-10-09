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
O HUD SHALL mostrar os estados digitando, ouvindo (forma de onda ao vivo do microfone), transcrevendo, pensando (orbe pulsando e passos como "consultando a agenda…"), respondendo e falando, recebidos por streaming do cérebro; com o Jarvis parado (online, sem ouvir, pensar ou falar), o orbe SHALL ficar parado, sem animação, e voltar a se mexer assim que houver atividade; em modo voz, a transcrição SHALL aparecer como a pergunta do turno.

#### Scenario: Consulta à agenda
- **WHEN** o agente chama `buscar_eventos`
- **THEN** o passo "consultando a agenda…" aparece antes da resposta

#### Scenario: Ouvindo
- **WHEN** o atalho de voz está segurado
- **THEN** o HUD mostra a forma de onda reagindo à voz e o estado "ouvindo"

#### Scenario: HUD aberto e parado
- **WHEN** o HUD fica aberto sem conversa em andamento
- **THEN** o orbe fica parado e o Jarvis gasta menos de 5% de CPU (app e processos do WebKit somados)

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
