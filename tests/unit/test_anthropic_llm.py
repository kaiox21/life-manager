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
    def __init__(self, pieces, final):
        self.pieces, self.final = pieces, final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    @property
    async def text_stream(self):
        for p in self.pieces:
            yield p

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
