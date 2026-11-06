"""Deutsche Zahlen- und Datumsformate."""
from datetime import date, datetime

import pytest

from app.core.formatting import de_date, de_datetime, de_number, parse_date, parse_number


@pytest.mark.parametrize("text,value", [("12,5", 12.5), ("1.234,5", 1234.5), ("1234.5", 1234.5), ("1,234.5", 1234.5),
                                        ("-0,25", -0.25), ("", None), (" 7 ", 7.0)])
def test_parse_number(text, value):
    assert parse_number(text) == value


def test_parse_number_invalid():
    with pytest.raises(ValueError):
        parse_number("abc")


def test_display():
    assert de_number(1234.5) == "1.234,5"
    assert de_number(0.1, 2) == "0,10"
    assert de_date(date(2026, 3, 5)) == "05.03.2026"
    assert de_datetime(datetime(2026, 3, 5, 14, 7)) == "05.03.2026 14:07"
    assert parse_date("05.03.2026") == date(2026, 3, 5) == parse_date("2026-03-05")
