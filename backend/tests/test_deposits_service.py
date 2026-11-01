from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import DepositRequest, DepositStatus, DepositStatusHistory, UserStatus
from app.services import deposits, players, receipt_storage
from app.services.errors import ServiceError

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
PDF = b"%PDF-1.7\n" + b"0" * 100


def approved_player(db, tg=1, player_id="1234-5678"):
    players.register_user(db, telegram_id=tg, username=None, first_name="Игрок")
    account = players.link_poker_account(db, telegram_id=tg, raw_player_id=player_id)
    players.approve_poker_account(db, account_id=account.id)
    return tg


def create(db, tg=1, amount=5000, method="fiat", key="key-00000001", now=T0, usdt=None):
    """fiat: сумма в тенге (`amount`); crypto: количество USDT (`usdt`)."""
    if method == "crypto":
        return deposits.create_deposit(
            db, telegram_id=tg, method=method, usdt_amount=usdt, idempotency_key=key, now=now
        )
    return deposits.create_deposit(
        db, telegram_id=tg, method=method, amount=amount, idempotency_key=key, now=now
    )


def code_of(exc_info) -> str:
    return exc_info.value.code


def receipt_files() -> list[Path]:
    root = Path(get_settings().receipts_dir)
    return [p for p in root.iterdir()] if root.exists() else []


def history(db, request_id):
    return db.scalars(
        select(DepositStatusHistory)
        .where(DepositStatusHistory.request_id == request_id)
        .order_by(DepositStatusHistory.id)
    ).all()


# ---------- создание ----------


def test_create_gives_requisites_and_waits_for_receipt(db, provider):
    approved_player(db)
    request, created = create(db)
    assert created is True
    assert request.status == DepositStatus.AWAITING_RECEIPT
    assert request.amount == 5000
    assert request.method == "fiat"
    assert request.payment_details["bank"] == "Тестовый банк"
    assert provider.calls == [("fiat", 5000)]
    # 10 минут на чек (Q-9)
    expires = request.expires_at.replace(tzinfo=timezone.utc)
    assert expires - T0 == timedelta(minutes=10)
    rows = history(db, request.id)
    assert [(h.from_status, h.to_status, h.actor_type) for h in rows] == [
        (None, "awaiting_receipt", "player")
    ]


def test_both_methods_are_supported(db, provider, usdt_rate):
    approved_player(db)
    fiat, _ = create(db, method="fiat", key="key-fiat-0001")
    deposits.cancel_deposit(db, telegram_id=1, request_id=fiat.id)
    crypto, _ = create(db, method="crypto", usdt=Decimal("10"), key="key-crypto-001")
    assert crypto.method == "crypto"


# ---------- крипта: сумма вводится в USDT, тенге считаются по курсу ----------


def test_crypto_amount_is_converted_by_rate_and_rate_is_stored(db, provider, usdt_rate):
    approved_player(db)
    request, _ = create(db, method="crypto", usdt=Decimal("10"))
    assert request.amount == 5005  # 10 × 500.50
    assert request.crypto_amount == 1000  # 10.00 USDT в сотых
    assert request.exchange_rate == "500.5"
    assert provider.calls == [("crypto", 5005)]
    assert provider.usdt_amounts == [Decimal("10")]  # платёжке передаётся и USDT


def test_fiat_request_has_no_crypto_fields(db, provider):
    approved_player(db)
    request, _ = create(db)
    assert (request.crypto_amount, request.exchange_rate) == (None, None)
    assert provider.usdt_amounts == [None]


def test_fractional_tenge_are_rounded_down(db, provider, usdt_rate):
    approved_player(db)
    request, _ = create(db, method="crypto", usdt=Decimal("12.34"))
    assert request.amount == 6176  # 12.34 × 500.50 = 6176.17
    assert request.crypto_amount == 1234


def test_rate_change_does_not_affect_existing_request(db, provider, usdt_rate):
    from app.models import AppSetting

    approved_player(db)
    request, _ = create(db, method="crypto", usdt=Decimal("10"))
    db.get(AppSetting, "usdt_kzt_rate").value = "600"
    db.commit()
    reloaded = deposits._load(db, request.id)
    assert (reloaded.amount, reloaded.exchange_rate) == (5005, "500.5")


def test_crypto_is_unavailable_until_owner_sets_the_rate(db, provider):
    """Курса по умолчанию нет: выдуманный курс недопустим."""
    approved_player(db)
    with pytest.raises(ServiceError) as exc:
        create(db, method="crypto", usdt=Decimal("10"))
    assert code_of(exc) == "exchange_rate_unavailable"
    assert db.scalars(select(DepositRequest)).all() == []
    assert provider.calls == []


