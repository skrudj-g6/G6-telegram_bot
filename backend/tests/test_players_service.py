import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Club, PokerAccount, PokerAccountStatus, User, UserStatus
from app.services import players
from app.services.errors import ServiceError


def register(db, tg=1, username="aliya", name="Алия"):
    return players.register_user(db, telegram_id=tg, username=username, first_name=name)


def link(db, tg=1, player_id="1234-5678"):
    return players.link_poker_account(db, telegram_id=tg, raw_player_id=player_id)


def code_of(exc_info) -> str:
    return exc_info.value.code


# ---------- регистрация ----------


def test_register_creates_active_user(db):
    user, created = register(db)
    assert created is True
    assert user.telegram_id == 1
    assert user.status == UserStatus.ACTIVE
    assert user.created_at is not None


def test_register_is_idempotent(db):
    first, created_first = register(db)
    second, created_second = register(db)
    assert (created_first, created_second) == (True, False)
    assert first.id == second.id
    assert len(db.scalars(select(User)).all()) == 1


def test_register_updates_changed_telegram_profile(db):
    register(db, username="old", name="Старое")
    user, created = register(db, username="new", name="Новое")
    assert created is False
    assert (user.username, user.first_name) == ("new", "Новое")


def test_register_allows_missing_username(db):
    user, _ = register(db, username=None)
    assert user.username is None


def test_get_unknown_user_fails(db):
    with pytest.raises(ServiceError) as exc:
        players.get_user(db, 999)
    assert code_of(exc) == "user_not_found"


# ---------- привязка игрового ID ----------


def test_link_creates_pending_account_in_default_club(db):
    register(db)
    account = link(db)
    assert account.player_id == "1234-5678"
    assert account.status == PokerAccountStatus.PENDING
    assert account.club.club_id == "692609"


def test_link_requires_registration(db):
    with pytest.raises(ServiceError) as exc:
        link(db, tg=404)
    assert code_of(exc) == "user_not_found"


@pytest.mark.parametrize("bad", ["", "1234", "1234-567", "abcd-efgh", "٠١٢٣-٤٥٦٧"])
def test_link_rejects_invalid_format(db, bad):
    register(db)
    with pytest.raises(ServiceError) as exc:
        link(db, player_id=bad)
    assert code_of(exc) == "invalid_player_id"
    assert db.scalars(select(PokerAccount)).all() == []


def test_link_strips_whitespace(db):
    register(db)
    assert link(db, player_id="  1234-5678 ").player_id == "1234-5678"


def test_link_same_id_twice_changes_nothing(db):
    register(db)
    first = link(db)
    second = link(db)
    assert first.id == second.id
    assert len(db.scalars(select(PokerAccount)).all()) == 1


def test_pending_account_can_be_corrected(db):
    register(db)
    first = link(db, player_id="1111-1111")
    second = link(db, player_id="2222-2222")
    assert first.id == second.id
    assert second.player_id == "2222-2222"
    assert second.status == PokerAccountStatus.PENDING


def test_player_id_cannot_be_taken_by_two_users(db):
    register(db, tg=1)
    register(db, tg=2, username="b", name="Бек")
    link(db, tg=1, player_id="1234-5678")
    with pytest.raises(ServiceError) as exc:
        link(db, tg=2, player_id="1234-5678")
    assert code_of(exc) == "player_id_taken"
    assert len(db.scalars(select(PokerAccount)).all()) == 1


def test_blocked_user_cannot_link(db):
    user, _ = register(db)
    user.status = UserStatus.BLOCKED
    db.commit()
    with pytest.raises(ServiceError) as exc:
        link(db)
    assert code_of(exc) == "user_blocked"


def test_approved_account_is_locked_for_player(db):
    register(db)
    account = link(db)
    players.approve_poker_account(db, account_id=account.id)
    with pytest.raises(ServiceError) as exc:
        link(db, player_id="9999-9999")
    assert code_of(exc) == "account_locked"
    assert db.get(PokerAccount, account.id).player_id == "1234-5678"


def test_rejected_account_can_be_resubmitted(db):
    register(db)
    account = link(db, player_id="1111-1111")
    players.reject_poker_account(db, account_id=account.id, reason="Опечатка в ID")
    resubmitted = link(db, player_id="2222-2222")
    assert resubmitted.id == account.id
    assert resubmitted.status == PokerAccountStatus.PENDING
    assert resubmitted.reject_reason is None
    assert resubmitted.reviewed_at is None


def test_rejected_account_can_resubmit_same_id(db):
    register(db)
    account = link(db)
    players.reject_poker_account(db, account_id=account.id, reason="Нет в клубе")
    assert link(db).status == PokerAccountStatus.PENDING


# ---------- модерация админом ----------


def test_approve_pending_account(db):
    register(db)
    account = link(db)
    approved = players.approve_poker_account(db, account_id=account.id)
    assert approved.status == PokerAccountStatus.APPROVED
    assert approved.reviewed_at is not None
    assert approved.reject_reason is None


def test_second_approve_is_refused(db):
    register(db)
    account = link(db)
    players.approve_poker_account(db, account_id=account.id)
    with pytest.raises(ServiceError) as exc:
        players.approve_poker_account(db, account_id=account.id)
    assert code_of(exc) == "invalid_transition"


def test_approve_unknown_account(db):
    with pytest.raises(ServiceError) as exc:
        players.approve_poker_account(db, account_id=12345)
    assert code_of(exc) == "account_not_found"


def test_reject_requires_reason(db):
    register(db)
    account = link(db)
    with pytest.raises(ServiceError) as exc:
        players.reject_poker_account(db, account_id=account.id, reason="   ")
    assert code_of(exc) == "reason_required"
    assert db.get(PokerAccount, account.id).status == PokerAccountStatus.PENDING


def test_reject_stores_reason(db):
    register(db)
    account = link(db)
    rejected = players.reject_poker_account(db, account_id=account.id, reason="  Вас нет в клубе ")
    assert rejected.status == PokerAccountStatus.REJECTED
    assert rejected.reject_reason == "Вас нет в клубе"


def test_decided_account_cannot_be_decided_again(db):
    register(db)
    account = link(db)
    players.reject_poker_account(db, account_id=account.id, reason="Нет в клубе")
    with pytest.raises(ServiceError) as exc:
        players.approve_poker_account(db, account_id=account.id)
    assert code_of(exc) == "invalid_transition"
    with pytest.raises(ServiceError) as exc:
        players.reject_poker_account(db, account_id=account.id, reason="Ещё раз")
    assert code_of(exc) == "invalid_transition"


# ---------- ограничения на уровне БД ----------


def test_db_allows_only_one_account_per_user(db):
    user, _ = register(db)
    club = db.scalar(select(Club))
    db.add(PokerAccount(user_id=user.id, club_id=club.id, player_id="1111-1111"))
    db.commit()
    db.add(PokerAccount(user_id=user.id, club_id=club.id, player_id="2222-2222"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_db_requires_reason_for_rejected_status(db):
    user, _ = register(db)
    club = db.scalar(select(Club))
    db.add(
        PokerAccount(
            user_id=user.id,
            club_id=club.id,
            player_id="1111-1111",
            status=PokerAccountStatus.REJECTED,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_db_rejects_unknown_user_status(db):
    db.add(User(telegram_id=7, first_name="X", status="deleted"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
