"""Regras da fatura importada (app/domain/statement.py) e extração do PDF: sem rede, sem LLM."""

import uuid
from datetime import date

import pytest

from app.domain.statement import (
    Existing,
    Item,
    StatementError,
    check_sum,
    item_date,
    match_items,
    parse_brl,
    parse_installment,
    plan_new_expenses,
    summary_text,
)
from app.statements.extract import StatementRefused, extract_pages, mask_card_numbers
from tests.pdfs import FATURA_FICTICIA, blank_pdf, encrypted_pdf, text_pdf

DUE = date(2026, 11, 8)
CYCLE = date(2026, 11, 1)


@pytest.mark.parametrize(
    ("raw", "cents"),
    [
        ("R$ 1.234,56", 123456),
        ("1234,56", 123456),
        ("47,90", 4790),
        ("-R$ 45,90", -4590),
        ("- R$ 45,90", -4590),
        ("45,90-", -4590),
        ("R$ 10", 1000),
        ("R$ 1.000.000,01", 100000001),
        ("−12,00", -1200),
    ],
)
def test_parse_brl(raw: str, cents: int) -> None:
    assert parse_brl(raw) == cents


@pytest.mark.parametrize("raw", ["", "abc", "12,5", "1,234.56", "R$ 1.23,00"])
def test_parse_brl_recusa(raw: str) -> None:
    with pytest.raises(StatementError):
        parse_brl(raw)


def test_data_sem_ano_usa_o_vencimento_e_vira_o_ano() -> None:
    assert item_date("16/10", DUE) == date(2026, 10, 16)
    assert item_date("15/12", DUE) == date(2025, 12, 15)  # parcela comprada no ano anterior
    assert item_date("15/12/2026", DUE) == date(2026, 12, 15)
    jan = date(2027, 1, 8)
    assert item_date("28/12", jan) == date(2026, 12, 28)
    with pytest.raises(StatementError):
        item_date("31/02", DUE)


def test_parcela() -> None:
    assert parse_installment("03/10") == (3, 10)
    assert parse_installment(" 3 / 10 ") == (3, 10)
    assert parse_installment("1/1") is None
    assert parse_installment(None) is None
    with pytest.raises(StatementError):
        parse_installment("11/10")


def _item(day: int, desc: str, cents: int, kind="compra", parc=None, month=10) -> Item:  # noqa: ANN001
    return Item(date(2026, month, day), desc, cents, kind, parc)


ITEMS = [
    _item(16, "RESTAURANTE X", 4790),
    _item(18, "LOJA Y", 12000, parc=(3, 10)),
    _item(20, "MERCADO Z", 123456),
    _item(21, "ESTORNO MERCADO Z", 9506, kind="estorno"),
    _item(25, "PAGAMENTO RECEBIDO", 90000, kind="pagamento"),
]


def test_soma_confere_com_saldo_e_pagamento() -> None:
    check = check_sum(ITEMS, 130740, previous_balance=90000)
    assert check.ok
    # pagamento impresso no resumo vale no lugar do item (não conta duas vezes)
    assert check_sum(ITEMS, 130740, previous_balance=90000, payments=90000).ok


def test_soma_divergente_aponta_a_diferenca() -> None:
    check = check_sum(ITEMS[1:], 130740, previous_balance=90000)
    assert check.difference_cents == -4790
    text = summary_text(
        card="Nubank",
        due=DUE,
        items_count=4,
        printed_total=130740,
        check=check,
        matching=match_items(ITEMS[1:], [], CYCLE),
    )
    assert text.startswith("Atenção: os itens somam R$ 47,90 a menos que o total da fatura")


def _existing(day: int, desc: str, cents: int, no=1, total=1, month=CYCLE) -> Existing:  # noqa: ANN001
    return Existing(uuid.uuid4(), cents, date(2026, 10, day), desc, no, total, month)


def test_casamento_lancado_a_mao_nao_duplica() -> None:
    almoco = _existing(15, "almoço", 4790)
    m = match_items(ITEMS, [almoco], CYCLE)
    assert [(i.description, e.id) for i, e in m.pairs] == [("RESTAURANTE X", almoco.id)]
    assert [i.description for i in m.new] == ["LOJA Y", "MERCADO Z", "ESTORNO MERCADO Z"]
    assert [i.description for i in m.ignored] == ["PAGAMENTO RECEBIDO"]


def test_casamento_fora_da_janela_ou_parcela_diferente() -> None:
    longe = _existing(10, "almoço", 4790)  # 6 dias antes
    outra_parcela = _existing(18, "loja y", 12000, no=2, total=10)
    m = match_items(ITEMS, [longe, outra_parcela], CYCLE)
    assert not m.pairs
    assert {e.id for e in m.outside} == {longe.id, outra_parcela.id}


