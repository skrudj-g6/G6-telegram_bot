"""Гонки на настоящем PostgreSQL (SQLite не даёт честной параллельной записи).

Запускаются только если задан TEST_POSTGRES_URL, например
postgresql+psycopg://user:pass@localhost:5432/altyn_test. БД должна быть тестовой:
таблицы пересоздаются. В CI она поднимается сервисом (.github/workflows/ci.yml).
"""

import os
import threading
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.models import (
    Club,
    DepositRequest,
    DepositStatusHistory,
    Notification,
    PokerAccount,
    StaffUser,
    User,
)
from app.services import notifications, request_processing as rp
from app.services.errors import ServiceError

URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_POSTGRES_URL не задан")

WORKERS = 8


@pytest.fixture
def pg():
    engine = create_engine(URL, pool_size=WORKERS + 2)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Club(club_id="692609", name="Altyn Crown"))
        s.commit()
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


def seed(engine, staff_count=WORKERS, status="pending") -> tuple[int, list[int]]:
    with Session(engine) as s:
        club = s.scalar(select(Club))
        user = User(telegram_id=1, first_name="Игрок", status="active")
        s.add(user)
        s.flush()
        account = PokerAccount(
            user_id=user.id, club_id=club.id, player_id="1234-5678", status="approved"
        )
        s.add(account)
        staff = [
            StaffUser(login=f"s{i}", display_name=f"S{i}", role="operator", password_hash="x", is_active=True)
            for i in range(staff_count)
        ]
        s.add_all(staff)
        s.flush()
        deposit = DepositRequest(
            user_id=user.id, poker_account_id=account.id, method="fiat", amount=5000,
            status=status, idempotency_key="key-00000001", commission_percent="0",
            commission_amount=0, payment_details={}, expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        )
        s.add(deposit)
        s.commit()
        return deposit.id, [x.id for x in staff]


def race(engine, staff_ids, action):
    """Запускает action(session, staff) во всех потоках одновременно; возвращает исходы."""
    barrier = threading.Barrier(len(staff_ids))
    outcomes: list = [None] * len(staff_ids)

    def work(index, staff_id):
        with Session(engine) as s:
            staff = s.get(StaffUser, staff_id)
            barrier.wait()
            try:
                action(s, staff, index)
                outcomes[index] = "ok"
            except ServiceError as exc:
                outcomes[index] = exc.code

    threads = [threading.Thread(target=work, args=(i, sid)) for i, sid in enumerate(staff_ids)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return outcomes


def test_only_one_operator_takes_a_request(pg):
    deposit_id, staff_ids = seed(pg)
    outcomes = race(pg, staff_ids, lambda s, staff, i: rp.take(s, rp.DEPOSIT, deposit_id, staff))
    assert outcomes.count("ok") == 1
    assert set(outcomes) - {"ok"} == {"invalid_transition"}
    with Session(pg) as s:
        taken = s.scalars(
            select(DepositStatusHistory).where(DepositStatusHistory.to_status == "processing")
        ).all()
        assert len(taken) == 1
        assert s.get(DepositRequest, deposit_id).assigned_staff_id == taken[0].actor_id


def test_complete_and_reject_cannot_both_win(pg):
    deposit_id, staff_ids = seed(pg, staff_count=2, status="processing")

    def action(s, staff, i):
        if i == 0:
            rp.complete(s, rp.DEPOSIT, deposit_id, staff)
        else:
            rp.reject(s, rp.DEPOSIT, deposit_id, staff, "Чек не читается")

    outcomes = race(pg, staff_ids, action)
    assert outcomes.count("ok") == 1
    with Session(pg) as s:
        final = s.get(DepositRequest, deposit_id).status
        assert final in ("completed", "rejected")
        # игрок получает ровно одно уведомление о результате
        assert s.scalar(select(func.count()).select_from(Notification)) == 1


def test_two_bots_never_claim_the_same_notification(pg):
    with Session(pg) as s:
        user = User(telegram_id=7, first_name="Игрок", status="active")
        s.add(user)
        s.flush()
        for _ in range(20):
            notifications.notify_account(s, user.id, "unblocked")
        s.commit()

    claimed: list[list[int]] = [[] for _ in range(4)]
    barrier = threading.Barrier(4)

    def work(index):
        with Session(pg) as s:
            barrier.wait()
            claimed[index] = [n.id for n in notifications.claim(s, limit=20)]

    threads = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    flat = [i for part in claimed for i in part]
    assert len(flat) == len(set(flat)) == 20
