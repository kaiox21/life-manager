"""Regra da fatura e das parcelas. Nunca delegar ao LLM.

Uma compra no crédito feita antes do fechamento do mês entra na fatura que fecha
nesse mês; no dia do fechamento ou depois, na que fecha no mês seguinte. A fatura
vence no mesmo mês do fechamento se due_day > closing_day; senão, no mês seguinte.
Dias além do fim do mês (ex.: closing_day=31 em fevereiro) viram o último dia.
"""

import calendar
from dataclasses import dataclass
from datetime import date


def _add_months(d: date, months: int) -> date:
    """Primeiro dia do mês `months` depois do mês de `d`."""
    index = d.year * 12 + (d.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def _clamp_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def closing_date(month_start: date, closing_day: int) -> date:
    return _clamp_day(month_start.year, month_start.month, closing_day)


def due_date(statement_month: date, due_day: int) -> date:
    return _clamp_day(statement_month.year, statement_month.month, due_day)


def statement_month_for(spent_on: date, closing_day: int, due_day: int) -> date:
    """Dia 1 do mês em que vence a fatura onde a compra entra."""
    _validate_days(closing_day, due_day)
    this_month = spent_on.replace(day=1)
    if spent_on < closing_date(this_month, closing_day):
        closes_in = this_month
    else:
        closes_in = _add_months(this_month, 1)
    return closes_in if due_day > closing_day else _add_months(closes_in, 1)


def open_statement_month(today: date, closing_day: int, due_day: int) -> date:
    """Fatura ainda aberta hoje: a mesma em que uma compra feita hoje entraria."""
    return statement_month_for(today, closing_day, due_day)


@dataclass(frozen=True, slots=True)
class Installment:
    number: int
    total: int
    amount_cents: int
    statement_month: date | None


def split_installments(
    amount_cents: int,
    installments: int,
    spent_on: date,
    closing_day: int | None = None,
    due_day: int | None = None,
) -> list[Installment]:
    """Divide a compra em parcelas inteiras; a sobra dos centavos vai para a 1ª.

    Sem closing_day/due_day (débito, pix...), statement_month fica None.
    """
    if amount_cents <= 0:
        raise ValueError("amount_cents precisa ser positivo")
    if installments < 1:
        raise ValueError("installments precisa ser >= 1")
    if installments > amount_cents:
        raise ValueError("parcelas demais para o valor")
    if (closing_day is None) != (due_day is None):
        raise ValueError("closing_day e due_day vêm juntos")
    if installments > 1 and closing_day is None:
        raise ValueError("parcelamento só no crédito")

    base, remainder = divmod(amount_cents, installments)
    first_month = (
        statement_month_for(spent_on, closing_day, due_day)
        if closing_day is not None and due_day is not None
        else None
    )
    return [
        Installment(
            number=i + 1,
            total=installments,
            amount_cents=base + (remainder if i == 0 else 0),
            statement_month=_add_months(first_month, i) if first_month else None,
        )
        for i in range(installments)
    ]


def _validate_days(closing_day: int, due_day: int) -> None:
    for name, day in (("closing_day", closing_day), ("due_day", due_day)):
        if not 1 <= day <= 31:
            raise ValueError(f"{name} precisa estar entre 1 e 31")
