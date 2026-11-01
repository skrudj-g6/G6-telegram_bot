"""Чтение данных для панели: списки и карточки заявок, игроков, журнал аудита."""

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    PokerAccount,
    User,
)
from app.services.errors import ServiceError
from app.services.request_processing import DEPOSIT, WITHDRAWAL, Kind

MAX_PAGE = 100


@dataclass
class Page:
    items: list
    total: int
    limit: int
    offset: int


def _paging(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(limit, MAX_PAGE)), max(0, offset)


def _search_filter(q: str):
    """Поиск игрока: по игровому ID, Telegram ID или @username."""
    q = q.strip().lstrip("@")
    if not q:
        return None
    parts = [PokerAccount.player_id.ilike(f"%{q}%"), User.username.ilike(f"%{q}%")]
    if q.isascii() and q.isdigit() and len(q) <= 18:
        parts.append(User.telegram_id == int(q))
    return or_(*parts)


def list_requests(
    db: Session,
    kind: Kind,
    *,
    status: str | None = None,
    method: str | None = None,
    q: str | None = None,
    oldest_first: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> Page:
    limit, offset = _paging(limit, offset)
    model = kind.model
    conditions = []
    if status:
        conditions.append(model.status == status)
    if method:
        conditions.append(model.method == method)
    if q and (clause := _search_filter(q)) is not None:
        conditions.append(clause)

    def joined(stmt):
        return (
            stmt.join(User, User.id == model.user_id)
            .join(PokerAccount, PokerAccount.id == model.poker_account_id)
            .where(*conditions)
        )

    total = db.scalar(joined(select(func.count()).select_from(model)))
    order = model.id.asc() if oldest_first else model.id.desc()
    rows = db.execute(
        joined(select(model, User, PokerAccount)).order_by(order).limit(limit).offset(offset)
    ).all()
    return Page([tuple(r) for r in rows], total, limit, offset)


def get_request(db: Session, kind: Kind, request_id: int):
    """(заявка, игрок, игровой аккаунт, история) или request_not_found."""
    model = kind.model
    row = db.execute(
        select(model, User, PokerAccount)
        .join(User, User.id == model.user_id)
        .join(PokerAccount, PokerAccount.id == model.poker_account_id)
        .where(model.id == request_id)
    ).first()
    if row is None:
        raise ServiceError("request_not_found")
    history = db.scalars(
        select(kind.history).where(kind.history.request_id == request_id).order_by(kind.history.id)
    ).all()
    return (*row, list(history))


def list_players(
    db: Session,
    *,
    status: str | None = None,
    user_status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page:
    limit, offset = _paging(limit, offset)
    conditions = []
    if status:
        conditions.append(PokerAccount.status == status)
    if user_status:
        conditions.append(User.status == user_status)
    if q and (clause := _search_filter(q)) is not None:
        conditions.append(clause)

    def joined(stmt):
        return stmt.outerjoin(PokerAccount, PokerAccount.user_id == User.id).where(*conditions)

    total = db.scalar(joined(select(func.count()).select_from(User)))
    rows = db.execute(
        joined(select(User, PokerAccount)).order_by(User.id.desc()).limit(limit).offset(offset)
    ).all()
    return Page([tuple(r) for r in rows], total, limit, offset)


def get_player(db: Session, user_id: int):
    row = db.execute(
        select(User, PokerAccount)
        .outerjoin(PokerAccount, PokerAccount.user_id == User.id)
        .where(User.id == user_id)
    ).first()
    if row is None:
        raise ServiceError("user_not_found")
    return tuple(row)


def player_history(db: Session, user_id: int, limit: int = 20) -> dict:
    """Последние заявки игрока: «история заявок» из Q-19."""
    result = {}
    for kind in (DEPOSIT, WITHDRAWAL):
        model = kind.model
        result[kind.name] = list(
            db.scalars(
                select(model).where(model.user_id == user_id).order_by(model.id.desc()).limit(limit)
            ).all()
        )
    return result


def list_audit(
    db: Session,
    *,
    action: str | None = None,
    staff_id: int | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page:
    limit, offset = _paging(limit, offset)
    conditions = []
    if action:
        conditions.append(AuditLog.action == action)
    if staff_id is not None:
        conditions.append(AuditLog.staff_id == staff_id)
    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)
    if entity_id:
        conditions.append(AuditLog.entity_id == entity_id)
    total = db.scalar(select(func.count()).select_from(AuditLog).where(*conditions))
    rows = db.scalars(
        select(AuditLog).where(*conditions).order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    ).all()
    return Page(list(rows), total, limit, offset)
