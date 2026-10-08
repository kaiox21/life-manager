# Gerenciador de Vida — Visão e decisões

Versão de 08/10/2026. Este arquivo guarda o **porquê**: visão, decisões, riscos e o que está em aberto. O **o quê** (requisitos e cenários de cada parte) está em `openspec/specs/<capacidade>/spec.md`. Mudanças novas entram como *changes* do OpenSpec (`openspec/changes/`). As fases 1 a 7, anteriores ao OpenSpec, estão registradas em `docs/fases/`.

## Visão e escopo

Um assistente pessoal de usuário único (Kaio) com duas portas para o mesmo núcleo: **WhatsApp**, para lançamentos, consultas e lembretes, e o **Jarvis no Mac**, com design próprio, texto e voz. O núcleo **lê e escreve** num banco próprio por linguagem natural: o LLM escolhe a ferramenta, e as regras moram no código. Texto, áudio e foto de recibo são aceitos como entrada. O núcleo também expõe as ferramentas por MCP.

**Exemplos que o sistema resolve:**

| Mensagem | O que o sistema faz |
| --- | --- |
| "coloque na agenda o aniversário da minha irmã, 14 de março" | Cria evento anual no banco e no Google Calendar; confirma |
| "que dia é minha prova de direito administrativo?" | Busca em eventos e responde com data e hora |
| "gastei 47 no almoço no Nubank" | Lança a despesa (valor, categoria, cartão, hoje) e devolve o resumo |
| (foto de um cupom fiscal ou print de Pix) | Extrai estabelecimento, valor e data; pede confirmação antes de gravar |
| (áudio) "paguei 120 de gasolina no pix" | Transcreve, mostra o que entendeu, pede confirmação |
| "total da fatura do Nubank de novembro" | Soma em SQL os lançamentos daquele ciclo de fatura |
| "quanto gastei com mercado esse mês?" | Agregação por categoria e período |

**Dentro:** agenda (eventos, recorrências, prazos, pessoas), gastos (lançamento, recibo, consultas e totais por fatura, categoria e período), lembretes proativos, MCP, Jarvis.

**Fora (por ora):** importação automática de fatura, Open Finance, painel web, múltiplos usuários, metas e orçamento.

## Mapa das capacidades (`openspec/specs`)

| Capacidade | Cobre |
| --- | --- |
| `canal-whatsapp` | Evolution API, webhook, allowlist, idempotência, envio só ao dono, modo provisório |
| `agente` | modelos, classificador, grupos de ferramentas, validação e escalada, prompt, `agent_runs`, prova |
| `gastos` | lançar, confirmar, resolver meio, desfazer, cartões, consultas em SQL |
| `fatura` | regra da fatura, último dia do mês, parcelas, fatura aberta |
| `agenda` | eventos, pessoas, busca com recorrência, atualizar e remover, Google Calendar |
| `midia` | áudio (`faster-whisper` local), foto de recibo, origem herdada, mídia não guardada |
| `lembretes` | resumo do dia, lembrete de evento, fechamento de fatura, uma vez só |
| `mcp` | ferramentas do núcleo por MCP, `contexto`, acesso restrito |
| `operacao` | hospedagem, segredos, backup cifrado, alerta de queda, dead man's switch |

## Decisões e riscos

| Decisão | Escolha | Risco principal | Mitigação |
| --- | --- | --- | --- |
| Canal WhatsApp | Evolution API v2 (Baileys, não oficial), self-hosted | Banimento do número; quebra quando o WhatsApp Web muda | Chip dedicado (ainda não em uso: ver modo provisório); volume baixo; camada `channel/` isolada |
| Agenda | Tabela própria é a fonte de verdade, espelhada no Google Calendar principal | Divergência entre banco e Calendar | Sync unidirecional banco → Calendar; `gcal_event_id`; edições sempre pelas ferramentas |
| Linguagem | Python 3.12 (FastAPI + cliente `openai` com o Vercel AI Gateway) | — | — |
| Entrada de gastos | Texto, áudio e foto de recibo; sem importação de fatura | "Total da fatura" só é exato se tudo for lançado | Cartão com dia de fechamento; conferência contra o app do banco |
| Hospedagem do núcleo | Oracle Cloud pay-as-you-go, São Paulo, dentro da cota grátis (desde 15/06/2026: 2 OCPU / 12 GB); Hetzner como plano B. **Provisório (08/10/2026): roda no Mac** (Oracle sem capacidade ARM); change `deploy-vps` pausado | Mac fechado = bot e lembretes parados | Backup cifrado; scripts de deploy prontos; atrasos de lembrete recuperados por até 6 h |
| Integração entre canais | Ferramentas do núcleo por MCP; Tailscale quando houver VPS | Duas lógicas divergindo | Regras só no núcleo; o Jarvis não toca o banco |
| Jarvis | Tauri 2 + React/Vite/TS (interface) e Python (agente, cliente MCP, ferramentas locais) no MacBook Air M5; voz local | Latência da voz; permissões do macOS | Push-to-talk antes de wake word; streaming; modelo rápido antes da voz |
| Modelo de IA | Modelos baratos via Vercel AI Gateway. Hoje `gpt-5-nano` em classificador, principal e escalada (provisório: o gateway está no plano gratuito) | Erros de ferramenta e de data; lentidão (20–40 s) | Prova (56 casos, ≥ 90%), roteamento por intenção, validação e escalada |
| Política de gravação | Grava direto com "desfazer"; confirma foto, áudio, exclusões e valores acima de R$ 500 | Gasto errado gravado sem perceber | Eco do que foi gravado em toda resposta |

