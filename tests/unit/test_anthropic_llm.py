import json
from decimal import Decimal
from types import SimpleNamespace as NS

from app.agent.llm import (
    AnthropicLLM,
    make_llm,
    to_anthropic,
    to_anthropic_tool_choice,
    to_anthropic_tools,
)


def test_traduz_conversa_com_ferramentas_e_resultados_agrupados():
    msgs = [
        {"role": "system", "content": "Você é o assistente."},
        {"role": "user", "content": "abre o safari e a agenda"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "abrir_app", "arguments": '{"nome": "Safari"}'},
                },
                {
                    "id": "c2",
                    "type": "function",
                    "function": {"name": "buscar_eventos", "arguments": "{}"},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": '{"status": "aberto"}'},
        {"role": "tool", "tool_call_id": "c2", "content": '{"eventos": []}'},
    ]
    system, out = to_anthropic(msgs)
    assert system == "Você é o assistente."
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert out[1]["content"][0] == {
        "type": "tool_use",
        "id": "c1",
        "name": "abrir_app",
        "input": {"nome": "Safari"},
    }
    # os dois resultados no mesmo turno do usuário
    assert [b["tool_use_id"] for b in out[2]["content"]] == ["c1", "c2"]


def test_imagem_em_data_url_vira_bloco_base64():
    _, out = to_anthropic(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "recibo"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBOR"}},
                ],
            }
        ]
    )
    assert out[0]["content"][1] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "iVBOR"},
    }


def test_ferramentas_e_escolha_forcada():
    tools = to_anthropic_tools(
        [
            {
                "type": "function",
                "function": {
                    "name": "classificar",
                    "description": "d",
                    "parameters": {"type": "object"},
                },
            }
        ]
    )
    assert tools == [
        {
            "name": "classificar",
            "description": "d",
            "input_schema": {"type": "object"},
            "cache_control": {"type": "ephemeral"},
        }
    ]
    assert to_anthropic_tool_choice({"type": "function", "function": {"name": "classificar"}}) == {
        "type": "tool",
        "name": "classificar",
    }
    assert to_anthropic_tool_choice("auto") is None


class FakeMessages:
    def __init__(self):
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return NS(
            content=[
                NS(type="text", text="Marquei."),
                NS(type="tool_use", id="t1", name="criar_evento", input={"title": "Dentista"}),
            ],
            usage=NS(input_tokens=1000, output_tokens=200),
        )


async def test_chat_traduz_ida_e_volta_e_calcula_custo():
    fake = FakeMessages()
    llm = AnthropicLLM(
        api_key="x", prices={"m": (0.10, 0.50)}, reasoning_effort="low", client=NS(messages=fake)
    )
    c = await llm.chat(
        "m",
        [{"role": "system", "content": "s"}, {"role": "user", "content": "oi"}],
        tools=[{"type": "function", "function": {"name": "criar_evento", "parameters": {}}}],
    )
    assert fake.kwargs["system"] == "s" and fake.kwargs["output_config"] == {"effort": "low"}
    assert "tool_choice" not in fake.kwargs  # auto é o padrão
    assert c.content == "Marquei."
    assert c.tool_calls[0].name == "criar_evento"
    assert json.loads(c.tool_calls[0].arguments) == {"title": "Dentista"}
    assert c.cost_usd == Decimal("0.0001") + Decimal("0.0001")  # 1000*0,10/1M + 200*0,50/1M
    assert c.assistant_message()["tool_calls"][0]["function"]["name"] == "criar_evento"


class FakeStream:
    """Como o stream do SDK: itera eventos (texto e início de blocos)."""

    def __init__(self, pieces, final, events=()):
        self.pieces, self.final, self.events = pieces, final, list(events)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def __aiter__(self):
        for e in self.events:
            yield e
        for p in self.pieces:
            yield NS(type="text", text=p)

    async def get_final_message(self):
        return self.final


async def test_stream_entrega_pedacos_e_depois_o_completion():
    final = NS(
        content=[NS(type="text", text="Olá, Kaio.")], usage=NS(input_tokens=10, output_tokens=3)
    )
    messages = NS(stream=lambda **kw: FakeStream(["Olá, ", "Kaio."], final))
    llm = AnthropicLLM(api_key="x", client=NS(messages=messages))
    got = [p async for p in llm.stream("m", [{"role": "user", "content": "oi"}])]
    assert got[:2] == ["Olá, ", "Kaio."]
    assert got[2].content == "Olá, Kaio." and got[2].output_tokens == 3


def test_fabrica_escolhe_provedor(settings):
    from pydantic import SecretStr

    s = settings.model_copy(
        update={
            "llm_provider": "anthropic",
            "anthropic_api_key": SecretStr("k"),
            "model_prices": '{"claude-haiku-5-5": [0.1, 0.5]}',
        }
    )
    assert isinstance(make_llm(s), AnthropicLLM)
    g = settings.model_copy(update={"ai_gateway_api_key": SecretStr("g")})
    assert type(make_llm(g)).__name__ == "GatewayLLM"


