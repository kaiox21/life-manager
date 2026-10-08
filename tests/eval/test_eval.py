"""A prova: classificador + agente contra o modelo real (marcador eval).

Uso:  docker compose --profile test up -d postgres-test
      MODEL_PRIMARY=openai/gpt-5-nano uv run pytest -m eval -q
Compara só a PRIMEIRA chamada de ferramenta válida (a que seria executada), seguindo o
cabeçalho de casos.yaml. Na fase 2 os casos de agenda só avaliam o classificador.
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.agent.intent import classify
from app.agent.llm import GatewayLLM
from app.agent.loop import run_agent
from app.agent.service import build_prompt
from app.agent.tools import ALL_TOOLS, ToolContext
from app.agent.tools.resolve import match_payment_methods, normalize
from app.clock import TZ, fixed_clock
from app.config import get_settings, provider_list
from app.db.base import Base
from app.db.models import PaymentMethod, PendingAction
from app.db.seed import seed_categories, seed_payment_methods

pytestmark = pytest.mark.eval

CASES_FILE = Path(__file__).parent / "casos.yaml"
DEFAULT_TODAY = "2026-10-07"
AGENT_SKIPPED_INTENTS = {"agenda", "pessoa"}  # ferramentas chegam na fase 3
REPORT_DIR = Path("data/eval")


def _iso(value: Any) -> Any:
    """PyYAML lê datas sem aspas como date/datetime: normaliza tudo para string ISO."""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _iso(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_iso(v) for v in value]
    return value


DATA = _iso(yaml.safe_load(CASES_FILE.read_text()))
CASES = DATA["casos"]


@dataclass
class Result:
    id: str
    group: str
    intent_ok: bool
    agent_ok: bool | None  # None = agente não avaliado nesta fase
    got_intent: str
    got: str
    detail: str = ""
    cost: Decimal = Decimal(0)
    escalated: bool = False


@dataclass
class Board:
    results: list[Result] = field(default_factory=list)


BOARD = Board()


@pytest.fixture(scope="module")
def llm() -> GatewayLLM:
    s = get_settings()
    if not s.ai_gateway_api_key.get_secret_value() or not s.model_primary:
        pytest.skip("defina AI_GATEWAY_API_KEY e MODEL_PRIMARY para rodar a prova")
    return GatewayLLM(
        api_key=s.ai_gateway_api_key.get_secret_value(),
        base_url=s.ai_gateway_base_url,
        allowed_providers=provider_list(s.allowed_providers),
        reasoning_effort=s.reasoning_effort,
    )


@pytest.fixture(scope="module", autouse=True)
def scoreboard():
    yield
    _print_board()


@pytest.fixture
async def eval_sessions(migrated_db: str):
    engine = create_async_engine(migrated_db, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text(f"truncate {', '.join(Base.metadata.tables)} cascade"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _setup(session: AsyncSession, case: dict[str, Any], now: datetime) -> None:
    fx = DATA["fixtures"]
    await seed_categories(session, fx["categorias"])
    await seed_payment_methods(session, fx["meios_pagamento"])
    if pend := case.get("pendente"):
        session.add(
            PendingAction(
                tool_name=pend["tool_name"],
                args=pend.get("args") or {},
                summary=pend["summary"],
                expires_at=now + timedelta(minutes=30),
            )
        )
    await session.flush()


def _norm(v: Any) -> Any:
    return normalize(v) if isinstance(v, str) else v


async def _resolved_method(session: AsyncSession, raw: str, tool: str) -> str:
    methods = list((await session.scalars(select(PaymentMethod))).all())
    if tool == "total_fatura":
        methods = [m for m in methods if m.kind == "credito"]
    found = match_payment_methods(methods, raw)
    return found[0].name if len(found) == 1 else f"<{raw}: {len(found)} opções>"


async def _check_call(session, case, name: str, args: dict[str, Any]) -> tuple[bool, str]:
    espera = case["espera"]
    if name != espera["tool"]:
        return False, f"chamou {name}, esperado {espera['tool']}"
    for key, want in (espera.get("args") or {}).items():
        got = args.get(key)
        if key == "payment_method" and isinstance(got, str):
            got = await _resolved_method(session, got, name)
        if _norm(got) != _norm(want):
            return False, f"{key}={got!r}, esperado {want!r}"
    for key, piece in (espera.get("contem") or {}).items():
        if key == "texto":
            haystack = f"{args.get('description') or ''} {args.get('merchant') or ''}"
        else:
            haystack = str(args.get(key) or "")
        if normalize(str(piece)) not in normalize(haystack):
            return False, f"{key} sem {piece!r} (veio {haystack!r})"
    return True, ""


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_caso(case: dict[str, Any], llm: GatewayLLM, eval_sessions) -> None:
    s = get_settings()
    hoje = date.fromisoformat(case.get("hoje") or DEFAULT_TODAY)
    now = datetime(hoje.year, hoje.month, hoje.day, 12, 0, tzinfo=TZ)
    history = [{"role": h["role"], "content": h["content"]} for h in case.get("historico") or []]
    pending_summary = (case.get("pendente") or {}).get("summary")

    async with eval_sessions() as session:
        async with session.begin():
            await _setup(session, case, now)
        ctx = ToolContext(session=session, clock=fixed_clock(now))
        async with session.begin():
            cls = await classify(
                llm, s.model_classifier or s.model_primary, case["msg"], history, pending_summary
            )
            result = Result(
                id=case["id"],
                group=case["intent"],
                intent_ok=cls.intent == case["intent"],
                agent_ok=None,
                got_intent=cls.intent,
                got="—",
                cost=cls.cost_usd,
            )
            if case["intent"] not in AGENT_SKIPPED_INTENTS:
                out = await run_agent(
                    llm=llm,
                    ctx=ctx,
                    intent=cls.intent,
                    system_prompt=await build_prompt(ctx, pending_summary),
                    history=history,
                    text=case["msg"],
                    primary_model=s.model_primary,
                    escalation_model=s.model_escalation or s.model_primary,
                    stop_at_first_tool=True,
                )
                result.cost += out.cost_usd
                result.escalated = out.escalated
                result.agent_ok, result.got, result.detail = await _judge(session, case, out)
            await session.rollback()
    BOARD.results.append(result)

    problems = []
    if not result.intent_ok:
        problems.append(f"intenção {cls.intent!r} (raw {cls.raw!r}), esperado {case['intent']!r}")
    if result.agent_ok is False:
        problems.append(result.detail)
    assert not problems, " | ".join(problems)


async def _judge(session, case, out) -> tuple[bool, str, str]:
    espera = case["espera"]
    first = out.first_call
    got = (
        f"{first.name}({json.dumps(first.args, ensure_ascii=False)})"
        if first
        else (f"texto: {out.reply[:80]!r}")
    )
    if first and first.name in (case.get("proibido") or []):
        return False, got, f"chamou ferramenta proibida {first.name}"
    if espera == "pergunta":
        if first:
            return False, got, "devia perguntar, chamou ferramenta"
        return (out.asked_question, got, "" if out.asked_question else "não fez pergunta")
    if espera == "sem_ferramenta":
        return (first is None, got, "" if first is None else "chamou ferramenta")
    if not first:
        return False, got, f"não chamou {espera['tool']}"
    validated = ALL_TOOLS[first.name].args_model.model_validate(first.args).model_dump(mode="json")
    ok, why = await _check_call(session, case, first.name, validated)
    return ok, got, why


def _print_board() -> None:
    results = BOARD.results
    if not results:
        return
    s = get_settings()
    by_group: dict[str, list[Result]] = defaultdict(list)
    for r in results:
        by_group[r.group].append(r)
    lines = [
        "",
        f"PROVA — classificador={s.model_classifier or s.model_primary} "
        f"principal={s.model_primary} escalada={s.model_escalation or s.model_primary}",
        f"{'grupo':16} {'intenção':>10} {'agente':>10}",
    ]
    for group, rs in sorted(by_group.items()):
        agent = [r for r in rs if r.agent_ok is not None]
        agent_txt = f"{sum(r.agent_ok for r in agent)}/{len(agent)}" if agent else "—"
        lines.append(f"{group:16} {sum(r.intent_ok for r in rs):>4}/{len(rs):<5} {agent_txt:>10}")
    agent_all = [r for r in results if r.agent_ok is not None]
    agent_hits = sum(r.agent_ok for r in agent_all)
    pct = 100 * agent_hits / len(agent_all) if agent_all else 0
    cost = sum((r.cost for r in results), Decimal(0))
    lines += [
        f"{'TOTAL':16} {sum(r.intent_ok for r in results):>4}/{len(results):<5} "
        f"{agent_hits:>4}/{len(agent_all)} ({pct:.0f}%)",
        f"escaladas: {sum(r.escalated for r in results)}   custo: US$ {cost:.4f}   "
        f"por caso: US$ {cost / len(results):.5f}",
        "falhas: "
        + (
            ", ".join(
                f"{r.id}[{r.detail or 'intenção ' + r.got_intent}]"
                for r in results
                if not r.intent_ok or r.agent_ok is False
            )
            or "nenhuma"
        ),
    ]
    report = "\n".join(lines)
    print(report)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(TZ).strftime("%Y%m%d-%H%M%S")
    name = (s.model_primary or "modelo").replace("/", "_")
    (REPORT_DIR / f"{stamp}-{name}.txt").write_text(
        report
        + "\n"
        + "\n".join(
            f"{r.id}\t{r.group}\tintent={r.got_intent}\tok={r.agent_ok}\t{r.got}\t{r.detail}"
            for r in results
        )
        + "\n"
    )