def test_casamento_parcela_tolera_um_centavo() -> None:
    manual = _existing(18, "loja y", 12001, no=3, total=10)
    m = match_items(ITEMS, [manual], CYCLE)
    assert [e.id for _, e in m.pairs] == [manual.id]


def test_dois_candidatos_vence_data_mais_proxima_depois_descricao() -> None:
    a = _existing(14, "restaurante x", 4790)
    b = _existing(17, "uber", 4790)
    c = _existing(17, "restaurante", 4790)
    m = match_items([ITEMS[0]], [a, b, c], CYCLE)
    assert m.pairs[0][1].id == c.id
    assert {e.id for e in m.outside} == {a.id, b.id}


def test_fora_da_fatura_so_do_ciclo() -> None:
    no_ciclo = _existing(5, "padaria", 3000)
    outro_ciclo = _existing(5, "padaria", 3000, month=date(2026, 12, 1))
    m = match_items([], [no_ciclo, outro_ciclo], CYCLE)
    assert [e.id for e in m.outside] == [no_ciclo.id]


def test_estorno_casa_com_gasto_negativo() -> None:
    estorno = _existing(21, "estorno", -9506)
    m = match_items([ITEMS[3]], [estorno], CYCLE)
    assert m.pairs and not m.new


def test_parcelas_k_a_n_viram_o_ano() -> None:
    plan = plan_new_expenses([ITEMS[1]], CYCLE)
    assert [(p.installment_no, p.statement_month) for p in plan] == [
        (3, date(2026, 11, 1)),
        (4, date(2026, 12, 1)),
        (5, date(2027, 1, 1)),
        (6, date(2027, 2, 1)),
        (7, date(2027, 3, 1)),
        (8, date(2027, 4, 1)),
        (9, date(2027, 5, 1)),
        (10, date(2027, 6, 1)),
    ]
    assert {p.amount_cents for p in plan} == {12000}
    assert {p.spent_on for p in plan} == {date(2026, 10, 18)}
    assert {p.group for p in plan} == {0}


def test_estorno_vira_gasto_negativo() -> None:
    (p,) = plan_new_expenses([ITEMS[3]], CYCLE)
    assert p.amount_cents == -9506 and p.installment_total == 1


def test_resumo_com_novos_e_fora_da_fatura() -> None:
    padaria = _existing(5, "padaria", 3000)
    m = match_items(ITEMS, [padaria], CYCLE)
    text = summary_text(
        card="Nubank",
        due=DUE,
        items_count=5,
        printed_total=130740,
        check=check_sum(ITEMS, 130740, 90000),
        matching=m,
    )
    assert "Fatura do Nubank (vence 08/11/2026): 5 itens, total R$ 1.307,40." in text
    assert "A soma confere com o total da fatura." in text
    assert "4 novos, R$ 1.307,40:" in text
    assert "- 18/10 LOJA Y (3/10): R$ 120,00 (+7 parcelas futuras)" in text
    assert "Lançados por você e fora da fatura: 05/10 padaria R$ 30,00." in text
    assert text.endswith("Lanço os 4? (sim/não)")


def test_resumo_reimportada_sem_nada_novo() -> None:
    m = match_items([ITEMS[0]], [_existing(16, "x", 4790)], CYCLE)
    text = summary_text(
        card="Nubank",
        due=DUE,
        items_count=1,
        printed_total=4790,
        check=check_sum([ITEMS[0]], 4790),
        matching=m,
        imported_before=date(2026, 10, 29),
    )
    assert "Já importada em 29/10; nada novo para lançar." in text
    assert "sim/não" not in text


def test_mascara_numero_do_cartao() -> None:
    assert mask_card_numbers("cartão 5162 9012 3456 7890 ok") == "cartão ****7890 ok"
    assert mask_card_numbers("5162-9012-3456-7890") == "****7890"
    assert mask_card_numbers("5162901234567890123") == "****0123"
    assert mask_card_numbers("final 7890, total 1.234,56, 08/11/2026") == (
        "final 7890, total 1.234,56, 08/11/2026"
    )


def test_extrai_texto_mascarado() -> None:
    pages = extract_pages(text_pdf(FATURA_FICTICIA))
    assert "RESTAURANTE X" in pages[0]
    assert "****7890" in pages[0] and "5162" not in pages[0]


@pytest.mark.parametrize(
    ("pdf", "motivo"),
    [
        (blank_pdf(), "escaneado"),
        (encrypted_pdf(FATURA_FICTICIA), "senha"),
        (b"PK\x03\x04 planilha", "não é um PDF"),
        (b"%PDF-1.4 quebrado", "Não consegui abrir"),
    ],
)
def test_pdf_recusado(pdf: bytes, motivo: str) -> None:
    with pytest.raises(StatementRefused, match=motivo):
        extract_pages(pdf)