@pytest.mark.parametrize("bad_rate", ["", "abc", "0", "-5", "NaN", "Infinity"])
def test_invalid_rate_in_settings_is_treated_as_missing(db, provider, bad_rate):
    from app.models import AppSetting

    db.add(AppSetting(key="usdt_kzt_rate", value=bad_rate))
    db.add(AppSetting(key="usdt_rate_mode", value="manual"))
    db.commit()
    approved_player(db)
    with pytest.raises(ServiceError) as exc:
        create(db, method="crypto", usdt=Decimal("10"))
    assert code_of(exc) == "exchange_rate_unavailable"


@pytest.mark.parametrize(
    "usdt", [None, Decimal("0"), Decimal("-1"), Decimal("1.234"), Decimal("NaN"), Decimal("1E+10")]
)
def test_invalid_usdt_amount_is_refused(db, provider, usdt_rate, usdt):
    approved_player(db)
    with pytest.raises(ServiceError) as exc:
        create(db, method="crypto", usdt=usdt)
    assert code_of(exc) == "invalid_amount"
    assert provider.calls == []


def test_amount_fields_must_match_the_method(db, provider, usdt_rate):
    approved_player(db)
    with pytest.raises(ServiceError) as exc:  # fiat с USDT
        deposits.create_deposit(
            db, telegram_id=1, method="fiat", amount=5000, usdt_amount=Decimal("10"),
            idempotency_key="key-00000001", now=T0,
        )
    assert code_of(exc) == "invalid_amount"
    with pytest.raises(ServiceError) as exc:  # crypto с тенге
        deposits.create_deposit(
            db, telegram_id=1, method="crypto", amount=5000, usdt_amount=Decimal("10"),
            idempotency_key="key-00000001", now=T0,
        )
    assert code_of(exc) == "invalid_amount"
    with pytest.raises(ServiceError) as exc:  # fiat без суммы
        deposits.create_deposit(
            db, telegram_id=1, method="fiat", idempotency_key="key-00000001", now=T0
        )
    assert code_of(exc) == "invalid_amount"
    assert db.scalars(select(DepositRequest)).all() == []


def test_limits_apply_to_tenge_equivalent_of_usdt(db, provider, usdt_rate):
    approved_player(db)
    with pytest.raises(ServiceError) as exc:  # 1 USDT = 500.5 ₸ < 1000
        create(db, method="crypto", usdt=Decimal("1"))
    assert code_of(exc) == "amount_out_of_range"
    assert exc.value.extra == {"min": 1000, "max": 2_000_000, "amount_kzt": 500}

    with pytest.raises(ServiceError) as exc:  # 4000 USDT = 2 002 000 ₸ > 2 000 000
        create(db, method="crypto", usdt=Decimal("4000"))
    assert exc.value.extra["amount_kzt"] == 2_002_000

    assert create(db, method="crypto", usdt=Decimal("2"))[0].amount == 1001  # 2 × 500.5


def test_quote_shows_tenge_before_confirmation(db, usdt_rate):
    quote = deposits.quote_usdt(db, Decimal("10"))
    assert quote == {
        "usdt_amount": "10.00",
        "rate": "500.5",
        "kzt_amount": 5005,
        "min": 1000,
        "max": 2_000_000,
        "within_limits": True,
    }
    assert deposits.quote_usdt(db, Decimal("1"))["within_limits"] is False


def test_quote_without_rate_is_unavailable(db):
    with pytest.raises(ServiceError) as exc:
        deposits.quote_usdt(db, Decimal("10"))
    assert code_of(exc) == "exchange_rate_unavailable"


def test_format_usdt():
    assert deposits.format_usdt(1000) == "10.00"
    assert deposits.format_usdt(1234) == "12.34"
    assert deposits.format_usdt(5) == "0.05"


def test_unknown_method_is_refused(db, provider):
    approved_player(db)
    with pytest.raises(ServiceError) as exc:
        create(db, method="paypal")
    assert code_of(exc) == "invalid_method"


def test_same_idempotency_key_returns_same_request(db, provider):
    approved_player(db)
    first, created_first = create(db)
    second, created_second = create(db)
    assert (created_first, created_second) == (True, False)
    assert first.id == second.id
    assert len(db.scalars(select(DepositRequest)).all()) == 1
    assert len(provider.calls) == 1  # реквизиты второй раз не резервировались


