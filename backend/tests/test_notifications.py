from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.models import Notification, User
from app.services import deposits, notifications
from app.services.errors import ServiceError
from tests.test_admin_players_config import newcomer  # noqa: F401  (фикстура)
from tests.test_admin_processing import (  # noqa: F401  (фикстуры)
    approved_player,
    pending_deposit,
    pending_withdrawal,
)

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100


def all_notifications(db):
    db.expire_all()
    return db.scalars(select(Notification).order_by(Notification.id)).all()


def request_notifications(db):
    """Уведомления по заявкам: подтверждение игрового ID при подготовке игрока не в счёт."""
    return [n for n in all_notifications(db) if n.kind != "account"]


def forget_account_notifications(db):
    """Подготовка игрока ставит в очередь «вас приняли»; тестам очереди заявок она мешает."""
    db.execute(delete(Notification).where(Notification.kind == "account"))
    db.commit()


def claim(client, bot_headers, limit=20):
    r = client.post("/bot/v1/notifications/claim", params={"limit": limit}, headers=bot_headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- постановка в очередь ----------


def test_taking_into_work_does_not_notify(client, db, auth, pending_deposit):
    headers, _ = auth("operator", "op1")
    client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=headers)
    assert request_notifications(db) == []


def test_completed_deposit_notifies_player(client, db, auth, pending_deposit):
    headers, _ = auth("operator", "op1")
    client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=headers)
    client.post(f"/admin/v1/deposits/{pending_deposit}/complete", headers=headers)
    (n,) = request_notifications(db)
    assert (n.kind, n.telegram_id) == ("deposit", 1)
    assert n.payload == {
        "id": pending_deposit, "status": "completed", "amount": 5000,
        "credit_amount": 5000, "reason": None,
    }


def test_rejected_deposit_carries_reason(client, db, auth, pending_deposit):
    headers, _ = auth("operator", "op1")
    client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=headers)
    client.post(
        f"/admin/v1/deposits/{pending_deposit}/reject", json={"reason": "Чек не читается"}, headers=headers
    )
    (n,) = request_notifications(db)
    assert n.payload["status"] == "rejected" and n.payload["reason"] == "Чек не читается"


def test_withdrawal_notifications(client, db, auth, pending_withdrawal):
    headers, _ = auth("operator", "op1")
    client.post(f"/admin/v1/withdrawals/{pending_withdrawal}/take", headers=headers)
    client.post(f"/admin/v1/withdrawals/{pending_withdrawal}/complete", headers=headers)
    (n,) = request_notifications(db)
    assert (n.kind, n.telegram_id) == ("withdrawal", 2)
    assert n.payload["status"] == "completed" and n.payload["payout_amount"] == 7000


def test_failed_transition_creates_no_notification(client, db, auth, pending_deposit):
    headers, _ = auth("operator", "op1")
    client.post(f"/admin/v1/deposits/{pending_deposit}/complete", headers=headers)  # 409: не взята
    assert request_notifications(db) == []


def test_expired_deposit_notifies(db, provider):
    approved_player(db)
    request, _ = deposits.create_deposit(
        db, telegram_id=1, method="fiat", amount=5000, idempotency_key="key-00000001"
    )
    deposits.expire_overdue(db, now=datetime.now(timezone.utc) + timedelta(minutes=30))
    (n,) = request_notifications(db)
    assert n.payload["status"] == "expired" and n.payload["id"] == request.id


def test_player_cancel_does_not_notify(client, db, bot_headers, provider):
    approved_player(db)
    request, _ = deposits.create_deposit(
        db, telegram_id=1, method="fiat", amount=5000, idempotency_key="key-00000001"
    )
    client.post(f"/bot/v1/users/1/deposits/{request.id}/cancel", headers=bot_headers)
    assert request_notifications(db) == []


def test_account_decisions_notify(client, db, auth, newcomer):  # noqa: F811
    headers, _ = auth("operator", "op1")
    client.post(f"/admin/v1/players/{newcomer}/approve", headers=headers)
    (n,) = all_notifications(db)
    assert (n.kind, n.telegram_id, n.payload["status"]) == ("account", 10, "approved")


