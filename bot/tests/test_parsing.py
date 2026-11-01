import pytest

from botapp.parsing import clean_name, parse_amount, parse_usdt


@pytest.mark.parametrize(
    "text,expected",
    [
        ("5000", 5000),
        ("  5000 ", 5000),
        ("5 000", 5000),
        ("5 000", 5000),
        ("2 000 000", 2_000_000),
        ("5000 ₸", 5000),
        ("5000тг", 5000),
        ("5000 тенге", 5000),
        ("1", 1),
    ],
)
def test_parse_amount_accepts_whole_tenge(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize(
    "text",
    [None, "", " ", "0", "00", "-5", "5.5", "5,5", "1e3", "abc", "5000abc", "٥٠٠٠", "5000.00", "1" * 13, "+5"],
)
def test_parse_amount_rejects_everything_else(text):
    assert parse_amount(text) is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("25", "25"),
        ("25.5", "25.5"),
        ("25,50", "25.50"),
        ("0.01", "0.01"),
        ("10 USDT", "10"),
        ("10usdt", "10"),
        (" 7 ", "7"),
    ],
)
def test_parse_usdt(text, expected):
    assert parse_usdt(text) == expected


@pytest.mark.parametrize(
    "text", [None, "", "0", "0.00", "-1", "1.234", "1e5", "abc", "1,2,3", "NaN", "Infinity", "12345678901"]
)
def test_parse_usdt_rejects(text):
    assert parse_usdt(text) is None


def test_clean_name():
    assert clean_name("  Алия   Серикова ") == "Алия Серикова"
    assert clean_name("А") is None
    assert clean_name("") is None
    assert clean_name(None) is None
    assert clean_name("x" * 101) is None
    assert clean_name("x" * 100) == "x" * 100