def test_requires_approved_account(db, provider):
    players.register_user(db, telegram_id=1, username=None, first_name="Игрок")
    with pytest.raises(ServiceError) as exc:
        create(db)
    assert code_of(exc) == "account_not_approved"  # аккаунта нет

    players.link_poker_account(db, telegram_id=1, raw_player_id="1234-5678")
    with pytest.raises(ServiceError) as exc:
        create(db)
    assert code_of(exc) == "account_not_approved"  # ждёт подтверждения админа (Q-3)
    assert provider.calls == []


def test_unknown_and_blocked_users(db, provider):
    with pytest.raises(ServiceError) as exc:
        create(db, tg=404)
    assert code_of(exc) == "user_not_found"

    approved_player(db)
    players.get_user(db, 1).status = UserStatus.BLOCKED
    db.commit()
    with pytest.raises(ServiceError) as exc:
        create(db)
    assert code_of(exc) == "user_blocked"


@pytest.mark.parametrize("amount", [0, -1, 999, 2_000_001])
def test_amount_outside_limits_is_refused(db, provider, amount):
    approved_player(db)
    with pytest.raises(ServiceError) as exc:
        create(db, amount=amount)
    assert code_of(exc) == "amount_out_of_range"
    assert exc.value.extra == {"min": 1000, "max": 2_000_000}  # Q-6
    assert db.scalars(select(DepositRequest)).all() == []


@pytest.mark.parametrize("amount", [1000, 2_000_000])
def test_limit_boundaries_are_allowed(db, provider, amount):
    approved_player(db)
    assert create(db, amount=amount)[0].amount == amount


def test_limits_come_from_settings_table(db, provider):
    """Q-6: лимиты меняются в панели, а не в коде."""
    from app.models import AppSetting

    db.add(AppSetting(key="deposit_min_amount", value="5000"))
    db.commit()
    approved_player(db)
    with pytest.raises(ServiceError) as exc:
        create(db, amount=4999)
    assert exc.value.extra["min"] == 5000
    assert create(db, amount=5000)[0].amount == 5000


def test_without_payment_provider_no_request_is_created(db):
    """Q-22: пока платёжка не подключена, свободных реквизитов нет."""
    approved_player(db)
    with pytest.raises(ServiceError) as exc:
        create(db)
    assert code_of(exc) == "no_requisites_available"
    assert db.scalars(select(DepositRequest)).all() == []


def test_one_open_request_at_a_time(db, provider):
    approved_player(db)
    first, _ = create(db)
    with pytest.raises(ServiceError) as exc:
        create(db, key="key-00000002")
    assert code_of(exc) == "deposit_awaiting_receipt"
    deposits.cancel_deposit(db, telegram_id=1, request_id=first.id)
    assert create(db, key="key-00000002")[1] is True


def test_expired_request_does_not_block_a_new_one(db, provider):
    approved_player(db)
    first, _ = create(db)
    second, created = create(db, key="key-00000002", now=T0 + timedelta(minutes=11))
    assert created is True
    assert deposits._load(db, first.id).status == DepositStatus.EXPIRED


# ---------- отмена (Q-5) ----------


def test_cancel_before_receipt(db, provider):
    approved_player(db)
    request, _ = create(db)
    cancelled = deposits.cancel_deposit(db, telegram_id=1, request_id=request.id)
    assert cancelled.status == DepositStatus.CANCELLED
    assert [h.to_status for h in history(db, request.id)] == ["awaiting_receipt", "cancelled"]


def test_cancel_twice_is_harmless(db, provider):
    approved_player(db)
    request, _ = create(db)
    deposits.cancel_deposit(db, telegram_id=1, request_id=request.id)
    again = deposits.cancel_deposit(db, telegram_id=1, request_id=request.id)
    assert again.status == DepositStatus.CANCELLED
    assert len(history(db, request.id)) == 2


def test_cannot_cancel_after_receipt(db, provider):
    approved_player(db)
    request, _ = create(db)
    deposits.attach_receipt(db, telegram_id=1, request_id=request.id, data=JPEG, now=T0)
    with pytest.raises(ServiceError) as exc:
        deposits.cancel_deposit(db, telegram_id=1, request_id=request.id)
    assert code_of(exc) == "invalid_transition"
    assert deposits._load(db, request.id).status == DepositStatus.PENDING


def test_cannot_touch_someone_elses_request(db, provider):
    approved_player(db, tg=1, player_id="1111-1111")
    approved_player(db, tg=2, player_id="2222-2222")
    request, _ = create(db, tg=1)
    for action in (
        lambda: deposits.cancel_deposit(db, telegram_id=2, request_id=request.id),
        lambda: deposits.get_deposit(db, telegram_id=2, request_id=request.id),
        lambda: deposits.attach_receipt(db, telegram_id=2, request_id=request.id, data=JPEG),
    ):
        with pytest.raises(ServiceError) as exc:
            action()
        assert code_of(exc) == "request_not_found"
    assert receipt_files() == []


