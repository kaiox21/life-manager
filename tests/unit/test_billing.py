from datetime import date

import pytest

from app.domain.billing import (
    due_date,
    open_statement_month,
    split_installments,
    statement_month_for,
)

NUBANK = (31, 8)  # fecha no último dia do mês, vence dia 8
MESMO_MES = (10, 17)  # fecha dia 10, vence dia 17 (mesmo mês)
ITAU = (25, 5)


@pytest.mark.parametrize(
    ("spent_on", "card", "expected"),
    [
        # Nubank: fechamento no último dia do mês
        (date(2026, 10, 15), NUBANK, date(2026, 11, 1)),
        (date(2026, 10, 30), NUBANK, date(2026, 11, 1)),
        (date(2026, 10, 31), NUBANK, date(2026, 12, 1)),  # no dia do fechamento: próxima
        (date(2026, 11, 29), NUBANK, date(2026, 12, 1)),
        (date(2026, 11, 30), NUBANK, date(2027, 1, 1)),  # mês de 30 dias + virada de ano
        (date(2026, 12, 15), NUBANK, date(2027, 1, 1)),  # virada de ano
        (date(2026, 12, 31), NUBANK, date(2027, 2, 1)),
        (date(2027, 2, 27), NUBANK, date(2027, 3, 1)),
        (date(2027, 2, 28), NUBANK, date(2027, 4, 1)),  # fevereiro fecha dia 28
        (date(2028, 2, 28), NUBANK, date(2028, 3, 1)),  # bissexto fecha dia 29
        (date(2028, 2, 29), NUBANK, date(2028, 4, 1)),
        # Vence no mesmo mês do fechamento
        (date(2026, 10, 1), MESMO_MES, date(2026, 10, 1)),
        (date(2026, 10, 9), MESMO_MES, date(2026, 10, 1)),
        (date(2026, 10, 10), MESMO_MES, date(2026, 11, 1)),
        (date(2026, 12, 20), MESMO_MES, date(2027, 1, 1)),  # virada de ano
        # Itaú (exemplo da prova): fecha 25, vence 5 do mês seguinte
        (date(2026, 10, 7), ITAU, date(2026, 11, 1)),
        (date(2026, 10, 25), ITAU, date(2026, 12, 1)),
        (date(2026, 12, 26), ITAU, date(2027, 2, 1)),  # virada de ano
    ],
)
def test_statement_month(spent_on, card, expected):
    assert statement_month_for(spent_on, *card) == expected


def test_fatura_aberta_hoje():
    hoje = date(2026, 10, 7)
    assert open_statement_month(hoje, *NUBANK) == date(2026, 11, 1)
    assert open_statement_month(hoje, *MESMO_MES) == date(2026, 10, 1)
    assert open_statement_month(hoje, *ITAU) == date(2026, 11, 1)


def test_due_date_ajusta_fim_do_mes():
    assert due_date(date(2027, 2, 1), 31) == date(2027, 2, 28)
    assert due_date(date(2026, 11, 1), 8) == date(2026, 11, 8)


def test_parcelas_avancam_um_mes_e_viram_o_ano():
    parts = split_installments(60000, 3, date(2026, 10, 15), *MESMO_MES)
    assert [(p.number, p.total, p.amount_cents, p.statement_month) for p in parts] == [
        (1, 3, 20000, date(2026, 11, 1)),
        (2, 3, 20000, date(2026, 12, 1)),
        (3, 3, 20000, date(2027, 1, 1)),
    ]


def test_sobra_dos_centavos_vai_para_a_primeira():
    parts = split_installments(10000, 3, date(2026, 10, 15), *NUBANK)
    assert [p.amount_cents for p in parts] == [3334, 3333, 3333]


@pytest.mark.parametrize("amount", [12, 99, 10000, 120000, 123457])
@pytest.mark.parametrize("n", [1, 2, 3, 6, 12])
def test_soma_das_parcelas_e_o_total(amount, n):
    parts = split_installments(amount, n, date(2026, 10, 15), *ITAU)
    assert sum(p.amount_cents for p in parts) == amount
    assert len({p.statement_month for p in parts}) == n


def test_parcelas_de_12_atravessam_o_ano():
    parts = split_installments(120000, 12, date(2026, 10, 15), *NUBANK)
    assert parts[0].statement_month == date(2026, 11, 1)
    assert parts[-1].statement_month == date(2027, 10, 1)


def test_sem_credito_nao_tem_fatura():
    (only,) = split_installments(4790, 1, date(2026, 10, 7))
    assert only.statement_month is None
    assert only.amount_cents == 4790


@pytest.mark.parametrize(
    "kwargs",
    [
        {"amount_cents": 0, "installments": 1},
        {"amount_cents": 100, "installments": 0},
        {"amount_cents": 2, "installments": 3, "closing_day": 3, "due_day": 10},
        {"amount_cents": 100, "installments": 2},  # parcelado fora do crédito
        {"amount_cents": 100, "installments": 1, "closing_day": 3},
        {"amount_cents": 100, "installments": 1, "closing_day": 0, "due_day": 10},
        {"amount_cents": 100, "installments": 1, "closing_day": 3, "due_day": 32},
    ],
)
def test_entradas_invalidas(kwargs):
    with pytest.raises(ValueError):
        split_installments(spent_on=date(2026, 10, 7), **kwargs)
