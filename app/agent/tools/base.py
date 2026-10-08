"""Infra comum das ferramentas: contexto, registro e erros de domínio."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock

Group = Literal["gasto", "consulta_gasto", "agenda", "pessoa", "confirmacao"]
Source = Literal["texto", "audio", "foto"]


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass
class ToolContext:
    session: AsyncSession
    clock: Clock
    source: Source = "texto"
    message_id: uuid.UUID | None = None


class ToolError(Exception):
    """Erro de domínio que o modelo deve repassar ao usuário (ex.: meio ambíguo).

    Não conta como falha de validação: volta como resultado normal da ferramenta.
    """

    def __init__(self, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.payload = {"erro": message, **extra}


ToolFn = Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Tool:
    name: str
    group: Group
    description: str
    args_model: type[ToolArgs]
    fn: ToolFn = field(repr=False)

    def openai_schema(self) -> dict[str, Any]:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": schema},
        }


def brl(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    reais, centavos = divmod(abs(cents), 100)
    return f"{sign}R$ {reais:,}".replace(",", ".") + f",{centavos:02d}"


def br_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")
