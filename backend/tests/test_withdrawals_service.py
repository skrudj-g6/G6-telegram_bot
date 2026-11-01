import pytest
from sqlalchemy import select

from app.models import (
    AppSetting,
    Bank,
    WithdrawalRequest,
    WithdrawalStatus,
    WithdrawalStatusHistory,
)
from app.services import app_settings, players, withdrawals
from app.services.errors import ServiceError


def approved_player(db, tg=1, player_id="1234-5678"):
    players.register_user(db, telegram_id=tg, username=None, first_name="Игрок")
    account = players.link_poker_account(db, telegram_id=tg, raw_player_id=player_id)
    players.approve_poker_account(db, account_id=account.id)
    return tg


def fiat(db, banks, tg=1, amount=5000, key="key-00000001", name="Алия Серикова", bank="Kaspi Bank"):
    return withdrawals.create_withdrawal(
        db,
        telegram_id=tg,
        method="fiat",
        amount=amount,
        holder_name=name,
        bank_id=banks[bank],
        idempotency_key=key,
    )


def code_of(exc_info) -> str:
    return exc_info.value.code


def set_setting(db, key, value):
    app_settings.set_str(db, key, value)
    db.commit()


# ---------- создание ----------


def test_fiat_withdrawal_is_created_pending_with_history(db, banks):
    approved_player(db)
    request, created = fiat(db, banks)
    assert created is True
    assert (request.status, request.amount, request.method) == ("pending", 5000, "fiat")
    assert (request.holder_name, request.bank_name) == ("Алия Серикова", "Kaspi Bank")
    assert request.payment_details is None
    rows = db.scalars(select(WithdrawalStatusHistory)).all()
    assert [(r.from_status, r.to_status, r.actor_type) for r in rows] == [(None, "pending", "player")]


def test_name_is_normalized(db, banks):
    approved_player(db)
    request, _ = fiat(db, banks, name="  Алия   Серикова ")
    assert request.holder_name == "Алия Серикова"


@pytest.mark.parametrize("name", ["", " ", "А", "Алия123", "<script>", "Алия\nСерикова;", "1234 5678"])
def test_invalid_holder_name_is_refused(db, banks, name):
    approved_player(db)
    with pytest.raises(ServiceError) as exc:
        fiat(db, banks, name=name)
    assert code_of(exc) == "invalid_holder_name"
    assert db.scalars(select(WithdrawalRequest)).all() == []


@pytest.mark.parametrize("name", ["Aliya Serikova", "О'Брайен", "Анна-Мария", "Иванов И.И."])
def test_reasonable_names_are_accepted(db, banks, name):
    approved_player(db)
    assert fiat(db, banks, name=name)[1] is True


def test_unknown_or_inactive_bank_is_refused(db, banks):
    approved_player(db)
    with pytest.raises(ServiceError) as exc:
        withdrawals.create_withdrawal(
            db, telegram_id=1, method="fiat", amount=5000,
            holder_name="Алия", bank_id=9999, idempotency_key="key-00000001",
        )
    assert code_of(exc) == "invalid_bank"
    bank = db.get(Bank, banks["Halyk Bank"])
    bank.is_active = False
    db.commit()
    with pytest.raises(ServiceError) as exc:
        fiat(db, banks, bank="Halyk Bank")
    assert code_of(exc) == "invalid_bank"


def test_fiat_requires_bank_and_name(db, banks):
    approved_player(db)
    with pytest.raises(ServiceError) as exc:
        withdrawals.create_withdrawal(
            db, telegram_id=1, method="fiat", amount=5000, idempotency_key="key-00000001"
        )
    assert code_of(exc) == "invalid_holder_name"


def test_list_banks_returns_active_in_order(db, banks):
    db.get(Bank, banks["Halyk Bank"]).is_active = False
    db.commit()
    assert [b.name for b in withdrawals.list_banks(db)] == [
        "Kaspi Bank", "Банк ЦентрКредит", "ForteBank", "Freedom Bank Kazakhstan",
    ]


