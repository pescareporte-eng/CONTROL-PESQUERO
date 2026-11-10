import pytest
from decimal import Decimal
from app.services.validation import parse_decimal, parse_date, money

def test_parse_decimal_accepts_decimal_comma():
    assert parse_decimal("12,345", "TM") == Decimal("12.345")

def test_parse_decimal_rejects_negative():
    with pytest.raises(ValueError):
        parse_decimal("-1", "TM")

def test_parse_date_iso():
    assert parse_date("2026-11-10") == "2026-11-10"

def test_money_rounds_to_cents():
    assert money(Decimal("10.555")) == Decimal("10.56")
