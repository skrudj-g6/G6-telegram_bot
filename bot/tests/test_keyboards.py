import pytest

pytest.importorskip("aiogram")

from botapp import keyboards  # noqa: E402


def test_buttons_carry_colors_as_in_the_prototype():
    onboarding = keyboards.onboarding().inline_keyboard[0][0]
    assert (onboarding.callback_data, onboarding.style) == ("club:join", "success")
    assert keyboards.register_in_cashier().inline_keyboard[0][0].style == "primary"
    menu = keyboards.main_menu().keyboard
    assert menu[0][0].style == "success" and menu[0][1].style == "danger"


def test_every_callback_data_fits_telegram_limit():
    markups = [
        keyboards.onboarding(), keyboards.register_in_cashier(), keyboards.deposit_methods(),
        keyboards.withdrawal_methods(), keyboards.confirm("dep:ok"), keyboards.cancel_only(),
        keyboards.banks([{"id": 99999, "name": "Bank"}]),
        keyboards.request_actions("dep", 10**9, True),
    ]
    for markup in markups:
        for row in markup.inline_keyboard:
            for b in row:
                assert b.callback_data is None or len(b.callback_data.encode()) <= 64
