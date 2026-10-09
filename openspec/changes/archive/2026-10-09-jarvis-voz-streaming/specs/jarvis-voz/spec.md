## MODIFIED Requirements

### Requirement: Fala com streaming
Em modo voz, o Jarvis SHALL falar a resposta frase a frase, começando pela primeira assim que ela chegar no stream do modelo, com no máximo duas frases faladas; listas e tabelas ficam nos cartões. Cada frase SHALL começar a tocar enquanto o áudio dela ainda está chegando, sem esperar a frase inteira, e as frases SHALL tocar na ordem. A voz SHALL ser a da Fish Audio quando houver chave e voz no `.env` e, sem elas ou se a Fish falhar antes de sair som, a voz pt-BR local do macOS, sem a resposta se perder. Ao chamar uma ferramenta, SHALL dizer antes uma frase curta de espera ("Um instante, senhor.").

#### Scenario: Primeira palavra rápida
- **WHEN** o Kaio faz uma pergunta simples por voz
- **THEN** a primeira palavra falada sai em menos de 3 s depois de soltar o atalho

#### Scenario: Pergunta com ferramenta
- **WHEN** o Kaio pergunta "o que eu tenho amanhã?" por voz
- **THEN** "Um instante, senhor." sai em menos de 3 s e a primeira frase da resposta em menos de 4 s

#### Scenario: Fala antes de a frase chegar inteira
- **WHEN** a Fish ainda está enviando o áudio de uma frase longa
- **THEN** o Jarvis já está falando o começo dela

#### Scenario: Fish fora do ar
- **WHEN** a Fish Audio não responde
- **THEN** a resposta sai na voz local e a Fish só é tentada de novo depois de alguns minutos
