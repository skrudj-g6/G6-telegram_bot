import pytest
from sqlalchemy import select

from app.models import (
    AuditLog,
    DepositRequest,
    DepositStatusHistory,
    WithdrawalStatusHistory,
)
from app.services import deposits, players, withdrawals

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100


def detail(response) -> dict:
    return response.json()["detail"]


def approved_player(db, tg=1, player_id="1234-5678"):
    players.register_user(db, telegram_id=tg, username=f"user{tg}", first_name="Игрок")
    account = players.link_poker_account(db, telegram_id=tg, raw_player_id=player_id)
    players.approve_poker_account(db, account_id=account.id)
    return tg


@pytest.fixture
def pending_deposit(db, provider):
    approved_player(db)
    request, _ = deposits.create_deposit(
        db, telegram_id=1, method="fiat", amount=5000, idempotency_key="key-00000001"
    )
    deposits.attach_receipt(db, telegram_id=1, request_id=request.id, data=JPEG)
    return request.id


@pytest.fixture
def pending_withdrawal(db, banks):
    approved_player(db, tg=2, player_id="8765-4321")
    request, _ = withdrawals.create_withdrawal(
        db, telegram_id=2, method="fiat", amount=7000, holder_name="Алия Серикова",
        bank_id=banks["Kaspi Bank"], idempotency_key="key-00000002",
    )
    return request.id


# ---------- доступ ----------


def test_requests_require_login(client, pending_deposit):
    assert client.get("/admin/v1/deposits").status_code == 401
    assert client.post(f"/admin/v1/deposits/{pending_deposit}/take").status_code == 401


def test_finance_can_view_but_not_process(client, auth, pending_deposit):
    headers, _ = auth("finance", "fin1")
    assert client.get("/admin/v1/deposits", headers=headers).status_code == 200
    r = client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=headers)
    assert (r.status_code, detail(r)["code"]) == (403, "forbidden")


# ---------- пополнения ----------


def test_list_and_detail_show_requisites_for_operator(client, auth, pending_deposit):
    headers, _ = auth("operator", "op1")
    page = client.get("/admin/v1/deposits", headers=headers).json()
    assert page["total"] == 1 and page["items"][0]["status"] == "pending"
    item = page["items"][0]
    assert item["payment_details"]["bank"] == "Тестовый банк"
    assert item["player"]["player_id"] == "1234-5678" and item["receipt"]["available"] is True
    one = client.get(f"/admin/v1/deposits/{pending_deposit}", headers=headers).json()
    assert [h["to_status"] for h in one["history"]] == ["awaiting_receipt", "pending"]


def test_list_filters_search_and_paging(client, db, auth, pending_deposit, provider):
    headers, _ = auth("operator", "op1")
    get = lambda **params: client.get("/admin/v1/deposits", params=params, headers=headers).json()
    assert get(status="pending")["total"] == 1
    assert get(status="completed")["total"] == 0
    assert get(method="crypto")["total"] == 0
    assert get(q="1234")["total"] == 1 and get(q="user1")["total"] == 1 and get(q="1")["total"] == 1
    assert get(q="9999")["total"] == 0
    assert get(limit=1, offset=1)["items"] == []
    assert client.get("/admin/v1/deposits?limit=0", headers=headers).status_code == 422
    assert client.get("/admin/v1/deposits?method=cash", headers=headers).status_code == 422


def test_take_complete_flow_with_history_and_audit(client, db, auth, pending_deposit):
    headers, op = auth("operator", "op1")
    taken = client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=headers)
    assert taken.status_code == 200
    assert (taken.json()["status"], taken.json()["assigned_staff_id"]) == ("processing", op.id)
    done = client.post(f"/admin/v1/deposits/{pending_deposit}/complete", headers=headers)
    assert done.json()["status"] == "completed"
    rows = db.scalars(select(DepositStatusHistory).order_by(DepositStatusHistory.id)).all()
    assert [(r.to_status, r.actor_type) for r in rows][-2:] == [
        ("processing", "staff"), ("completed", "staff"),
    ]
    assert rows[-1].actor_id == op.id
    actions = [a.action for a in db.scalars(select(AuditLog)).all()]
    assert "deposit.take" in actions and "deposit.complete" in actions


