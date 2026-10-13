## 1. Modo

- [ ] 1.1 `jarvis/study.py`: `StudyMode` com fases, hora marcada, `tick()` (pergunta na hora; > 10 min de atraso encerra em silêncio), retomada e encerramento na subida pelo `proativo.json`; testes com relógio falso (bloco → pergunta → pausa → pergunta → novo bloco; dormiu além do fim; reinício no meio e depois da hora)
- [ ] 1.2 Foco: `shortcuts list` com limite de 10 s, nome exato, `shortcuts run` com limite, `foco_ligado`, desligar só se ligou e em todo caminho de encerrar; testes com runner falso (atalho inexistente, `run` que demora, falha)
- [ ] 1.3 Playlist: busca `minha_playlist` pelo nome do `.env` e toca; sem login ou sem resultado segue sem música e diz; música não muda na pausa nem no fim; testes com Spotify falso
- [ ] 1.4 `Proactive.hold("estudo", on)`: avisos descartados e nada falado enquanto retido; `step()` chama `study.tick()`; testes

## 2. Cérebro

- [ ] 2.1 `_open_answer` generalizada (afirmativa com resposta e ação, `on_timeout`) sem mudar o fechamento do dia e o lembrete; `brain.study_prompt`; testes ("sim", "não", "mais 25 minutos" vai ao modelo, sem resposta encerra)
- [ ] 2.2 Ferramenta local `modo_estudo(acao, minutos, pausa)` no catálogo (sem confirmação; faixas validadas; resultado com o que ligou), `local_action("estudo_iniciar"|"estudo_parar")` com resposta fixa, `estudo` nos dados do painel, variáveis do `.env` e `.env.example`; testes
- [ ] 2.3 Ligação em `__main__.py` (Spotify, runner, proativo) e `tests/jarvis/test_local_tools.py::test_schemas_para_o_modelo` atualizado

## 3. Interface

- [ ] 3.1 Botão Estudo nos modos (`hud-mode--f`): inicia parado, mostra "Estudo N min" / "Pausa N min" rodando e encerra ao clicar; estado "estudo · faltam N min"; tipo `estudo`; testes (rótulo pelo relógio local, clique certo em cada fase)

## 4. Fechamento

- [ ] 4.1 `uv run pytest`, `uv run ruff check . && uv run ruff format .`, testes da interface, `openspec validate --all --strict`; reconstruir o app e reiniciar o cérebro (o núcleo não muda)
- [ ] 4.2 Prova do agente não roda: a ferramenta é local do Jarvis e os casos de `tests/eval/casos.yaml` são do WhatsApp; conferir a escolha do modelo com 4 pedidos reais ("modo estudo por 25 minutos com pausa de 5", "para o estudo", "quanto falta do estudo", "mais 25 minutos" na resposta), custa frações de centavo
- [ ] 4.3 Aceite real com o Kaio (antes: criar os atalhos "Jarvis Foco" e "Jarvis Foco Fim" no app Atalhos, instruções em `docs/proximos-passos.md`): modo pela voz com Foco e playlist; sem os atalhos; pelo botão; fim do bloco com "sim" e "não"; "para o estudo"; lembrete não falado durante o bloco; Mac dormindo além do fim; o Foco continua ligado ao trocar de app
- [ ] 4.4 `SPEC.md` (modo estudo: Foco só por atalhos do Kaio, Jarvis não cria atalhos, silêncio durante o modo), `/opsx:archive` depois de `jarvis-proativo`, atualizar `docs/proximos-passos.md`
