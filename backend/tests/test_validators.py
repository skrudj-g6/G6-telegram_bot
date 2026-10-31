import pytest

from app.core.validators import normalize_player_id


@pytest.mark.parametrize("raw", ["1234-5678", "0000-0000", " 1234-5678 ", "1234-5678\n"])
def test_valid_player_ids(raw):
    assert normalize_player_id(raw) == raw.strip()


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "12345678",
        "1234-567",
        "1234-56789",
        "123-45678",
        "abcd-efgh",
        "1234_5678",
        "1234 5678",
        "1234-5678-9",
        "٠١٢٣-٤٥٦٧",  # арабо-индийские цифры: \d их пропустил бы
        "１２３４-５６７８",  # полноширинные цифры
    ],
)
def test_invalid_player_ids(raw):
    assert normalize_player_id(raw) is None