def test_account_rejection_carries_reason(client, db, auth, newcomer):  # noqa: F811
    headers, _ = auth("operator", "op1")
    client.post(f"/admin/v1/players/{newcomer}/reject", json={"reason": "Вас нет в клубе"}, headers=headers)
    (n,) = all_notifications(db)
    assert n.payload == {"status": "rejected", "reason": "Вас нет в клубе"}


def test_unblock_notifies(client, db, auth, newcomer):  # noqa: F811
    from app.models import UserStatus

    user = db.get(User, newcomer)
    user.status = UserStatus.BLOCKED
    db.commit()
    headers, _ = auth("operator", "op1")
    client.post(f"/admin/v1/players/{newcomer}/unblock", headers=headers)
    (n,) = all_notifications(db)
    assert n.payload["status"] == "unblocked"


def test_payload_has_no_requisites_or_secrets(client, db, auth, pending_deposit):
    headers, _ = auth("operator", "op1")
    client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=headers)
    client.post(f"/admin/v1/deposits/{pending_deposit}/complete", headers=headers)
    dump = str([n.payload for n in request_notifications(db)])
    assert "Тестовый банк" not in dump and "payment_details" not in dump and "token" not in dump.lower()


# ---------- выдача боту ----------


def test_endpoints_require_service_token(client, auth, pending_deposit):
    staff_headers, _ = auth("owner", "own1")
    assert client.post("/bot/v1/notifications/claim").status_code == 401
    assert client.post("/bot/v1/notifications/claim", headers=staff_headers).status_code == 401
    assert client.post("/bot/v1/notifications/1/sent").status_code == 401
    assert client.post("/bot/v1/notifications/1/failed", json={}).status_code == 401


def test_claim_returns_items_once_then_after_lease(client, db, auth, bot_headers, pending_deposit):
    forget_account_notifications(db)
    headers, _ = auth("operator", "op1")
    client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=headers)
    client.post(f"/admin/v1/deposits/{pending_deposit}/complete", headers=headers)
    first = claim(client, bot_headers)
    assert len(first) == 1 and first[0]["telegram_id"] == 1 and first[0]["attempts"] == 1
    assert set(first[0]) == {"id", "telegram_id", "kind", "payload", "attempts", "created_at"}
    assert claim(client, bot_headers) == []  # аренда: второй бот ту же запись не получит
    later = datetime.now(timezone.utc) + timedelta(seconds=notifications.LEASE_SECONDS + 5)
    again = notifications.claim(db, now=later)
    assert [n.id for n in again] == [first[0]["id"]] and again[0].attempts == 2


def test_sent_notification_is_not_returned_again(client, db, auth, bot_headers, pending_deposit):
    forget_account_notifications(db)
    headers, _ = auth("operator", "op1")
    client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=headers)
    client.post(f"/admin/v1/deposits/{pending_deposit}/complete", headers=headers)
    item = claim(client, bot_headers)[0]
    assert client.post(f"/bot/v1/notifications/{item['id']}/sent", headers=bot_headers).status_code == 204
    assert client.post(f"/bot/v1/notifications/{item['id']}/sent", headers=bot_headers).status_code == 204
    later = datetime.now(timezone.utc) + timedelta(hours=1)
    assert notifications.claim(db, now=later) == []


def test_unknown_notification_is_404(client, bot_headers):
    assert client.post("/bot/v1/notifications/999/sent", headers=bot_headers).status_code == 404
    r = client.post("/bot/v1/notifications/999/failed", json={}, headers=bot_headers)
    assert r.status_code == 404


def test_claim_limit_and_order(client, db, auth, bot_headers, newcomer):  # noqa: F811
    for i in range(3):
        notifications.notify_account(db, newcomer, "unblocked")
    db.commit()
    first = claim(client, bot_headers, limit=2)
    assert len(first) == 2 and first[0]["id"] < first[1]["id"]
    assert len(claim(client, bot_headers, limit=2)) == 1
    assert client.post("/bot/v1/notifications/claim?limit=0", headers=bot_headers).status_code == 422


