# jarvis-voz Specification

## Purpose
Falar com o Jarvis segurando ⌘⇧Espaço: o áudio é capturado pelo app e transcrito no Mac, e a resposta volta falada frase a frase (voz da Fish Audio, com a voz do macOS de reserva), curta e no estilo mordomo, com os detalhes nos cartões.

## Requirements

### Requirement: Push-to-talk
O Jarvis SHALL gravar enquanto o atalho de voz (⌘⇧Espaço) estiver segurado e SHALL enviar a gravação ao soltar. O atalho de voz SHALL ser diferente do atalho do modo texto (⌥Espaço), que continua abrindo o HUD com o campo focado e fechando com Esc. Sem fala detectada, nada é transcrito e o HUD volta a como estava.

#### Scenario: Pergunta falada
- **WHEN** o Kaio segura ⌘⇧Espaço, diz "o que eu tenho amanhã?" e solta
- **THEN** o HUD mostra a transcrição como pergunta e o Jarvis responde falando

#### Scenario: Segurou sem falar
- **WHEN** o Kaio segura ⌘⇧Espaço sem falar e solta
- **THEN** nada é transcrito e o HUD volta a como estava

#### Scenario: Modo texto continua no seu atalho
- **WHEN** o Kaio aperta ⌥Espaço e depois Esc
- **THEN** o HUD abre com o campo focado e fecha com o Esc

### Requirement: Áudio local
A captura SHALL ser feita pelo próprio Jarvis.app (permissão de Microfone atribuída a ele), e a transcrição SHALL ser local (`mlx-whisper`), com corte de silêncio por VAD; o áudio nunca sai do Mac e não é guardado.

#### Scenario: Gravação sem fala
- **WHEN** o Kaio segura o atalho e não fala nada
- **THEN** o Jarvis responde "não ouvi" sem chamar o modelo

### Requirement: Fala com streaming
Em modo voz, o Jarvis SHALL falar a resposta frase a frase, começando pela primeira assim que ela chegar no stream do modelo, com no máximo duas frases faladas; listas e tabelas ficam nos cartões. A voz SHALL ser a da Fish Audio quando houver chave e voz no `.env` e, sem elas ou se a Fish falhar, a voz pt-BR local do macOS, sem a resposta se perder. Ao chamar uma ferramenta, SHALL dizer antes uma frase curta de espera ("Um instante, senhor.").

#### Scenario: Primeira palavra rápida
- **WHEN** o Kaio faz uma pergunta simples por voz
- **THEN** a primeira palavra falada sai em menos de 4 s depois de soltar o atalho

#### Scenario: Pergunta com ferramenta
- **WHEN** o Kaio pergunta "o que eu tenho amanhã?" por voz
- **THEN** "Um instante, senhor." sai em menos de 3 s e a resposta em seguida

#### Scenario: Fish fora do ar
- **WHEN** a Fish Audio não responde
- **THEN** a resposta sai na voz local e a Fish só é tentada de novo depois de alguns minutos

### Requirement: Interrupção
Apertar o atalho de voz enquanto o Jarvis fala SHALL interromper a fala e começar a ouvir.

#### Scenario: Corrigir no meio
- **WHEN** o Jarvis está falando e o Kaio segura ⌘⇧Espaço
- **THEN** a fala para na hora e a gravação começa
