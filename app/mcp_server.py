"""Ferramentas do núcleo expostas por MCP (Streamable HTTP), para o Jarvis e o Claude.

As funções são as mesmas do agente do WhatsApp (app/agent/tools): mesmos nomes, mesma
validação Pydantic, mesmas confirmações. Nada de regra de negócio aqui.
"""

import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError as McpToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field, ValidationError
from pydantic_core import to_jsonable_python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.service import build_prompt
from app.agent.tools import ALL_TOOLS, Tool, ToolContext, ToolError
from app.agent.tools.painel import painel as panel_data
from app.clock import Clock
from app.db.models import AgentRun

log = logging.getLogger(__name__)

INSTRUCTIONS = (
    "Agenda e gastos pessoais do Kaio. Chame `contexto` primeiro para saber a data de hoje, "
    "os meios de pagamento, as faturas abertas, as categorias e as pessoas; copie datas de lá "
    "em vez de calcular. Valores em centavos (R$ 47,90 -> 4790). Ações que pedem confirmação "
    "devolvem status 'aguardando_confirmacao': mostre o resumo ao usuário e só depois chame "
    "confirmar_pendente."
)

AfterWrite = Callable[[], Awaitable[None]]


def _signature(tool: Tool) -> inspect.Signature:
    """Assinatura com os campos do modelo Pydantic, para o MCP montar o mesmo schema."""
    params = []
    for name, field in tool.args_model.model_fields.items():
        annotation: Any = field.annotation
        if field.description:
            annotation = Annotated[annotation, Field(description=field.description)]
        default = inspect.Parameter.empty if field.is_required() else field.get_default()
        params.append(
            inspect.Parameter(
                name, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=annotation
            )
        )
    return inspect.Signature(params, return_annotation=str)


Sessions = Callable[[], async_sessionmaker[AsyncSession]]


def _wrap(
    tool: Tool,
    get_sessions: Sessions,
    clock: Clock,
    after_write: AfterWrite | None,
) -> Callable[..., Awaitable[str]]:
    async def call(**raw: Any) -> str:
        sessions = get_sessions()
        # O SDK já converteu datas etc. em objetos Python: guardar em forma serializável (JSONB).
        entry: dict[str, Any] = {"name": tool.name, "model": "mcp", "args": to_jsonable_python(raw)}
        try:
            args = tool.args_model.model_validate(raw)
        except ValidationError as exc:
            errors = [f"{'.'.join(map(str, e['loc'])) or 'args'}: {e['msg']}" for e in exc.errors()]
            entry.update(ok=False, error="; ".join(errors))
            await _log_run(sessions, entry)
            # ToolError do SDK: a mensagem chega ao cliente (exceção genérica seria escondida).
            raise McpToolError("argumentos inválidos: " + "; ".join(errors)) from None
        async with sessions.begin() as session:
            ctx = ToolContext(session=session, clock=clock, source="texto")
            try:
                async with session.begin_nested():
                    result = await tool.fn(ctx, args)
            except ToolError as exc:
                result = exc.payload  # erro de domínio: o cliente repassa ao usuário
            entry.update(ok=True, result=to_jsonable_python(result))
            session.add(
                AgentRun(
                    channel="desktop", intent=tool.groups[0], model="mcp", tools_called=[entry]
                )
            )
        if after_write is not None:
            await after_write()
        return json.dumps(result, ensure_ascii=False, default=str)

    call.__name__ = tool.name
    call.__doc__ = tool.description
    call.__signature__ = _signature(tool)  # type: ignore[attr-defined]
    return call


async def _log_run(sessions: async_sessionmaker[AsyncSession], entry: dict[str, Any]) -> None:
    async with sessions.begin() as session:
        session.add(
            AgentRun(channel="desktop", model="mcp", tools_called=[entry], error=entry.get("error"))
        )


def build_mcp(
    *,
    get_sessions: Sessions,
    clock: Clock,
    after_write: AfterWrite | None = None,
) -> MCPServer:
    server = MCPServer("life-manager", instructions=INSTRUCTIONS)
    for tool in ALL_TOOLS.values():
        server.add_tool(
            _wrap(tool, get_sessions, clock, after_write),
            name=tool.name,
            description=tool.description,
        )

    async def contexto() -> str:
        """Data e hora atuais, tabela de datas, meios de pagamento e faturas abertas,
        categorias, pessoas e agenda dos próximos 7 dias. Chame antes das outras ferramentas."""
        async with get_sessions()() as session:
            return await build_prompt(
                ToolContext(session=session, clock=clock), None, data_only=True
            )

    server.add_tool(contexto, name="contexto")

    async def painel() -> str:
        """Dados do painel do Jarvis, já calculados: agenda de hoje e dos próximos 7 dias,
        gastos do mês por categoria, fatura aberta de cada cartão e últimos registros.
        Só leitura; não registra em agent_runs."""
        async with get_sessions()() as session:
            data = await panel_data(ToolContext(session=session, clock=clock))
        return json.dumps(data, ensure_ascii=False, default=str)

    server.add_tool(painel, name="painel")
    return server


def mcp_http_app(server: MCPServer, allowed_hosts: list[str]) -> Any:
    """App ASGI do transporte Streamable HTTP, para montar em /mcp no FastAPI."""
    return server.streamable_http_app(
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(allowed_hosts=allowed_hosts),
    )
