"""Сотрудники: вход, сессии, управление учётными записями (этап 5).

Все изменения пишутся в аудит в той же транзакции. Пароли и токены в аудит не попадают.
"""

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.permissions import can_manage_role
from app.models import StaffRole, StaffSession, StaffUser
from app.services import audit
from app.services.errors import ServiceError

MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
_LOGIN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    # SQLite (тесты) отдаёт даты без часового пояса; в БД они всегда в UTC.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def normalize_login(raw: str) -> str:
    return (raw or "").strip().lower()


def _check_password(password: str) -> None:
    if not security.password_is_acceptable(password):
        raise ServiceError(
            "weak_password",
            min_length=security.MIN_PASSWORD_LENGTH,
            max_length=security.MAX_PASSWORD_LENGTH,
        )


# --- Токены и сессии ---------------------------------------------------------------


def issue_access_token(staff: StaffUser, now: datetime | None = None) -> tuple[str, int]:
    settings = get_settings()
    now = now or _now()
    ttl = settings.access_token_minutes * 60
    claims = {"sub": str(staff.id), "typ": "access", "iat": int(now.timestamp()), "exp": now.timestamp() + ttl}
    return security.encode_jwt(claims, settings.jwt_secret), ttl


def staff_from_access_token(db: Session, token: str, now: datetime | None = None) -> StaffUser | None:
    """Сотрудник по access-токену. Роль и активность берутся из БД, а не из токена:
    отключение или смена роли действуют сразу."""
    now = now or _now()
    claims = security.decode_jwt(token, get_settings().jwt_secret, now.timestamp())
    if not claims or claims.get("typ") != "access":
        return None
    try:
        staff_id = int(claims["sub"])
    except (KeyError, ValueError, TypeError):
        return None
    staff = db.get(StaffUser, staff_id)
    return staff if staff is not None and staff.is_active else None


def _open_session(db: Session, staff_id: int, now: datetime) -> str:
    token = security.new_refresh_token()
    db.add(
        StaffSession(
            staff_id=staff_id,
            token_hash=security.hash_token(token),
            expires_at=now + timedelta(days=get_settings().refresh_token_days),
        )
    )
    return token


def revoke_all_sessions(db: Session, staff_id: int, now: datetime | None = None) -> None:
    """Закрывает все refresh-сессии сотрудника. Коммитит вызывающий."""
    db.execute(
        update(StaffSession)
        .where(StaffSession.staff_id == staff_id, StaffSession.revoked_at.is_(None))
        .values(revoked_at=now or _now())
    )


# --- Вход --------------------------------------------------------------------------


def login(
    db: Session, *, login: str, password: str, ip: str | None = None, now: datetime | None = None
) -> tuple[StaffUser, str]:
    """Проверяет пароль, открывает сессию. Возвращает (сотрудник, refresh-токен)."""
    now = now or _now()
    staff = db.scalar(select(StaffUser).where(StaffUser.login == normalize_login(login)))

    if staff is None:
        security.verify_password(password, security.DUMMY_HASH)  # то же время, что и для реального
        audit.record(db, staff_id=None, action="auth.login_failed", details={"known": False}, ip=ip)
        db.commit()
        raise ServiceError("invalid_credentials")

    locked_until = _aware(staff.locked_until)
    if locked_until is not None and now < locked_until:
        raise ServiceError("too_many_attempts")

    if not security.verify_password(password, staff.password_hash) or not staff.is_active:
        attempts = staff.failed_attempts + 1
        values = {"failed_attempts": attempts}
        if attempts >= MAX_FAILED_ATTEMPTS:
            values = {
                "failed_attempts": 0,
                "locked_until": now + timedelta(minutes=LOCK_MINUTES),
            }
        db.execute(update(StaffUser).where(StaffUser.id == staff.id).values(**values))
        audit.record(
            db,
            staff_id=staff.id,
            action="auth.login_failed",
            details={"locked": attempts >= MAX_FAILED_ATTEMPTS},
            ip=ip,
        )
        db.commit()
        raise ServiceError("invalid_credentials")

    staff.failed_attempts = 0
    staff.locked_until = None
    staff.last_login_at = now
    token = _open_session(db, staff.id, now)
    audit.record(db, staff_id=staff.id, action="auth.login", ip=ip)
    db.commit()
    return staff, token