@pytest.mark.parametrize("amount", [999, 2_000_001])
def test_amount_limits(db, banks, amount):
    approved_player(db)
    with pytest.raises(ServiceError) as exc:
        fiat(db, banks, amount=amount)
    assert code_of(exc) == "amount_out_of_range"
    assert exc.value.extra == {"min": 1000, "max": 2_000_000}


def test_limits_come_from_settings(db, banks):
    approved_player(db)
    set_setting(db, "withdrawal_min_amount", "5000")
    with pytest.raises(ServiceError) as exc:
        fiat(db, banks, amount=4999)
    assert exc.value.extra["min"] == 5000


@pytest.mark.parametrize("amount", [0, -5, True, 10.5, "5000", None])
def test_invalid_amount_is_refused(db, banks, amount):
    approved_player(db)
    with pytest.raises(ServiceError) as exc:
        fiat(db, banks, amount=amount)
    assert code_of(exc) == "invalid_amount"


def test_player_must_be_approved(db, banks):
    players.register_user(db, telegram_id=1, username=None, first_name="Игрок")
    with pytest.raises(ServiceError) as exc:
        fiat(db, banks)
    assert code_of(exc) == "account_not_approved"
    players.link_poker_account(db, telegram_id=1, raw_player_id="1234-5678")  # ещё pending
    with pytest.raises(ServiceError) as exc:
        fiat(db, banks)
    assert code_of(exc) == "account_not_approved"


def test_blocked_user_cannot_withdraw(db, banks):
    from app.models import User, UserStatus

    approved_player(db)
    user = db.scalar(select(User))
    user.status = UserStatus.BLOCKED
    db.commit()
    with pytest.raises(ServiceError) as exc:
        fiat(db, banks)
    assert code_of(exc) == "user_blocked"


def test_unknown_method_is_refused(db, banks):
    approved_player(db)
    with pytest.raises(ServiceError) as exc:
        withdrawals.create_withdrawal(
            db, telegram_id=1, method="cash", amount=5000, idempotency_key="key-00000001"
        )
    assert code_of(exc) == "invalid_method"


# ---------- идемпотентность и одна открытая заявка ----------


def test_same_key_returns_same_request(db, banks):
    approved_player(db)
    first, c1 = fiat(db, banks)
    second, c2 = fiat(db, banks)
    assert (c1, c2) == (True, False)
    assert first.id == second.id
    assert len(db.scalars(select(WithdrawalRequest)).all()) == 1


def test_only_one_open_withdrawal_per_player(db, banks):
    approved_player(db)
    fiat(db, banks)
    with pytest.raises(ServiceError) as exc:
        fiat(db, banks, key="key-00000002")
    assert code_of(exc) == "withdrawal_already_open"


def test_new_withdrawal_allowed_after_cancel(db, banks):
    approved_player(db)
    first, _ = fiat(db, banks)
    withdrawals.cancel_withdrawal(db, telegram_id=1, request_id=first.id)
    second, created = fiat(db, banks, key="key-00000002")
    assert created is True and second.id != first.id


def test_other_players_are_independent(db, banks):
    approved_player(db, tg=1, player_id="1234-5678")
    approved_player(db, tg=2, player_id="8765-4321")
    fiat(db, banks, tg=1)
    assert fiat(db, banks, tg=2)[1] is True


# ---------- процент клуба ----------


def test_percent_is_snapshotted(db, banks):
    approved_player(db)
    set_setting(db, "withdrawal_commission_percent", "-3")
    request, _ = fiat(db, banks, amount=10_000)
    assert (request.commission_percent, request.commission_amount) == ("-3", -300)
    set_setting(db, "withdrawal_commission_percent", "10")
    db.refresh(request)
    assert request.commission_amount == -300


def test_positive_percent_is_a_bonus_on_withdrawal(db, banks):
    approved_player(db)
    set_setting(db, "withdrawal_commission_percent", "3")
    request, _ = fiat(db, banks, amount=10_000)
    assert request.commission_amount == 300  # игрок получит 10 300


def test_deposit_percent_does_not_affect_withdrawal(db, banks):
    approved_player(db)
    set_setting(db, "deposit_commission_percent", "5")
    request, _ = fiat(db, banks)
    assert request.commission_amount == 0


