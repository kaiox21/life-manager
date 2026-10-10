## MODIFIED Requirements

### Requirement: Abrir e fechar sob demanda
O painel SHALL abrir em tela cheia, no monitor em uso, com o atalho global ⌥⇧Espaço ou pelo item "Painel" no menu da barra, e SHALL fechar com o mesmo atalho ou com Esc. Com o foco numa aba de terminal, o Esc SHALL ir para a sessão (o Claude Code o usa para interromper) e SHALL NOT fechar o painel. O painel SHALL NOT ficar aberto sozinho nem abrir ao iniciar o Mac.

#### Scenario: Abrir pelo atalho
- **WHEN** o Kaio aperta ⌥⇧Espaço com qualquer app em primeiro plano
- **THEN** o painel cobre a tela com o relógio, a agenda, os gastos, as faturas, o registro e o orbe

#### Scenario: Fechar
- **WHEN** o painel está aberto, sem foco numa aba de terminal, e o Kaio aperta Esc
- **THEN** o painel fecha e o app que estava em uso volta ao primeiro plano

#### Scenario: Esc numa aba de terminal
- **WHEN** o foco está na aba do Terminal 3 e o Kaio aperta Esc
- **THEN** o Esc vai para o Claude Code e o painel continua aberto

#### Scenario: Abrir pelo menu
- **WHEN** o Kaio escolhe "Painel" no ícone do Jarvis na barra de menus
- **THEN** o painel abre em tela cheia