def refresh(db: Session, *, token: str, ip: str | None = None, now: datetime | None = None) -> tuple[StaffUser, str]:
    """Меняет refresh-токен на новый (ротация). Повторное использование старого токена
    считается кражей: все сессии сотрудника закрываются."""
    now = now or _now()
    session = db.scalar(
        select(StaffSession).where(StaffSession.token_hash == security.hash_token(token or ""))
    )
    if session is None:
        raise ServiceError("invalid_refresh")
    if session.revoked_at is not None:
        revoke_all_sessions(db, session.staff_id, now)
        audit.record(db, staff_id=session.staff_id, action="auth.refresh_reuse", ip=ip)
        db.commit()
        raise ServiceError("invalid_refresh")
    staff = db.get(StaffUser, session.staff_id)
    if _aware(session.expires_at) <= now or staff is None or not staff.is_active:
        raise ServiceError("invalid_refresh")

    result = db.execute(
        update(StaffSession)
        .where(StaffSession.id == session.id, StaffSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    if result.rowcount == 0:  # параллельный запрос успел раньше
        db.rollback()
        raise ServiceError("invalid_refresh")
    new_token = _open_session(db, staff.id, now)
    db.commit()
    return staff, new_token


def logout(db: Session, *, token: str, now: datetime | None = None) -> None:
    db.execute(
        update(StaffSession)
        .where(
            StaffSession.token_hash == security.hash_token(token or ""),
            StaffSession.revoked_at.is_(None),
        )
        .values(revoked_at=now or _now())
    )
    db.commit()


def change_own_password(
    db: Session, *, staff: StaffUser, current: str, new: str, ip: str | None = None
) -> None:
    if not security.verify_password(current, staff.password_hash):
        raise ServiceError("invalid_credentials")
    _check_password(new)
    staff.password_hash = security.hash_password(new)
    revoke_all_sessions(db, staff.id)
    audit.record(db, staff_id=staff.id, action="staff.password_changed", entity_type="staff", entity_id=staff.id, ip=ip)
    db.commit()


# --- Управление сотрудниками --------------------------------------------------------


def _target(db: Session, staff_id: int) -> StaffUser:
    target = db.get(StaffUser, staff_id)
    if target is None:
        raise ServiceError("staff_not_found")
    return target


def _active_owners(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(StaffUser).where(
            StaffUser.role == StaffRole.OWNER, StaffUser.is_active.is_(True)
        )
    )


def list_staff(db: Session) -> list[StaffUser]:
    return list(db.scalars(select(StaffUser).order_by(StaffUser.id)).all())


def create_staff(
    db: Session,
    *,
    actor: StaffUser | None,
    login: str,
    display_name: str,
    role: str,
    password: str,
    ip: str | None = None,
) -> StaffUser:
    """`actor=None` — создание из командной строки на сервере (первый Owner)."""
    if role not in StaffRole.ALL:
        raise ServiceError("invalid_role")
    if actor is not None and not can_manage_role(actor.role, role):
        raise ServiceError("forbidden")
    login = normalize_login(login)
    name = " ".join((display_name or "").split())
    if not _LOGIN_RE.match(login) or not 1 <= len(name) <= 100:
        raise ServiceError("invalid_staff_data")
    _check_password(password)

    staff = StaffUser(
        login=login, display_name=name, role=role, password_hash=security.hash_password(password)
    )
    db.add(staff)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ServiceError("login_taken") from None
    audit.record(
        db,
        staff_id=actor.id if actor else None,
        action="staff.created",
        entity_type="staff",
        entity_id=staff.id,
        details={"login": login, "role": role, "via": "api" if actor else "cli"},
        ip=ip,
    )
    db.commit()
    return staff


def update_staff(
    db: Session,
    *,
    actor: StaffUser,
    staff_id: int,
    role: str | None = None,
    display_name: str | None = None,
    is_active: bool | None = None,
    ip: str | None = None,
) -> StaffUser:
    target = _target(db, staff_id)
    if not can_manage_role(actor.role, target.role):
        raise ServiceError("forbidden")
    changes: dict = {}

    if role is not None and role != target.role:
        if role not in StaffRole.ALL:
            raise ServiceError("invalid_role")
        if not can_manage_role(actor.role, role):
            raise ServiceError("forbidden")
        if target.id == actor.id:
            raise ServiceError("cannot_modify_self")
        changes["role"] = (target.role, role)
    if is_active is not None and is_active != target.is_active:
        if target.id == actor.id:
            raise ServiceError("cannot_modify_self")
        changes["is_active"] = (target.is_active, is_active)
    if display_name is not None:
        name = " ".join(display_name.split())
        if not 1 <= len(name) <= 100:
            raise ServiceError("invalid_staff_data")
        if name != target.display_name:
            changes["display_name"] = (target.display_name, name)

    # В системе всегда остаётся хотя бы один действующий Owner.
    loses_owner = target.role == StaffRole.OWNER and target.is_active and (
        ("role" in changes) or (changes.get("is_active", (None, True))[1] is False)
    )
    if loses_owner and _active_owners(db) <= 1:
        raise ServiceError("last_owner")

    if not changes:
        return target
    for field, (_, new_value) in changes.items():
        setattr(target, field, new_value)
    if "is_active" in changes and not target.is_active or "role" in changes:
        revoke_all_sessions(db, target.id)
    audit.record(
        db,
        staff_id=actor.id,
        action="staff.updated",
        entity_type="staff",
        entity_id=target.id,
        details={k: {"from": old, "to": new} for k, (old, new) in changes.items()},
        ip=ip,
    )
    db.commit()
    return target


def reset_password(
    db: Session, *, actor: StaffUser, staff_id: int, new_password: str, ip: str | None = None
) -> None:
    """Q-13: сброс доступа — Owner/Admin задаёт новый временный пароль вручную."""
    target = _target(db, staff_id)
    if target.id != actor.id and not can_manage_role(actor.role, target.role):
        raise ServiceError("forbidden")
    _check_password(new_password)
    target.password_hash = security.hash_password(new_password)
    target.failed_attempts = 0
    target.locked_until = None
    revoke_all_sessions(db, target.id)
    audit.record(
        db, staff_id=actor.id, action="staff.password_reset", entity_type="staff", entity_id=target.id, ip=ip
    )
    db.commit()
