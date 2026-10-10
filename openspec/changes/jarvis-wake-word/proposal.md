## Why

Hoje o Kaio fala com o Jarvis segurando ⌘⇧Espaço. Ele quer só dizer "Jarvis, …" e ser atendido, sem tocar no teclado (pedido de 10/10/2026). O `SPEC.md` previa isso: "push-to-talk antes de wake word". O push-to-talk está aceito desde 09/10, então chegou a vez da palavra de ativação.

## What Changes

- **"Jarvis, [pedido]"**: com a escuta ligada, uma frase que **começa** com "Jarvis" ativa o Jarvis.
  - O resto da frase vira o pedido: "Jarvis, o que eu tenho amanhã?".
  - O HUD aparece sem roubar o foco, como no push-to-talk, e a resposta sai falada.
  - "Jarvis" sozinho abre o HUD ouvindo, e o pedido vem em seguida.
- **Escuta ligada e desligada** por um item no menu da barra ("Ouvir 'Jarvis'"), lembrado entre reinícios.
  - Desligada, o microfone fica fechado e o ponto laranja do macOS some.
  - Ligada, o ponto laranja fica aceso o tempo todo: é o aviso do sistema e não dá para esconder.
- **Tudo local:**
  - um detector pequeno de palavra-chave roda no Mac, com cerca de 2% de um núcleo de CPU;
  - o áudio não sai do Mac e não é guardado;
  - só o trecho do pedido vai para a transcrição local que já existe.
- **Sem se ativar sozinho:** a escuta pausa enquanto o Jarvis fala e enquanto o atalho de voz está segurado.
- O push-to-talk (⌘⇧Espaço) continua igual.

## Non-goals

- Outra palavra ou frase de ativação ("Ei, Jarvis" no meio da frase, "Computador").
- Treinar um modelo próprio. Fica para depois, se o modelo pronto falhar com a voz do Kaio.
- Ativar com o Mac bloqueado ou dormindo.
- Escuta contínua de conversa: nada além do pedido que vem depois de "Jarvis" é transcrito.
- Interromper a fala do Jarvis dizendo "Jarvis". Para interromper, continua valendo o atalho de voz.
- Desligar sozinho em reuniões. O Kaio desliga pelo menu.

## Capabilities

### New Capabilities
<!-- nenhuma -->

### Modified Capabilities
- `jarvis-voz`: ativação por "Jarvis, [pedido]", escuta ligada/desligada pelo menu, escuta local e leve, e sem se ativar com a própria voz do Jarvis.

## Impact

- **App (Rust):**
  - captura contínua do microfone com a crate `cpal`, enquanto a escuta estiver ligada. A permissão de Microfone continua sendo do Jarvis.app;
  - manda o áudio (16 kHz, mono) ao cérebro pelo WebSocket local;
  - item no menu da barra.
- **Cérebro (Python):**
  - detector de palavra-chave `sherpa-onnx` (dependência nova, Apache 2.0, modelo em inglês de 3,3 M parâmetros, cerca de 19 MB), com o porteiro de voz (VAD) que já existe;
  - ao detectar a palavra, junta o pedido até o silêncio e segue pelo mesmo caminho da voz de hoje.
- **Interface:** um estado "ouvindo" aberto pela palavra (HUD sem foco, ou o painel se estiver aberto).
- **`SPEC.md`:** decisão da palavra de ativação (motor, privacidade, ponto laranja); fecha "push-to-talk antes de wake word".