def test_two_operators_cannot_take_the_same_request(client, auth, pending_deposit):
    h1, _ = auth("operator", "op1")
    h2, _ = auth("operator", "op2")
    assert client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=h1).status_code == 200
    r = client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=h2)
    assert (r.status_code, detail(r)["code"]) == (409, "invalid_transition")
    assert detail(r)["status"] == "processing"


def test_any_operator_can_work_with_any_request(client, auth, pending_deposit):
    """Q-42: заявку, которую взял другой оператор, может завершить любой сотрудник с правом."""
    h1, op1 = auth("operator", "op1")
    h2, op2 = auth("operator", "op2")
    client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=h1)
    released = client.post(f"/admin/v1/deposits/{pending_deposit}/release", headers=h2)
    assert (released.status_code, released.json()["status"]) == (200, "pending")
    client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=h1)
    done = client.post(f"/admin/v1/deposits/{pending_deposit}/complete", headers=h2)
    assert (done.status_code, done.json()["status"]) == (200, "completed")


def test_finished_by_other_operator_is_recorded_in_history(client, db, auth, pending_deposit):
    h1, op1 = auth("operator", "op1")
    h2, op2 = auth("operator", "op2")
    client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=h1)
    client.post(f"/admin/v1/deposits/{pending_deposit}/reject", json={"reason": "Нет оплаты"}, headers=h2)
    last = db.scalars(select(DepositStatusHistory).order_by(DepositStatusHistory.id.desc())).first()
    assert (last.to_status, last.actor_id) == ("rejected", op2.id)


def test_release_returns_to_queue_and_another_can_take(client, auth, pending_deposit):
    h1, _ = auth("operator", "op1")
    h2, op2 = auth("operator", "op2")
    client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=h1)
    released = client.post(f"/admin/v1/deposits/{pending_deposit}/release", headers=h1).json()
    assert (released["status"], released["assigned_staff_id"]) == ("pending", None)
    taken = client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=h2).json()
    assert taken["assigned_staff_id"] == op2.id


def test_cannot_complete_without_taking(client, auth, pending_deposit):
    headers, _ = auth("operator", "op1")
    r = client.post(f"/admin/v1/deposits/{pending_deposit}/complete", headers=headers)
    assert (r.status_code, detail(r)["code"]) == (409, "invalid_transition")


def test_finished_request_is_final(client, auth, pending_deposit):
    headers, _ = auth("operator", "op1")
    client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=headers)
    client.post(f"/admin/v1/deposits/{pending_deposit}/complete", headers=headers)
    for action in ("take", "complete", "release"):
        r = client.post(f"/admin/v1/deposits/{pending_deposit}/{action}", headers=headers)
        assert r.status_code == 409


def test_reject_needs_reason_and_player_sees_it(client, auth, bot_headers, pending_deposit):
    headers, _ = auth("operator", "op1")
    client.post(f"/admin/v1/deposits/{pending_deposit}/take", headers=headers)
    assert client.post(
        f"/admin/v1/deposits/{pending_deposit}/reject", json={"reason": "  "}, headers=headers
    ).status_code in (409, 422)
    assert client.post(f"/admin/v1/deposits/{pending_deposit}/reject", json={}, headers=headers).status_code == 422
    r = client.post(
        f"/admin/v1/deposits/{pending_deposit}/reject",
        json={"reason": "Чек не читается"}, headers=headers,
    )
    assert (r.json()["status"], r.json()["reject_reason"]) == ("rejected", "Чек не читается")
    mine = client.get(f"/bot/v1/users/1/deposits/{pending_deposit}", headers=bot_headers).json()
    assert (mine["status"], mine["reject_reason"]) == ("rejected", "Чек не читается")


def test_blank_reason_is_reason_required(client, db, auth, pending_deposit):
    from app.services import request_processing as rp
    from app.services.errors import ServiceError

    _, op = auth("operator", "op1")
    rp.take(db, rp.DEPOSIT, pending_deposit, op)
    with pytest.raises(ServiceError) as exc:
        rp.reject(db, rp.DEPOSIT, pending_deposit, op, "   ")
    assert exc.value.code == "reason_required"


def test_unknown_request_is_404(client, auth):
    headers, _ = auth("operator", "op1")
    assert client.get("/admin/v1/deposits/999", headers=headers).status_code == 404
    assert client.post("/admin/v1/deposits/999/take", headers=headers).status_code == 404