# ---------- чек (Q-23) ----------


@pytest.mark.parametrize(
    "data, content_type, suffix",
    [(JPEG, "image/jpeg", ".jpg"), (PNG, "image/png", ".png"), (PDF, "application/pdf", ".pdf")],
)
def test_receipt_moves_request_to_operator_queue(db, provider, data, content_type, suffix):
    approved_player(db)
    request, _ = create(db)
    updated = deposits.attach_receipt(
        db, telegram_id=1, request_id=request.id, data=data, now=T0 + timedelta(minutes=3)
    )
    assert updated.status == DepositStatus.PENDING
    assert updated.receipt_content_type == content_type
    assert updated.receipt_size == len(data)
    assert updated.receipt_filename.endswith(suffix)
    [stored] = receipt_files()
    assert stored.name == updated.receipt_filename
    assert stored.read_bytes() == data
    assert history(db, request.id)[-1].to_status == "pending"


@pytest.mark.parametrize(
    "data",
    [b"", b"hello", b"GIF89a" + b"0" * 50, b"MZ" + b"0" * 50, b"<html></html>"],
)
def test_unsupported_receipt_is_refused(db, provider, data):
    approved_player(db)
    request, _ = create(db)
    with pytest.raises(ServiceError) as exc:
        deposits.attach_receipt(db, telegram_id=1, request_id=request.id, data=data, now=T0)
    assert code_of(exc) == "invalid_receipt"
    assert deposits._load(db, request.id).status == DepositStatus.AWAITING_RECEIPT
    assert receipt_files() == []


def test_receipt_larger_than_limit_is_refused(db, provider):
    approved_player(db)
    request, _ = create(db)
    big = JPEG + b"0" * receipt_storage.MAX_RECEIPT_BYTES
    with pytest.raises(ServiceError) as exc:
        deposits.attach_receipt(db, telegram_id=1, request_id=request.id, data=big, now=T0)
    assert code_of(exc) == "receipt_too_large"
    assert receipt_files() == []


def test_receipt_after_deadline_is_refused_and_leaves_no_file(db, provider):
    approved_player(db)
    request, _ = create(db)
    late = T0 + timedelta(minutes=10, seconds=1)
    with pytest.raises(ServiceError) as exc:
        deposits.attach_receipt(db, telegram_id=1, request_id=request.id, data=JPEG, now=late)
    assert code_of(exc) == "request_expired"
    assert receipt_files() == []
    assert deposits._load(db, request.id).receipt_filename is None


def test_second_receipt_is_refused(db, provider):
    approved_player(db)
    request, _ = create(db)
    deposits.attach_receipt(db, telegram_id=1, request_id=request.id, data=JPEG, now=T0)
    with pytest.raises(ServiceError) as exc:
        deposits.attach_receipt(db, telegram_id=1, request_id=request.id, data=PNG, now=T0)
    assert code_of(exc) == "invalid_transition"
    assert len(receipt_files()) == 1


def test_receipt_for_cancelled_request_is_refused(db, provider):
    approved_player(db)
    request, _ = create(db)
    deposits.cancel_deposit(db, telegram_id=1, request_id=request.id)
    with pytest.raises(ServiceError) as exc:
        deposits.attach_receipt(db, telegram_id=1, request_id=request.id, data=JPEG, now=T0)
    assert code_of(exc) == "invalid_transition"
    assert receipt_files() == []


# ---------- автозакрытие (Q-9) ----------


def test_overdue_request_without_receipt_is_closed(db, provider):
    approved_player(db)
    request, _ = create(db)
    assert deposits.expire_overdue(db, now=T0 + timedelta(minutes=9)) == 0
    assert deposits.expire_overdue(db, now=T0 + timedelta(minutes=10)) == 1
    assert deposits._load(db, request.id).status == DepositStatus.EXPIRED
    last = history(db, request.id)[-1]
    assert (last.from_status, last.to_status, last.actor_type) == (
        "awaiting_receipt",
        "expired",
        "system",
    )


def test_request_with_receipt_is_never_auto_closed(db, provider):
    approved_player(db)
    request, _ = create(db)
    deposits.attach_receipt(db, telegram_id=1, request_id=request.id, data=JPEG, now=T0)
    assert deposits.expire_overdue(db, now=T0 + timedelta(hours=5)) == 0
    assert deposits._load(db, request.id).status == DepositStatus.PENDING


