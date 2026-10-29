"""Conselho de compra: projeção mensal e veredito. Nunca delegar ao LLM (o modelo só explica).

Para cada mês que a compra atinge (no crédito, o mês de vencimento de cada parcela; à vista, o
mês corrente): sobra = renda − contas fixas − parcelas já comprometidas − média dos gastos
avulsos dos 3 meses completos anteriores − a parcela nova. Veredito: `segura` se toda sobra é
pelo menos `folga_pct`% da renda; `arriscada` se alguma é negativa; senão `atencao`.
"""

import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.domain.billing import _add_months, split_installments

Verdict = Literal["segura", "atencao", "arriscada"]
HISTORY_MONTHS = 3


@dataclass(frozen=True)
class PastExpense:
    spent_on: date
    amount_cents: int
    description: str
    installment_total: int
    statement_month: date | None


@dataclass(frozen=True)
class Month:
    month: date  # dia 1
    income: int
    fixed: int
    committed: int  # parcelas de compras anteriores com vencimento neste mês
    average: int  # média mensal dos gastos avulsos
    new_installment: int

    @property
    def leftover(self) -> int:
        return self.income - self.fixed - self.committed - self.average - self.new_installment


@dataclass(frozen=True)
class Advice:
    months: list[Month]
    verdict: Verdict
    decisive: Month
    history_months: int


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def purchase_months(
    amount_cents: int,
    installments: int,
    today: date,
    closing_day: int | None = None,
    due_day: int | None = None,
) -> list[tuple[date, int]]:
    """(mês, valor) de cada parcela. Crédito: regra da fatura. Sem cartão e parcelado: a partir
    do mês que vem. À vista: o mês corrente."""
    if closing_day is not None and due_day is not None:
        parts = split_installments(amount_cents, installments, today, closing_day, due_day)
        return [(p.statement_month, p.amount_cents) for p in parts if p.statement_month]
    this_month = today.replace(day=1)
    if installments == 1:
        return [(this_month, amount_cents)]
    base, remainder = divmod(amount_cents, installments)
    return [
        (_add_months(this_month, i + 1), base + (remainder if i == 0 else 0))
        for i in range(installments)
    ]


def average_variable(
    expenses: list[PastExpense], fixed_names: list[str], today: date
) -> tuple[int, int]:
    """(média mensal em centavos, meses usados). Avulsos (1 parcela) dos 3 meses completos antes
    do mês corrente, sem os que citam uma conta fixa; menos histórico: divide pelos meses que há."""
    start = _add_months(today.replace(day=1), -HISTORY_MONTHS)
    end = today.replace(day=1)
    names = [_plain(n) for n in fixed_names if n.strip()]
    first = min((e.spent_on for e in expenses), default=None)
    if first is None or first >= end:
        return 0, 0
    months_used = sum(
        1
        for i in range(HISTORY_MONTHS)
        if _add_months(start, i + 1) > first  # o mês tem algum dia depois do 1º gasto
    )
    total = sum(
        e.amount_cents
        for e in expenses
        if e.installment_total == 1
        and start <= e.spent_on < end
        and not any(n in _plain(e.description) for n in names)
    )
    return (total // months_used if months_used else 0), months_used


def committed_by_month(expenses: list[PastExpense]) -> dict[date, int]:
    out: dict[date, int] = {}
    for e in expenses:
        if e.installment_total > 1 and e.statement_month is not None:
            out[e.statement_month] = out.get(e.statement_month, 0) + e.amount_cents
    return out


def advise(
    *,
    purchase: list[tuple[date, int]],
    income: int,
    fixed: int,
    fixed_names: list[str],
    expenses: list[PastExpense],
    today: date,
    folga_pct: int,
) -> Advice:
    average, history = average_variable(expenses, fixed_names, today)
    committed = committed_by_month(expenses)
    months = [
        Month(
            month=m,
            income=income,
            fixed=fixed,
            committed=committed.get(m, 0),
            average=average,
            new_installment=cents,
        )
        for m, cents in purchase
    ]
    decisive = min(months, key=lambda m: (m.leftover, m.month))
    if decisive.leftover < 0:
        verdict: Verdict = "arriscada"
    elif all(m.leftover * 100 >= m.income * folga_pct for m in months):
        verdict = "segura"
    else:
        verdict = "atencao"
    return Advice(months=months, verdict=verdict, decisive=decisive, history_months=history)


def leftover_pct(m: Month) -> int:
    """Sobra em % da renda, arredondada para baixo (só para exibir)."""
    return (m.leftover * 100) // m.income if m.income else 0
