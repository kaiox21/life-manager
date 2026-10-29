"""Regras da fatura importada em PDF. Nunca delegar ao LLM: o modelo só transcreve.

- `parse_brl`: valor impresso ("R$ 1.234,56", "-45,90", "45,90-") em centavos.
- `item_date`: data impressa sem ano ganha o ano pelo vencimento.
- `check_sum`: saldo anterior − pagamentos + compras + encargos − estornos = total impresso.
- `match_items`: casa os itens com os gastos já lançados do mesmo cartão.
- `plan_new_expenses`: o que falta lançar, com as parcelas k a N de cada compra parcelada.
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from typing import Literal

from app.domain.billing import _add_months

ItemKind = Literal["compra", "estorno", "encargo", "pagamento"]
MATCH_WINDOW_DAYS = 3
SUMMARY_MAX_LINES = 15

_BRL = re.compile(
    r"^(?P<lead>-)?\s*(?:R\$)?\s*(?P<num>\d{1,3}(?:\.\d{3})*|\d+)(?:,(?P<dec>\d{2}))?\s*(?P<trail>-)?$"
)


class StatementError(ValueError):
    """Transcrição que o código não aceita (valor ou data ilegível)."""


def parse_brl(text: str) -> int:
    """Centavos com sinal. Aceita "R$ 1.234,56", "1234,56", "-R$ 45,90", "45,90-", "R$ 10"."""
    raw = text.strip().replace(" ", " ").replace("−", "-")
    raw = re.sub(r"^-\s*R\$", "-", raw)
    m = _BRL.match(raw)
    if not m:
        raise StatementError(f"valor ilegível: {text!r}")
    cents = int(m["num"].replace(".", "")) * 100 + int(m["dec"] or 0)
    return -cents if (m["lead"] or m["trail"]) else cents


def item_date(printed: str, due: date) -> date:
    """ "16/10" ou "16/10/2026". Sem ano: o do vencimento, ou o anterior se cairia depois dele."""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", printed.strip())
    if not m:
        raise StatementError(f"data ilegível: {printed!r}")
    day, month = int(m[1]), int(m[2])
    try:
        if m[3]:
            return date(int(m[3]), month, day)
        candidate = date(due.year, month, day)
        return candidate if candidate <= due else date(due.year - 1, month, day)
    except ValueError as exc:
        raise StatementError(f"data inválida: {printed!r}") from exc


@dataclass(frozen=True)
class Item:
    """Item da fatura já em centavos (sempre positivo; o sinal vem do tipo)."""

    on: date
    description: str
    amount_cents: int
    kind: ItemKind
    installment: tuple[int, int] | None = None  # (k, N)
    category: str | None = None

    @property
    def signed_cents(self) -> int:
        """Efeito no total da fatura (pagamento e estorno descontam)."""
        return -self.amount_cents if self.kind in ("estorno", "pagamento") else self.amount_cents

    @property
    def expense_cents(self) -> int:
        """Valor do gasto que o item vira: estorno é gasto negativo."""
        return -self.amount_cents if self.kind == "estorno" else self.amount_cents

    @property
    def number(self) -> int:
        return self.installment[0] if self.installment else 1

    @property
    def total(self) -> int:
        return self.installment[1] if self.installment else 1


def parse_installment(text: str | None) -> tuple[int, int] | None:
    if not text:
        return None
    m = re.fullmatch(r"\s*(\d{1,2})\s*/\s*(\d{1,2})\s*", text)
    if not m:
        raise StatementError(f"parcela ilegível: {text!r}")
    k, n = int(m[1]), int(m[2])
    if not 1 <= k <= n or n > 99:
        raise StatementError(f"parcela inválida: {text!r}")
    return None if n == 1 else (k, n)


@dataclass(frozen=True)
class SumCheck:
    computed_cents: int
    printed_cents: int

    @property
    def difference_cents(self) -> int:
        return self.computed_cents - self.printed_cents

    @property
    def ok(self) -> bool:
        return self.difference_cents == 0


def check_sum(
    items: list[Item], printed_total: int, previous_balance: int = 0, payments: int | None = None
) -> SumCheck:
    """`payments` impresso no resumo vale no lugar dos itens de pagamento (não conta duas vezes)."""
    paid = (
        payments
        if payments is not None
        else sum(i.amount_cents for i in items if i.kind == "pagamento")
    )
    charges = sum(i.signed_cents for i in items if i.kind != "pagamento")
    return SumCheck(previous_balance - abs(paid) + charges, printed_total)


@dataclass(frozen=True)
class Existing:
    """Gasto ativo do mesmo cartão, candidato a par de um item."""

    id: uuid.UUID
    amount_cents: int
    spent_on: date
    description: str
    installment_no: int
    installment_total: int
    statement_month: date | None
    purchase_group: uuid.UUID | None = None


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).lower().split())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _plain(a), _plain(b)).ratio()


def _same_amount(item: Item, e: Existing) -> bool:
    # Parcela lançada à mão pode diferir 1 centavo da do banco (onde fica a sobra do rateio).
    tolerance = 1 if item.total > 1 else 0
    return abs(e.amount_cents - item.expense_cents) <= tolerance


@dataclass
class Matching:
    pairs: list[tuple[Item, Existing]] = field(default_factory=list)
    new: list[Item] = field(default_factory=list)
    outside: list[Existing] = field(default_factory=list)  # lançados no ciclo, fora da fatura
    ignored: list[Item] = field(default_factory=list)  # pagamentos: não viram gasto


def match_items(items: list[Item], existing: list[Existing], cycle: date) -> Matching:
    """Cada item casa com no máximo um gasto: mesmo valor da parcela, mesma parcela e data a
    até 3 dias; empate: data mais próxima, depois descrição mais parecida. Guloso por data."""
    result = Matching()
    used: set[uuid.UUID] = set()
    for item in sorted(items, key=lambda i: (i.on, i.description)):
        if item.kind == "pagamento":
            result.ignored.append(item)
            continue
        candidates = [
            e
            for e in existing
            if e.id not in used
            and e.installment_no == item.number
            and e.installment_total == item.total
            and _same_amount(item, e)
            and abs((e.spent_on - item.on).days) <= MATCH_WINDOW_DAYS
        ]
        if not candidates:
            result.new.append(item)
            continue
        best = min(
            candidates,
            key=lambda e: (
                abs((e.spent_on - item.on).days),
                -similarity(e.description, item.description),
            ),
        )
        used.add(best.id)
        result.pairs.append((item, best))
    result.outside = [e for e in existing if e.id not in used and e.statement_month == cycle]
    return result


@dataclass(frozen=True)
class NewExpense:
    amount_cents: int
    description: str
    category: str | None
    spent_on: date
    statement_month: date
    installment_no: int
    installment_total: int
    group: int  # mesma compra = mesmo número (vira um purchase_group na gravação)


def plan_new_expenses(new_items: list[Item], cycle: date) -> list[NewExpense]:
    """Item "k/N" gera as parcelas k a N, uma por mês a partir do ciclo da fatura; as anteriores
    a k ficaram em faturas passadas. O valor de cada parcela é o impresso (o banco já dividiu)."""
    plan: list[NewExpense] = []
    for group, item in enumerate(new_items):
        for offset, number in enumerate(range(item.number, item.total + 1)):
            plan.append(
                NewExpense(
                    amount_cents=item.expense_cents,
                    description=item.description,
                    category=item.category,
                    spent_on=item.on,
                    statement_month=_add_months(cycle, offset),
                    installment_no=number,
                    installment_total=item.total,
                    group=group,
                )
            )
    return plan


def brl(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    reais, centavos = divmod(abs(cents), 100)
    return f"{sign}R$ {reais:,}".replace(",", ".") + f",{centavos:02d}"


def sum_warning(check: SumCheck) -> str | None:
    if check.ok:
        return None
    side = "a menos" if check.difference_cents < 0 else "a mais"
    return (
        f"Atenção: os itens somam {brl(abs(check.difference_cents))} {side} que o total da "
        "fatura. Confira no app do banco antes de confirmar."
    )


def summary_text(
    *,
    card: str,
    due: date,
    items_count: int,
    printed_total: int,
    check: SumCheck,
    matching: Matching,
    imported_before: date | None = None,
) -> str:
    """Resumo fixo da importação (sem LLM), com a pergunta no fim quando há o que lançar."""
    lines: list[str] = []
    if warning := sum_warning(check):
        lines.append(warning)
    lines.append(
        f"Fatura do {card} (vence {due:%d/%m/%Y}): {items_count} itens, total {brl(printed_total)}."
    )
    if check.ok:
        lines.append("A soma confere com o total da fatura.")
    if imported_before and not matching.new:
        lines.append(f"Já importada em {imported_before:%d/%m}; nada novo para lançar.")
    elif imported_before:
        lines.append(f"Já importada em {imported_before:%d/%m}.")
    lines.append(f"{len(matching.pairs)} já estavam lançados.")
    if matching.new:
        total_new = sum(i.expense_cents for i in matching.new)
        lines.append(f"{len(matching.new)} novos, {brl(total_new)}:")
        for item in matching.new[:SUMMARY_MAX_LINES]:
            parcel = f" ({item.number}/{item.total})" if item.installment else ""
            future = item.total - item.number
            tail = (
                f" (+{future} parcela{'s' if future > 1 else ''} futura{'s' if future > 1 else ''})"
                if future
                else ""
            )
            lines.append(
                f"- {item.on:%d/%m} {item.description}{parcel}: {brl(item.expense_cents)}{tail}"
            )
        if len(matching.new) > SUMMARY_MAX_LINES:
            lines.append(f"- +{len(matching.new) - SUMMARY_MAX_LINES} itens")
    elif not imported_before:
        lines.append("Nada novo para lançar.")
    if matching.outside:
        shown = ", ".join(
            f"{e.spent_on:%d/%m} {e.description} {brl(e.amount_cents)}"
            for e in matching.outside[:5]
        )
        more = f" e +{len(matching.outside) - 5}" if len(matching.outside) > 5 else ""
        lines.append(f"Lançados por você e fora da fatura: {shown}{more}.")
    if matching.new:
        lines.append(
            f"Lanço os {len(matching.new)}? (sim/não)"
            if len(matching.new) > 1
            else "Lanço? (sim/não)"
        )
    return "\n".join(lines)