def test_quote(db):
    set_setting(db, "withdrawal_commission_percent", "-2.5")
    assert withdrawals.quote(db, 10_000) == {
        "amount": 10_000, "min": 1000, "max": 2_000_000, "within_limits": True,
        "commission_percent": "-2.5", "commission_amount": -250, "payout_amount": 9750,
    }
    assert withdrawals.quote(db, 500)["within_limits"] is False
    with pytest.raises(ServiceError):
        withdrawals.quote(db, 0)


# ---------- крипта через PSP (Q-31) ----------


def crypto(db, amount=5000, key="key-00000001", **extra):
    return withdrawals.create_withdrawal(
        db, telegram_id=1, method="crypto", amount=amount, idempotency_key=key, **extra
    )


def test_crypto_is_unavailable_until_psp_is_connected(db):
    approved_player(db)
    with pytest.raises(ServiceError) as exc:
        crypto(db)
    assert code_of(exc) == "no_requisites_available"
    assert db.scalars(select(WithdrawalRequest)).all() == []


def test_crypto_withdrawal_takes_only_amount_and_stores_psp_data(db, crypto_payout):
    approved_player(db)
    request, created = crypto(db)
    assert created is True
    assert crypto_payout.calls == [5000]
    assert request.payment_details == {"psp_ref": "TEST-1", "amount": 5000}
    assert (request.holder_name, request.bank_name, request.bank_id) == (None, None, None)


def test_crypto_does_not_accept_name_or_bank(db, banks, crypto_payout):
    approved_player(db)
    with pytest.raises(ServiceError) as exc:
        crypto(db, holder_name="Алия", bank_id=banks["Kaspi Bank"])
    assert code_of(exc) == "invalid_method"
    assert crypto_payout.calls == []


def test_psp_is_not_called_when_amount_is_out_of_range(db, crypto_payout):
    approved_player(db)
    with pytest.raises(ServiceError):
        crypto(db, amount=10)
    assert crypto_payout.calls == []


# ---------- отмена ----------


def test_cancel_pending_withdrawal(db, banks):
    approved_player(db)
    request, _ = fiat(db, banks)
    cancelled = withdrawals.cancel_withdrawal(db, telegram_id=1, request_id=request.id)
    assert cancelled.status == WithdrawalStatus.CANCELLED
    assert withdrawals.cancel_withdrawal(db, telegram_id=1, request_id=request.id).status == "cancelled"
    rows = db.scalars(select(WithdrawalStatusHistory).order_by(WithdrawalStatusHistory.id)).all()
    assert [r.to_status for r in rows] == ["pending", "cancelled"]


def test_cannot_cancel_after_operator_took_it(db, banks):
    approved_player(db)
    request, _ = fiat(db, banks)
    request.status = WithdrawalStatus.PROCESSING
    db.commit()
    with pytest.raises(ServiceError) as exc:
        withdrawals.cancel_withdrawal(db, telegram_id=1, request_id=request.id)
    assert code_of(exc) == "invalid_transition"
    assert db.get(WithdrawalRequest, request.id).status == "processing"


def test_cannot_touch_someone_elses_request(db, banks):
    approved_player(db, tg=1, player_id="1234-5678")
    approved_player(db, tg=2, player_id="8765-4321")
    request, _ = fiat(db, banks, tg=1)
    for action in (withdrawals.cancel_withdrawal, withdrawals.get_withdrawal):
        with pytest.raises(ServiceError) as exc:
            action(db, telegram_id=2, request_id=request.id)
        assert code_of(exc) == "request_not_found"


def test_list_is_newest_first_and_limited(db, banks):
    approved_player(db)
    ids = []
    for i in range(3):
        request, _ = fiat(db, banks, key=f"key-0000000{i}")
        ids.append(request.id)
        withdrawals.cancel_withdrawal(db, telegram_id=1, request_id=request.id)
    listed = withdrawals.list_withdrawals(db, telegram_id=1, limit=2)
    assert [r.id for r in listed] == ids[::-1][:2]
