## Why

Hoje o Kaio fala com o Jarvis segurando ⌘⇧Espaço. Ele quer só dizer "Jarvis, …" e ser atendido, sem tocar no teclado (pedido de 10/10/2026). O `SPEC.md` previa isso: "push-to-talk antes de wake word". O push-to-talk está aceito desde 09/10, então chegou a vez da palavra de ativação.

## What Changes

> **Revisão de 10/10/2026 (depois do primeiro teste real):** o Kaio não quer que a palavra abra o HUD. "Hey Jarvis" sozinho deve **cumprimentar falando o resumo do dia** (compromissos de hoje, temperatura e o que mais importar), só por voz. Os itens abaixo já estão atualizados.

- **"Jarvis, [pedido]"**: com a escuta ligada, uma frase que **começa** com "Jarvis" ativa o Jarvis.
  - O resto da frase vira o pedido: "Jarvis, o que eu tenho amanhã?".
  - **Nenhuma janela abre:** a resposta sai só falada. Se o painel já estiver aberto, a conversa aparece nele, como hoje.
- **"Hey Jarvis" (ou "Jarvis") sozinho = resumo do dia falado**, sem chamar o modelo:
  - cumprimento pela hora ("Bom dia, senhor.");
  - temperatura agora, máxima e mínima de Brasília, e chance de chuva se for relevante (Open-Meteo, grátis e sem chave);
  - compromissos de hoje (da agenda do núcleo, a mesma do painel);
  - fatura que fecha ou vence nos próximos 3 dias, se houver;
  - pedidos de permissão de terminal esperando, se houver.
  - Depois do resumo, ele fica uns segundos ouvindo um pedido sem precisar dizer o nome de novo.
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
- `jarvis-voz`: ativação por "Jarvis, [pedido]" só por voz, resumo do dia falado com "Hey Jarvis" sozinho, escuta ligada/desligada pelo menu, escuta local e leve, e sem se ativar com a própria voz do Jarvis.

## Impact

- **App (Rust):**
  - captura contínua do microfone com a crate `cpal`, enquanto a escuta estiver ligada. A permissão de Microfone continua sendo do Jarvis.app;
  - manda o áudio (16 kHz, mono) ao cérebro pelo WebSocket local;
  - item no menu da barra.
- **Cérebro (Python):**
  - detector de palavra-chave `sherpa-onnx` (dependência nova, Apache 2.0, modelo em inglês de 3,3 M parâmetros, cerca de 19 MB), com o porteiro de voz (VAD) que já existe;
  - ao detectar a palavra, junta o pedido até o silêncio e segue pelo mesmo caminho da voz de hoje.
- **Interface:** a palavra não abre janela; o HUD deixa de ser mostrado por ela. O painel, se aberto, mostra a conversa.
- **Rede:** uma chamada ao Open-Meteo por resumo (só latitude e longitude, configuráveis no `.env`; padrão Brasília). Sem internet, o resumo sai sem o clima.
- **`SPEC.md`:** decisão da palavra de ativação (motor, privacidade, ponto laranja); fecha "push-to-talk antes de wake word".