def test_expiry_is_not_repeated(db, provider):
    approved_player(db)
    request, _ = create(db)
    later = T0 + timedelta(minutes=30)
    assert deposits.expire_overdue(db, now=later) == 1
    assert deposits.expire_overdue(db, now=later) == 0
    assert len(history(db, request.id)) == 2


def test_cancelled_request_is_not_expired(db, provider):
    approved_player(db)
    request, _ = create(db)
    deposits.cancel_deposit(db, telegram_id=1, request_id=request.id)
    assert deposits.expire_overdue(db, now=T0 + timedelta(hours=1)) == 0
    assert deposits._load(db, request.id).status == DepositStatus.CANCELLED


# ---------- срок хранения чеков (Q-23) ----------


def test_receipts_are_deleted_after_a_week(db, provider):
    approved_player(db)
    request, _ = create(db)
    deposits.attach_receipt(db, telegram_id=1, request_id=request.id, data=PDF, now=T0)

    assert deposits.cleanup_receipts(db, now=T0 + timedelta(days=6, hours=23)) == 0
    assert len(receipt_files()) == 1

    assert deposits.cleanup_receipts(db, now=T0 + timedelta(days=7, seconds=1)) == 1
    assert receipt_files() == []
    kept = deposits._load(db, request.id)
    assert kept.receipt_filename is None
    assert kept.receipt_deleted_at is not None
    assert kept.status == DepositStatus.PENDING  # сама заявка остаётся (ТЗ §7)
    assert deposits.cleanup_receipts(db, now=T0 + timedelta(days=30)) == 0


def test_storage_ignores_unsafe_filenames(tmp_path):
    outside = tmp_path / "keep.txt"
    outside.write_text("x")
    receipt_storage.delete("../keep.txt")
    receipt_storage.delete(str(outside))
    assert outside.exists()
    with pytest.raises(ValueError):
        receipt_storage.path_for("../../etc/passwd")


# ---------- «Мои заявки» ----------


def test_list_returns_only_own_requests_newest_first(db, provider):
    approved_player(db, tg=1, player_id="1111-1111")
    approved_player(db, tg=2, player_id="2222-2222")
    first, _ = create(db, tg=1, key="key-00000001")
    deposits.cancel_deposit(db, telegram_id=1, request_id=first.id)
    second, _ = create(db, tg=1, key="key-00000002")
    create(db, tg=2, key="key-00000003")
    listed = deposits.list_deposits(db, telegram_id=1)
    assert [r.id for r in listed] == [second.id, first.id]


# ---------- комиссия клуба (Q-33) ----------


def set_commission(db, direction, value):
    from app.models import AppSetting
    from app.services import app_settings

    key = app_settings.COMMISSION_KEYS[direction]
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    db.commit()


def test_commission_is_zero_by_default(db, provider):
    approved_player(db)
    request, _ = create(db)
    assert (request.commission_percent, request.commission_amount) == ("0", 0)


def test_commission_is_snapshotted_in_request(db, provider):
    approved_player(db)
    set_commission(db, "deposit", "2.5")
    request, _ = create(db, amount=10_000)
    assert (request.commission_percent, request.commission_amount) == ("2.5", 250)
    set_commission(db, "deposit", "10")
    db.refresh(request)
    assert (request.commission_percent, request.commission_amount) == ("2.5", 250)


def test_commission_is_rounded_up_to_whole_tenge(db, provider):
    approved_player(db)
    set_commission(db, "deposit", "1.5")
    request, _ = create(db, amount=1001)  # 15.015 → 16
    assert request.commission_amount == 16


def test_commission_applies_to_tenge_equivalent_of_crypto(db, provider, usdt_rate):
    approved_player(db)
    set_commission(db, "deposit", "2")
    request, _ = create(db, method="crypto", usdt=Decimal("10"))  # 5005 ₸
    assert request.amount == 5005
    assert request.commission_amount == 101  # 100.1 → 101


def test_withdrawal_commission_does_not_affect_deposits(db, provider):
    approved_player(db)
    set_commission(db, "withdrawal", "5")
    request, _ = create(db)
    assert request.commission_amount == 0


@pytest.mark.parametrize("bad", ["-1", "51", "abc", "NaN", "1.234", ""])
def test_invalid_commission_is_treated_as_zero(db, provider, bad):
    approved_player(db)
    set_commission(db, "deposit", bad)
    request, _ = create(db)
    assert request.commission_amount == 0
