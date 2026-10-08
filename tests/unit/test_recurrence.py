from datetime import date, datetime

import pytest

from app.clock import TZ
from app.domain.recurrence import (
    day_bounds,
    next_occurrence,
    normalize_rrule,
    occurrences_between,
)


def dt(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=TZ)


def test_normalize_rrule():
    assert normalize_rrule("FREQ=YEARLY") == "FREQ=YEARLY"
    assert normalize_rrule("RRULE:FREQ=WEEKLY;BYDAY=MO") == "FREQ=WEEKLY;BYDAY=MO"
    assert normalize_rrule(None) is None
    assert normalize_rrule("  ") is None
    with pytest.raises(ValueError):
        normalize_rrule("FREQ=TODO_DIA")


def test_aniversario_criado_com_ano_antigo_aparece_no_periodo():
    start, end = day_bounds(date(2027, 3, 14), date(2027, 3, 14))
    assert occurrences_between(dt(2000, 3, 14), "FREQ=YEARLY", start, end) == [dt(2027, 3, 14)]


def test_proxima_ocorrencia_vira_o_ano():
    hoje = dt(2026, 10, 7)
    assert next_occurrence(dt(2026, 3, 14), "FREQ=YEARLY", hoje) == dt(2027, 3, 14)
    assert next_occurrence(dt(2026, 12, 25), "FREQ=YEARLY", hoje) == dt(2026, 12, 25)


def test_proxima_ocorrencia_inclui_hoje():
    assert next_occurrence(dt(2020, 10, 7), "FREQ=YEARLY", dt(2026, 10, 7)) == dt(2026, 10, 7)


def test_evento_unico():
    hoje = dt(2026, 10, 7)
    assert next_occurrence(dt(2026, 10, 9, 14), None, hoje) == dt(2026, 10, 9, 14)
    assert next_occurrence(dt(2026, 10, 1, 14), None, hoje) is None
    start, end = day_bounds(date(2026, 10, 9), date(2026, 10, 9))
    assert occurrences_between(dt(2026, 10, 9, 14), None, start, end) == [dt(2026, 10, 9, 14)]
    assert occurrences_between(dt(2026, 10, 10, 0), None, start, end) == []


def test_29_de_fevereiro_pula_anos_nao_bissextos():
    # Comportamento do dateutil (RFC 5545): sem 29/02, o ano é pulado.
    assert next_occurrence(dt(2024, 2, 29), "FREQ=YEARLY", dt(2026, 10, 7)) == dt(2028, 2, 29)


def test_semanal_no_periodo():
    start, end = day_bounds(date(2026, 10, 12), date(2026, 10, 18))
    got = occurrences_between(dt(2026, 9, 7, 19), "FREQ=WEEKLY;BYDAY=MO,WE", start, end)
    assert got == [dt(2026, 10, 12, 19), dt(2026, 10, 14, 19)]