# --- ferramentas de servidor: busca e leitura de páginas (Jarvis com internet)


def _usage(i=100, o=20, searches=0, fetches=0):
    return NS(
        input_tokens=i,
        output_tokens=o,
        server_tool_use=NS(web_search_requests=searches, web_fetch_requests=fetches),
    )


class Block(NS):
    def model_dump(self, exclude_none=True):
        return {k: v for k, v in vars(self).items() if not (exclude_none and v is None)}


def _search_response():
    return NS(
        stop_reason="end_turn",
        usage=_usage(searches=2),
        content=[
            Block(type="server_tool_use", id="srv1", name="web_search", input={"query": "dólar"}),
            Block(
                type="web_search_tool_result",
                tool_use_id="srv1",
                content=[{"encrypted_content": "x"}],
            ),
            Block(
                type="text",
                text="O dólar fechou a R$ 5,40.",
                citations=[
                    {"url": "https://g1.globo.com/x", "title": "G1"},
                    {"url": "https://g1.globo.com/x", "title": "G1"},
                ],
            ),
        ],
    )


def test_ferramentas_de_servidor_vao_cruas_e_o_cache_fica_nas_do_mac():
    from app.agent.llm import server_tool, to_anthropic_tools

    tools = [
        {"type": "function", "function": {"name": "abrir_app", "parameters": {}}},
        server_tool({"type": "web_search_20250305", "name": "web_search", "max_uses": 3}),
    ]
    out = to_anthropic_tools(tools)
    assert out[0]["name"] == "abrir_app" and out[0]["cache_control"]
    assert out[1] == {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}


async def test_busca_custa_por_uso_e_traz_as_fontes_e_os_blocos_crus():
    async def create(**kw):
        return _search_response()

    llm = AnthropicLLM(
        api_key="x", prices={"m": (0.10, 0.50)}, client=NS(messages=NS(create=create))
    )
    c = await llm.chat("m", [{"role": "user", "content": "e o dólar?"}])
    assert c.content == "O dólar fechou a R$ 5,40." and c.searches == 2
    assert c.cost_usd == Decimal("0.00001") + Decimal("0.00001") + Decimal("0.02")
    assert c.sources == [{"title": "G1", "url": "https://g1.globo.com/x"}]
    # os blocos voltam intactos se a conversa continuar (conteúdo cifrado da busca)
    msg = c.assistant_message()
    _, converted = to_anthropic([{"role": "user", "content": "oi"}, msg])
    assert converted[-1]["content"][1]["type"] == "web_search_tool_result"


async def test_turno_pausado_continua_e_soma_tudo():
    sent = []
    first = NS(
        stop_reason="pause_turn",
        usage=_usage(searches=1),
        content=[Block(type="server_tool_use", id="s", name="web_search", input={})],
    )
    second = NS(
        stop_reason="end_turn",
        usage=_usage(searches=1),
        content=[Block(type="text", text="Pronto.")],
    )
    replies = iter([first, second])

    async def create(**kw):
        sent.append(kw["messages"])
        return next(replies)

    llm = AnthropicLLM(api_key="x", client=NS(messages=NS(create=create)))
    c = await llm.chat("m", [{"role": "user", "content": "pesquisa"}])
    assert c.content == "Pronto." and c.searches == 2 and len(sent) == 2
    assert sent[1][-1]["role"] == "assistant"  # o turno pausado foi devolvido


async def test_stream_avisa_quando_comeca_a_buscar():
    from app.agent.llm import ServerToolUse

    final = _search_response()
    start = NS(
        type="content_block_start", content_block=NS(type="server_tool_use", name="web_search")
    )
    messages = NS(stream=lambda **kw: FakeStream(["O dólar…"], final, events=[start]))
    llm = AnthropicLLM(api_key="x", client=NS(messages=messages))
    got = [p async for p in llm.stream("m", [{"role": "user", "content": "e o dólar?"}])]
    assert got[0] == ServerToolUse("web_search") and got[1] == "O dólar…"
    assert got[-1].sources and got[-1].searches == 2


async def test_gateway_ignora_ferramentas_de_servidor():
    from app.agent.llm import GatewayLLM, server_tool

    seen = {}

    async def create(**kw):
        seen.update(kw)
        msg = NS(content="ok", tool_calls=None)
        return NS(
            choices=[NS(message=msg)], usage=NS(prompt_tokens=1, completion_tokens=1), model="m"
        )

    llm = GatewayLLM.__new__(GatewayLLM)
    llm._client = NS(chat=NS(completions=NS(create=create)))
    llm._reasoning_effort, llm._allowed, llm._prices = "", [], {}
    await llm.chat(
        "m",
        [{"role": "assistant", "content": "x", "_anthropic_content": [{"type": "text"}]}],
        tools=[server_tool({"type": "web_search_20250305", "name": "web_search"})],
    )
    assert "tools" not in seen and "_anthropic_content" not in seen["messages"][0]