def test_player_cannot_cancel_after_operator_takes_withdrawal(client, auth, bot_headers, pending_withdrawal):
    headers, _ = auth("operator", "op1")
    client.post(f"/admin/v1/withdrawals/{pending_withdrawal}/take", headers=headers)
    r = client.post(f"/bot/v1/users/2/withdrawals/{pending_withdrawal}/cancel", headers=bot_headers)
    assert (r.status_code, detail(r)["code"]) == (409, "invalid_transition")


# ---------- выводы ----------


def test_withdrawal_shows_holder_and_bank_to_operator(client, auth, pending_withdrawal):
    headers, _ = auth("operator", "op1")
    item = client.get(f"/admin/v1/withdrawals/{pending_withdrawal}", headers=headers).json()
    assert (item["holder_name"], item["bank_name"], item["payout_amount"]) == (
        "Алия Серикова", "Kaspi Bank", 7000,
    )


def test_withdrawal_full_cycle(client, db, auth, pending_withdrawal):
    headers, op = auth("operator", "op1")
    assert client.post(f"/admin/v1/withdrawals/{pending_withdrawal}/take", headers=headers).status_code == 200
    done = client.post(f"/admin/v1/withdrawals/{pending_withdrawal}/complete", headers=headers)
    assert done.json()["status"] == "completed"
    rows = db.scalars(select(WithdrawalStatusHistory).order_by(WithdrawalStatusHistory.id)).all()
    assert [r.to_status for r in rows] == ["pending", "processing", "completed"]
    assert "withdrawal.complete" in [a.action for a in db.scalars(select(AuditLog)).all()]


def test_withdrawal_reject_frees_player_for_new_request(client, db, auth, banks, pending_withdrawal):
    headers, _ = auth("operator", "op1")
    client.post(f"/admin/v1/withdrawals/{pending_withdrawal}/take", headers=headers)
    client.post(f"/admin/v1/withdrawals/{pending_withdrawal}/reject", json={"reason": "Нет средств"}, headers=headers)
    request, created = withdrawals.create_withdrawal(
        db, telegram_id=2, method="fiat", amount=3000, holder_name="Алия",
        bank_id=banks["Halyk Bank"], idempotency_key="key-00000003",
    )
    assert created is True


# ---------- чеки ----------


def test_operator_downloads_receipt_and_view_is_audited(client, db, auth, pending_deposit):
    headers, op = auth("operator", "op1")
    r = client.get(f"/admin/v1/deposits/{pending_deposit}/receipt", headers=headers)
    assert r.status_code == 200 and r.content == JPEG
    assert r.headers["content-type"] == "image/jpeg"
    assert "no-store" in r.headers["cache-control"] and r.headers["x-content-type-options"] == "nosniff"
    log = db.scalars(select(AuditLog).where(AuditLog.action == "receipt.view")).all()
    assert [(l.staff_id, l.entity_id) for l in log] == [(op.id, str(pending_deposit))]


def test_receipt_requires_login(client, pending_deposit):
    assert client.get(f"/admin/v1/deposits/{pending_deposit}/receipt").status_code == 401


def test_receipt_missing_or_deleted_is_404(client, db, auth, provider):
    headers, _ = auth("finance", "fin1")
    approved_player(db)
    request, _ = deposits.create_deposit(
        db, telegram_id=1, method="fiat", amount=5000, idempotency_key="key-00000001"
    )
    assert client.get(f"/admin/v1/deposits/{request.id}/receipt", headers=headers).status_code == 404
    deposits.attach_receipt(db, telegram_id=1, request_id=request.id, data=JPEG)
    assert client.get(f"/admin/v1/deposits/{request.id}/receipt", headers=headers).status_code == 200
    from datetime import datetime, timedelta, timezone

    deposits.cleanup_receipts(db, now=datetime.now(timezone.utc) + timedelta(days=8))
    r = client.get(f"/admin/v1/deposits/{request.id}/receipt", headers=headers)
    assert (r.status_code, detail(r)["code"]) == (404, "receipt_not_available")
    item = client.get(f"/admin/v1/deposits/{request.id}", headers=headers).json()
    assert item["receipt"]["available"] is False
