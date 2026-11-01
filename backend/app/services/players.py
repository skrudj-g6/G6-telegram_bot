import logging

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.validators import normalize_player_id
from app.services import audit
from app.models import Club, PokerAccount, PokerAccountStatus, User, UserStatus
from app.services.errors import ServiceError

logger = logging.getLogger(__name__)


def get_user(db: Session, telegram_id: int) -> User:
    user = db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        raise ServiceError("user_not_found")
    return user


def register_user(
    db: Session, *, telegram_id: int, username: str | None, first_name: str
) -> tuple[User, bool]:
    """Регистрирует игрока по Telegram ID. Идемпотентно: повтор не создаёт дубль.

    Возвращает (пользователь, создан_ли_сейчас).
    """
    user = db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is not None:
        # Имя и username в Telegram могут меняться — обновляем.
        if user.username != username or user.first_name != first_name:
            user.username = username
            user.first_name = first_name
            db.commit()
        return user, False

    user = User(telegram_id=telegram_id, username=username, first_name=first_name)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Одновременный /start: другой запрос успел создать запись первым.
        db.rollback()
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
            raise
        return user, False
    return user, True


def _get_club(db: Session) -> Club:
    club = db.scalar(select(Club).where(Club.club_id == get_settings().club_id))
    if club is None:
        # Клуб создаётся миграцией; его отсутствие — ошибка конфигурации, а не игрока.
        raise RuntimeError(f"Клуб {get_settings().club_id!r} не найден в БД")
    return club


def _player_id_taken(db: Session, club_id: int, player_id: str, user_id: int) -> bool:
    return (
        db.scalar(
            select(PokerAccount.id).where(
                PokerAccount.club_id == club_id,
                PokerAccount.player_id == player_id,
                PokerAccount.user_id != user_id,
            )
        )
        is not None
    )


# Q-27 + Q-29: первая попытка занять чужой ID — предупреждение, вторая — блокировка.
MAX_TAKEN_ID_ATTEMPTS = 2


def _taken_id_error(db: Session, user: User, player_id: str) -> ServiceError:
    """Фиксирует попытку занять уже зарегистрированный ID и возвращает ошибку для бота.

    Счётчик растёт атомарным UPDATE: две одновременные попытки не потеряются.
    Разблокировать может только сотрудник (кнопка в панели — этап 8).
    """
    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(duplicate_id_attempts=User.duplicate_id_attempts + 1)
    )
    db.commit()
    db.refresh(user)

    if user.duplicate_id_attempts < MAX_TAKEN_ID_ATTEMPTS:
        logger.warning(
            "Предупреждение telegram_id=%s: игровой ID %s уже привязан", user.telegram_id, player_id
        )
        return ServiceError(
            "player_id_taken",
            blocked=False,
            attempts_left=MAX_TAKEN_ID_ATTEMPTS - user.duplicate_id_attempts,
        )

    user.status = UserStatus.BLOCKED
    user.block_reason = f"Повторная попытка привязать уже занятый игровой ID {player_id}"
    db.commit()
    logger.warning(
        "Пользователь telegram_id=%s заблокирован: игровой ID %s уже привязан", user.telegram_id, player_id
    )
    return ServiceError("player_id_taken", blocked=True)