def test_transient_failure_backs_off_and_retries(client, db, newcomer, bot_headers):  # noqa: F811
    notifications.notify_account(db, newcomer, "approved")
    db.commit()
    item = claim(client, bot_headers)[0]
    r = client.post(
        f"/bot/v1/notifications/{item['id']}/failed", json={"error": "network"}, headers=bot_headers
    )
    assert r.status_code == 204
    assert claim(client, bot_headers) == []  # пауза
    later = datetime.now(timezone.utc) + timedelta(seconds=90)
    retry = notifications.claim(db, now=later)
    assert [n.attempts for n in retry] == [2]


def test_retry_after_from_telegram_is_respected(client, db, newcomer, bot_headers):  # noqa: F811
    notifications.notify_account(db, newcomer, "approved")
    db.commit()
    item = claim(client, bot_headers)[0]
    client.post(
        f"/bot/v1/notifications/{item['id']}/failed",
        json={"error": "flood", "retry_after_seconds": 600}, headers=bot_headers,
    )
    soon = datetime.now(timezone.utc) + timedelta(seconds=120)
    assert notifications.claim(db, now=soon) == []
    assert len(notifications.claim(db, now=soon + timedelta(seconds=600))) == 1


def test_permanent_failure_is_final(client, db, newcomer, bot_headers):  # noqa: F811
    notifications.notify_account(db, newcomer, "approved")
    db.commit()
    item = claim(client, bot_headers)[0]
    client.post(
        f"/bot/v1/notifications/{item['id']}/failed",
        json={"permanent": True, "error": "bot blocked by user"}, headers=bot_headers,
    )
    row = all_notifications(db)[0]
    assert row.failed_at is not None and row.last_error == "bot blocked by user"
    assert notifications.claim(db, now=datetime.now(timezone.utc) + timedelta(days=1)) == []


def test_gives_up_after_max_attempts(db, newcomer):  # noqa: F811
    notifications.notify_account(db, newcomer, "approved")
    db.commit()
    now = datetime.now(timezone.utc)
    for attempt in range(notifications.MAX_ATTEMPTS):
        now += timedelta(hours=2)
        (n,) = notifications.claim(db, now=now)
        notifications.mark_failed(db, n.id, permanent=False, error="x", now=now)
    row = all_notifications(db)[0]
    assert row.attempts == notifications.MAX_ATTEMPTS and row.failed_at is not None
    assert notifications.claim(db, now=now + timedelta(days=1)) == []


def test_crashed_bot_does_not_loop_forever(db, newcomer):  # noqa: F811
    """Бот брал запись и падал, не подтверждая: после MAX_ATTEMPTS аренд запись закрывается."""
    notifications.notify_account(db, newcomer, "approved")
    db.commit()
    now = datetime.now(timezone.utc)
    for _ in range(notifications.MAX_ATTEMPTS):
        now += timedelta(seconds=notifications.LEASE_SECONDS + 1)
        assert len(notifications.claim(db, now=now)) == 1
    now += timedelta(seconds=notifications.LEASE_SECONDS + 1)
    assert notifications.claim(db, now=now) == []
    assert all_notifications(db)[0].last_error == "max_attempts"


def test_error_text_is_truncated(db, newcomer):  # noqa: F811
    notifications.notify_account(db, newcomer, "approved")
    db.commit()
    (n,) = notifications.claim(db)
    notifications.mark_failed(db, n.id, permanent=True, error="e" * 500)
    assert len(all_notifications(db)[0].last_error) == notifications.MAX_ERROR


def test_cleanup_removes_only_old_finished_records(db, newcomer):  # noqa: F811
    for _ in range(3):
        notifications.notify_account(db, newcomer, "approved")
    db.commit()
    rows = all_notifications(db)
    old = datetime.now(timezone.utc) - timedelta(days=40)
    rows[0].created_at = old
    rows[0].sent_at = old  # старая отправленная: удалить
    rows[1].created_at = old  # старая, но ещё не отправлена: оставить
    db.commit()
    assert notifications.cleanup(db) == 1
    assert len(all_notifications(db)) == 2


def test_service_error_type():
    with pytest.raises(ServiceError):
        raise ServiceError("notification_not_found")
