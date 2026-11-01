from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app import worker
from app.models import AppSetting
from app.services import app_settings, deposits, rates
from app.services.errors import ServiceError

from tests.test_deposits_service import approved_player

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


class FakeSource:
    name = "fake"

    def __init__(self, value="500.55", error=False):
        self.value = Decimal(value)
        self.error = error

    def fetch(self):
        if self.error:
            raise rates.RateFetchError("down")
        return self.value


def setting(db, key, value):
    app_settings.set_str(db, key, value)
    db.commit()


def seed_auto_rate(db, value="500", at=T0):
    setting(db, "usdt_kzt_rate", value)
    setting(db, "usdt_kzt_rate_updated_at", at.isoformat())
    setting(db, "usdt_rate_mode", "auto")


# ---------- провайдер ----------


def make_coingecko(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return rates.CoinGeckoProvider("https://example.test/price", client=client)


def test_coingecko_parses_rate_and_requests_tether_in_kzt():
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"tether": {"kzt": 521.37}})

    assert make_coingecko(handler).fetch() == Decimal("521.37")
    assert seen["params"] == {"ids": "tether", "vs_currencies": "kzt"}


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"tether": {}}),
        httpx.Response(200, json={"tether": {"kzt": "abc"}}),
        httpx.Response(200, content=b"not json"),
    ],
)
def test_coingecko_errors_become_rate_fetch_error(response):
    with pytest.raises(rates.RateFetchError):
        make_coingecko(lambda request: response).fetch()


# ---------- обновление ----------


def test_refresh_stores_rate_time_and_source(db):
    assert rates.refresh_usdt_rate(db, FakeSource("500.555"), now=T0) == rates.UPDATED
    assert app_settings.get_str(db, "usdt_kzt_rate") == "500.56"
    assert app_settings.get_str(db, "usdt_kzt_rate_source") == "auto:fake"
    assert app_settings.get_usdt_rate(db, T0) == Decimal("500.56")


def test_rate_is_usable_before_and_unusable_after_max_age(db):
    seed_auto_rate(db)
    assert app_settings.get_usdt_rate(db, T0 + timedelta(minutes=29)) == Decimal("500")
    assert app_settings.get_usdt_rate(db, T0 + timedelta(minutes=31)) is None


def test_auto_rate_without_timestamp_is_unusable(db):
    setting(db, "usdt_kzt_rate", "500")
    assert app_settings.get_usdt_rate(db, T0) is None


def test_unknown_mode_is_treated_as_auto(db):
    seed_auto_rate(db)
    setting(db, "usdt_rate_mode", "weird")
    assert app_settings.get_usdt_rate_mode(db) == "auto"
    assert app_settings.get_usdt_rate(db, T0 + timedelta(hours=5)) is None


def test_manual_rate_never_goes_stale_and_is_not_overwritten(db):
    setting(db, "usdt_kzt_rate", "480")
    setting(db, "usdt_rate_mode", "manual")
    assert app_settings.get_usdt_rate(db, T0 + timedelta(days=30)) == Decimal("480")
    assert rates.refresh_usdt_rate(db, FakeSource("500"), now=T0) == rates.SKIPPED
    assert app_settings.get_str(db, "usdt_kzt_rate") == "480"


def test_big_jump_from_fresh_rate_is_rejected(db):
    seed_auto_rate(db, "500")
    result = rates.refresh_usdt_rate(db, FakeSource("650"), now=T0 + timedelta(minutes=5))
    assert result == rates.REJECTED
    assert app_settings.get_str(db, "usdt_kzt_rate") == "500"


def test_moderate_change_from_fresh_rate_is_accepted(db):
    seed_auto_rate(db, "500")
    result = rates.refresh_usdt_rate(db, FakeSource("540"), now=T0 + timedelta(minutes=5))
    assert result == rates.UPDATED
    assert app_settings.get_str(db, "usdt_kzt_rate") == "540.00"


def test_big_jump_is_accepted_when_previous_rate_is_stale(db):
    seed_auto_rate(db, "500")
    result = rates.refresh_usdt_rate(db, FakeSource("650"), now=T0 + timedelta(hours=2))
    assert result == rates.UPDATED
    assert app_settings.get_str(db, "usdt_kzt_rate") == "650.00"


def test_first_rate_is_accepted_without_previous(db):
    assert rates.refresh_usdt_rate(db, FakeSource("500"), now=T0) == rates.UPDATED


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "0.001"])
def test_invalid_values_from_source_are_rejected(db, value):
    assert rates.refresh_usdt_rate(db, FakeSource(value), now=T0) == rates.REJECTED
    assert app_settings.get_str(db, "usdt_kzt_rate") is None


def test_source_error_is_raised_and_keeps_old_rate(db):
    seed_auto_rate(db, "500")
    with pytest.raises(rates.RateFetchError):
        rates.refresh_usdt_rate(db, FakeSource(error=True), now=T0)
    assert app_settings.get_str(db, "usdt_kzt_rate") == "500"


def test_no_provider_means_skipped(db):
    rates.set_provider(None)
    try:
        assert rates.refresh_usdt_rate(db, now=T0) == rates.SKIPPED
    finally:
        rates._provider_overridden = False


# ---------- влияние на пополнение ----------


def test_crypto_deposit_blocked_when_auto_rate_is_stale(db, provider):
    approved_player(db)
    seed_auto_rate(db, "500", at=T0 - timedelta(minutes=45))
    with pytest.raises(ServiceError) as exc:
        deposits.create_deposit(
            db,
            telegram_id=1,
            method="crypto",
            usdt_amount=Decimal("10"),
            idempotency_key="key-00000001",
            now=T0,
        )
    assert exc.value.code == "exchange_rate_unavailable"
    assert provider.calls == []


def test_crypto_deposit_uses_fresh_auto_rate_and_floors_tenge(db, provider):
    approved_player(db)
    seed_auto_rate(db, "500.55", at=T0 - timedelta(minutes=5))
    request, _ = deposits.create_deposit(
        db,
        telegram_id=1,
        method="crypto",
        usdt_amount=Decimal("10"),
        idempotency_key="key-00000001",
        now=T0,
    )
    assert request.amount == 5005  # 5005.5 → вниз до целых тенге
    assert request.exchange_rate == "500.55"


# ---------- фоновая задача ----------


def test_worker_refreshes_rate_when_asked(db):
    rates.set_provider(FakeSource("505.00"))
    try:
        worker.run_once(cleanup=False, refresh_rate=True)
    finally:
        rates._provider_overridden = False
    db.expire_all()
    assert app_settings.get_str(db, "usdt_kzt_rate") == "505.00"


def test_worker_survives_rate_source_failure(db):
    rates.set_provider(FakeSource(error=True))
    try:
        worker.run_once(cleanup=False, refresh_rate=True)  # не должно бросать
    finally:
        rates._provider_overridden = False
    assert app_settings.get_str(db, "usdt_kzt_rate") is None


def test_worker_does_not_fetch_rate_unless_asked(db):
    rates.set_provider(FakeSource("505.00"))
    try:
        worker.run_once(cleanup=False)
    finally:
        rates._provider_overridden = False
    assert app_settings.get_str(db, "usdt_kzt_rate") is None