**Modo provisório "conversa comigo mesmo" (`SELF_CHAT_MODE`, 07/10/2026).**
- Sem o chip dedicado, a instância está conectada ao número pessoal do dono, que fala com o bot na conversa consigo mesmo.
- Riscos aceitos: o número pessoal fica exposto a banimento, e os avisos não fazem o celular tocar.
- Ao trocar para o chip: `SELF_CHAT_MODE=false` e escanear o QR de novo.

**Por que isolar o canal.** A Evolution API suporta Baileys e a Cloud API oficial (`WHATSAPP-BUSINESS`) com o mesmo formato de webhook. Se o número for banido, troca-se a integração sem reescrever o agente.

**Contexto regulatório (out/2026).**
- Desde 15/01/2026, a Meta proíbe assistentes de IA de uso geral na API oficial.
- No Brasil, uma liminar do Cade suspende a proibição, e a Meta cobra "AI Providers" por mensagem a números +55 desde 11/03/2026.
- Um bot pessoal provavelmente não se enquadra, mas é zona cinzenta. Só pesa se migrar para a API oficial.

**Conta Claude compartilhada com o trabalho (08/10/2026).** O conector MCP está só no Claude Desktop do Mac, desligado por padrão nas conversas. O histórico de conversas é da conta, então dados pessoais usados ali ficam visíveis a quem compartilha a conta. O Claude Code não usa o MCP.

## Arquitetura

```mermaid
flowchart LR
  U[Você no WhatsApp] <--> EV[Evolution API]
  EV <--> APP[App FastAPI<br/>allowlist, dedupe,<br/>transcreve áudio]
  APP <--> AG[Agente LLM<br/>Vercel AI Gateway]
  AG <-->|tool calls| T[Ferramentas<br/>do núcleo]
  T <--> DB[(Postgres<br/>fonte de verdade)]
  T -->|sync| GC[Google Calendar]
  DB --> S[APScheduler<br/>lembretes] --> EV
  T --- MCP["/mcp<br/>token"]
  J[Jarvis no Mac<br/>Tauri + Python<br/>ferramentas locais] <-->|MCP| MCP
  CD[Claude Desktop] <-->|MCP| MCP
```

## Riscos e questões em aberto

O risco que mais derruba projetos assim é parar de lançar os gastos, não um defeito técnico. O atrito de entrada deve ser mínimo, e a fatura precisa ser conferível.

**Riscos**

- Banimento do número: perde-se o canal, não os dados. No modo provisório, o banido seria o número pessoal.
- Interpretação errada de valor ou data: eco do que foi gravado + "desfazer".
- Fatura divergente do banco: estornos, IOF e anuidade não entram sozinhos; considerar a ferramenta `ajuste_fatura`.
- Custo de LLM: orçamento mensal no painel do Vercel AI Gateway.
- Lentidão do modelo atual (20–40 s): inviabiliza a voz até haver um modelo rápido.

**Questões em aberto**

- [ ] **Modelo rápido** para o Jarvis por voz: créditos pagos no gateway (e BYOK com os US$ 100 da Anthropic) ou API Anthropic direto. Bloqueia a voz.
- [ ] Escalada de verdade (hoje igual ao principal) e comparação dos outros candidatos: depende de créditos pagos no gateway.
- [ ] Hospedagem: Oracle (tentativas) ou Hetzner. Change `deploy-vps`.
- [ ] Chip dedicado para sair do modo provisório.
- [ ] Teste real da foto de recibo (adiado pelo Kaio).
- [ ] **Roteador de modelos por dificuldade** (pedido de 08/10/2026), junto com o Jarvis. O classificador devolve também a dificuldade, sem chamada extra, combinada com sinais fixos. Uma tabela no `.env` liga cada faixa a um modelo, com a escalada como rede de segurança. A tabela sai da prova (acerto, custo e latência por faixa).
- [ ] **Sessões do Claude Code no Jarvis** (pedido de 08/10/2026): ver o estado e ser avisado quando uma sessão termina ou espera resposta. Só leitura e avisos.

**Decididas (resumo):**
- calendário principal, com avisos do Google desligados;
- `faster-whisper` local;
- mídia não é guardada;
- cartões reais só no banco local;
- backup no Google Drive, cifrado com `age`;
- alerta por ntfy;
- Jarvis com Tauri + React;
- OpenSpec a partir de 08/10/2026;
- categorias Alimentação, Mercado, Transporte, Casa, Saúde, Lazer, Educação, Assinaturas, Outros.
