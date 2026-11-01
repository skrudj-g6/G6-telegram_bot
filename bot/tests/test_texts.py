from zoneinfo import ZoneInfo

from botapp import texts

TZ = ZoneInfo("Asia/Almaty")


def deposit(**over):
    base = {
        "id": 7, "method": "fiat", "amount": 5000, "usdt_amount": None, "exchange_rate": None,
        "commission_percent": "0", "commission_amount": 0, "credit_amount": 5000,
        "status": "awaiting_receipt", "payment_details": {"bank": "Kaspi", "card": "4400 0000"},
        "expires_at": "2026-11-01T12:10:00Z", "receipt_uploaded": False, "reject_reason": None,
        "created_at": "2026-11-01T12:00:00Z",
    }
    base.update(over)
    return base


def test_money_formatting():
    assert texts.money(5000) == "5 000 ₸"
    assert texts.money(2_000_000) == "2 000 000 ₸"


def test_times_are_shown_in_club_timezone():
    assert texts.clock_time("2026-11-01T12:10:00Z", TZ) == "17:10"  # UTC+5
    assert texts.local_time("2026-11-01T12:10:00+00:00", TZ) == "01.11 17:10"
    assert texts.clock_time("2026-11-01T12:10:00", TZ) == "17:10"  # без пояса — UTC


def test_deposit_created_shows_requisites_and_deadline():
    text = texts.deposit_created(deposit(), TZ)
    assert "Kaspi" in text and "4400 0000" in text and "до 17:10" in text
    assert "К зачислению на игровой счёт" in text


def test_percent_note_bonus_and_fee():
    assert "Бонус +3%" in texts.percent_note("3", 300)
    assert "Комиссия -2.5%" in texts.percent_note("-2.5", -250)
    assert texts.percent_note("0", 0) is None


def test_deposit_created_mentions_bonus():
    text = texts.deposit_created(
        deposit(commission_percent="3", commission_amount=150, credit_amount=5150), TZ
    )
    assert "Бонус" in text and "5 150" in text


def test_crypto_deposit_shows_usdt_and_rate():
    text = texts.deposit_created(
        deposit(method="crypto", usdt_amount="10.00", exchange_rate="500.5", amount=5005, credit_amount=5005), TZ
    )
    assert "10.00 USDT" in text and "500.5" in text


def test_user_input_is_escaped():
    text = texts.deposit_card(deposit(status="rejected", reject_reason="<b>x</b> & <script>"), TZ)
    assert "<script>" not in text and "&lt;script&gt;" in text
    card = texts.profile_card(
        {"poker_account": {"player_id": "1234-5678", "status": "rejected", "reject_reason": "<i>"}}, "692609"
    )
    assert "<i>" not in card.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "")


def test_payment_details_are_escaped_and_not_shown_after_receipt():
    awaiting = texts.deposit_card(deposit(payment_details={"card": "<1>"}), TZ)
    assert "&lt;1&gt;" in awaiting
    done = texts.deposit_card(deposit(status="pending", payment_details=None), TZ)
    assert "Реквизиты" not in done


def test_status_labels_cover_backend_statuses():
    for status in ("awaiting_receipt", "pending", "processing", "completed", "rejected", "cancelled", "expired"):
        assert status in texts.DEPOSIT_STATUS
    for status in ("pending", "processing", "completed", "rejected", "cancelled"):
        assert status in texts.WITHDRAWAL_STATUS


def test_cancel_rules_match_owner_decisions():
    assert texts.DEPOSIT_CANCELLABLE == {"awaiting_receipt"}  # Q-5
    assert texts.WITHDRAWAL_CANCELLABLE == {"pending"}  # Q-36


def test_stub_message_for_missing_requisites():
    """Q-22: пока платёжка не подключена."""
    msg = texts.error_text("no_requisites_available")
    assert "нет свободных реквизитов" in msg and "10 минут" in msg


def test_error_texts():
    assert "от 1 000 ₸ до 2 000 000 ₸" in texts.error_text(
        "amount_out_of_range", {"min": 1000, "max": 2_000_000}
    )
    assert "Эквивалент" in texts.error_text(
        "amount_out_of_range", {"min": 1000, "max": 2_000_000, "amount_kzt": 500}
    )
    assert "повторной попытке" in texts.error_text("player_id_taken", {"blocked": False, "attempts_left": 1})
    assert "закрыт" in texts.error_text("player_id_taken", {"blocked": True})
    assert texts.error_text("something_new") == texts.GENERIC_ERROR


def test_withdrawal_summary_and_card():
    quote = {"amount": 10000, "commission_percent": "-2.5", "commission_amount": -250, "payout_amount": 9750}
    text = texts.withdrawal_summary(quote, "fiat", "Алия <S>", "Kaspi Bank")
    assert "9 750" in text and "Комиссия" in text and "&lt;S&gt;" in text and "Kaspi Bank" in text
    card = texts.withdrawal_card(
        {"id": 3, "status": "rejected", "method": "fiat", "amount": 10000, "payout_amount": 9750,
         "holder_name": "Алия", "bank_name": "Kaspi Bank", "reject_reason": "Нет средств",
         "created_at": "2026-11-01T12:00:00Z"}, TZ,
    )
    assert "Отклонена" in card and "Нет средств" in card


def test_request_line():
    line = texts.request_line("dep", deposit(), TZ)
    assert "№7" in line and "Ожидает чек" in line