def link_poker_account(db: Session, *, telegram_id: int, raw_player_id: str) -> PokerAccount:
    """Привязывает игровой ID к игроку; аккаунт ждёт подтверждения админом (Q-3, Q-4).

    - pending: ID можно исправить (опечатка);
    - rejected: можно отправить исправленный ID, аккаунт снова pending;
    - approved: игрок менять ID не может;
    - ID уже привязан другому игроку: первая попытка — предупреждение, вторая блокирует
      пользователя (Q-27, Q-29).
    """
    player_id = normalize_player_id(raw_player_id)
    if player_id is None:
        raise ServiceError("invalid_player_id")

    user = get_user(db, telegram_id)
    if user.status != UserStatus.ACTIVE:
        raise ServiceError("user_blocked")

    club = _get_club(db)
    account = user.poker_account

    if account is not None and account.status == PokerAccountStatus.APPROVED:
        raise ServiceError("account_locked")

    if _player_id_taken(db, club.id, player_id, user.id):
        raise _taken_id_error(db, user, player_id)

    if account is None:
        account = PokerAccount(
            user_id=user.id,
            club_id=club.id,
            player_id=player_id,
            status=PokerAccountStatus.PENDING,
        )
        db.add(account)
    elif account.status == PokerAccountStatus.PENDING and account.player_id == player_id:
        return account  # тот же ID повторно — ничего не меняем
    else:
        account.player_id = player_id
        account.status = PokerAccountStatus.PENDING
        account.reject_reason = None
        account.reviewed_at = None

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Гонка: ID успел занять другой игрок.
        if _player_id_taken(db, club.id, player_id, user.id):
            raise _taken_id_error(db, user, player_id)
        raise
    return account


def _review_failure(db: Session, account_id: int) -> ServiceError:
    exists = db.scalar(select(PokerAccount.id).where(PokerAccount.id == account_id))
    return ServiceError("account_not_found" if exists is None else "invalid_transition")


def approve_poker_account(
    db: Session, *, account_id: int, staff_id: int | None = None, ip: str | None = None
) -> PokerAccount:
    """Админ принимает игрока в клуб. Только из pending; повторное подтверждение — ошибка.

    Условный UPDATE защищает от гонки двух админов. Кто подтвердил — в журнале аудита.
    """
    result = db.execute(
        update(PokerAccount)
        .where(
            PokerAccount.id == account_id,
            PokerAccount.status == PokerAccountStatus.PENDING,
        )
        .values(
            status=PokerAccountStatus.APPROVED,
            reject_reason=None,
            reviewed_at=func.now(),
        )
    )
    if result.rowcount == 0:
        db.rollback()
        raise _review_failure(db, account_id)
    audit.record(
        db, staff_id=staff_id, action="player.approved", entity_type="poker_account",
        entity_id=account_id, ip=ip,
    )
    db.commit()
    return db.get(PokerAccount, account_id, populate_existing=True)


def reject_poker_account(
    db: Session, *, account_id: int, reason: str, staff_id: int | None = None, ip: str | None = None
) -> PokerAccount:
    """Админ отклоняет игрока. Причина обязательна (по аналогии с ТЗ §5.2)."""
    reason = reason.strip()
    if not reason:
        raise ServiceError("reason_required")

    result = db.execute(
        update(PokerAccount)
        .where(
            PokerAccount.id == account_id,
            PokerAccount.status == PokerAccountStatus.PENDING,
        )
        .values(
            status=PokerAccountStatus.REJECTED,
            reject_reason=reason[:500],
            reviewed_at=func.now(),
        )
    )
    if result.rowcount == 0:
        db.rollback()
        raise _review_failure(db, account_id)
    audit.record(
        db, staff_id=staff_id, action="player.rejected", entity_type="poker_account",
        entity_id=account_id, details={"reason": reason[:500]}, ip=ip,
    )
    db.commit()
    return db.get(PokerAccount, account_id, populate_existing=True)


def unblock_user(db: Session, *, user_id: int, staff_id: int, ip: str | None = None) -> User:
    """Сотрудник снимает блокировку (в том числе по Q-27). Счётчик попыток занять чужой ID
    не обнуляется: следующая такая попытка снова заблокирует игрока."""
    result = db.execute(
        update(User)
        .where(User.id == user_id, User.status == UserStatus.BLOCKED)
        .values(status=UserStatus.ACTIVE, block_reason=None)
    )
    if result.rowcount == 0:
        db.rollback()
        if db.get(User, user_id) is None:
            raise ServiceError("user_not_found")
        raise ServiceError("invalid_transition")
    audit.record(
        db, staff_id=staff_id, action="player.unblocked", entity_type="user", entity_id=user_id, ip=ip
    )
    db.commit()
    return db.get(User, user_id, populate_existing=True)
