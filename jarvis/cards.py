"""Converte resultados de ferramentas em cartões tipados. A interface só desenha.

Os números vêm prontos das ferramentas (somas feitas no banco); nada é calculado aqui
além de formatar o título.
"""

from datetime import date
from typing import Any


def _ddmm(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        return date.fromisoformat(str(iso)).strftime("%d/%m")
    except ValueError:
        return None


def _period(args: dict[str, Any]) -> str:
    de, ate = _ddmm(args.get("de")), _ddmm(args.get("ate"))
    if de and ate:
        return de if de == ate else f"{de} a {ate}"
    return de or ate or ""


def card_for(tool: str, args: dict[str, Any], data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    if data.get("erro"):
        return {
            "kind": "texto",
            "title": "Atenção",
            "text": data["erro"],
            "options": data.get("opcoes") or data.get("permitidos") or [],
        }

    if tool == "buscar_eventos":
        title = "Agenda" + (f" · {_period(args)}" if _period(args) else "")
        return {
            "kind": "agenda",
            "title": title,
            "items": data.get("eventos", []),
            "omitted": data.get("omitidos", 0),
        }
    if tool in ("criar_evento", "atualizar_evento") and data.get("evento"):
        verb = "Criado" if tool == "criar_evento" else "Atualizado"
        return {"kind": "agenda", "title": verb, "items": [data["evento"]], "omitted": 0}
    if tool == "buscar_gastos":
        title = "Gastos" + (f" · {_period(args)}" if _period(args) else "")
        return {
            "kind": "gastos",
            "title": title,
            "total": data.get("total"),
            "count": data.get("lancamentos", 0),
            "items": data.get("itens", []),
            "omitted": data.get("itens_omitidos", 0),
        }
    if tool == "total_fatura":
        return {
            "kind": "fatura",
            "title": f"Fatura {data.get('cartao', '')}".strip(),
            "total": data.get("total"),
            "due": data.get("vencimento"),
            "closing": data.get("fechamento"),
            "status": data.get("situacao"),
            "count": data.get("lancamentos", 0),
            "items": data.get("maiores_itens", []),
        }
    if tool == "resumo_gastos":
        return {
            "kind": "grafico",
            "title": f"Gastos · {data.get('periodo', '')}",
            "total": data.get("total"),
            "groupBy": args.get("agrupar_por"),
            "series": [
                {
                    "label": g["grupo"],
                    "value": g.get("total_centavos", 0),
                    "display": g["total"],
                    "count": g["lancamentos"],
                }
                for g in data.get("grupos", [])
            ],
        }
    if tool in (
        "lancar_gasto",
        "confirmar_pendente",
        "desfazer_ultimo",
        "gerenciar_meio_pagamento",
        "gerenciar_pessoa",
        "remover_evento",
    ):
        text = data.get("resumo") or data.get("pessoa") or data.get("status")
        title = {
            "gravado": "Gravado",
            "desfeito": "Desfeito",
            "cancelado": "Cancelado",
            "removido": "Removido",
        }.get(str(data.get("status")), "Feito")
        return {"kind": "texto", "title": title, "text": str(text or "")}
    if tool in ("abrir_terminal", "mandar_terminal", "fechar_terminal"):
        n, pasta = data.get("numero"), data.get("pasta", "")
        text = {
            "aberto": f"Terminal {n} · {pasta} aberto no painel.",
            "enviado": (
                f"{'Comando no' if data.get('tipo') == 'comando' else 'Mensagem para o'} "
                f"Terminal {n} ({pasta}): {data.get('texto', '')}"
            ),
            "fechado": f"Terminal {n} · {pasta} fechado.",
            "cancelado": f"Nada feito no Terminal {n}.",
        }.get(str(data.get("status")))
        return {"kind": "texto", "title": "Terminais", "text": text} if text else None
    if tool == "listar_terminais":
        return {"kind": "terminais", "title": "Terminais", "items": data.get("terminais", [])}
    if tool == "buscar_arquivo":
        return {
            "kind": "arquivos",
            "title": f"Arquivos · {args.get('texto', '')}",
            "items": data.get("arquivos", []),
            "total": data.get("total", 0),
        }
    return None
