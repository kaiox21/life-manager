"""Registro das ferramentas. O LLM só toca o banco por aqui."""

from app.agent.tools import confirmacao, consultas, gastos
from app.agent.tools.base import Group, Tool, ToolContext, ToolError

ALL_TOOLS: dict[str, Tool] = {
    t.name: t for t in (*gastos.TOOLS, *consultas.TOOLS, *confirmacao.TOOLS)
}


def tools_for(group: Group) -> list[Tool]:
    return [t for t in ALL_TOOLS.values() if t.group == group]


__all__ = ["ALL_TOOLS", "Group", "Tool", "ToolContext", "ToolError", "tools_for"]
