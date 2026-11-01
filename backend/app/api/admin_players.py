from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.admin_deps import client_ip, require_permission
from app.core import permissions
from app.db.session import get_db
from app.models import StaffUser
from app.schemas.admin import (
    DepositAdminOut,
    PageOut,
    PlayerDetailOut,
    PlayerRef,
    RejectRequest,
    WithdrawalAdminOut,
)
from app.services import admin_views, players
from app.services.errors import ServiceError

router = APIRouter(prefix="/admin/v1/players", tags=["admin-players"])

Viewer = Depends(require_permission(permissions.PLAYERS_VIEW))
Moderator = Depends(require_permission(permissions.PLAYERS_MODERATE))


def _detail(db: Session, user_id: int) -> PlayerDetailOut:
    user, account = admin_views.get_player(db, user_id)
    history = admin_views.player_history(db, user_id)
    ref = PlayerRef.build(user, account)
    return PlayerDetailOut(
        player=ref,
        block_reason=user.block_reason,
        duplicate_id_attempts=user.duplicate_id_attempts,
        reject_reason=account.reject_reason if account else None,
        registered_at=user.created_at,
        deposits=[DepositAdminOut.build(r, user, account) for r in history["deposit"]],
        withdrawals=[WithdrawalAdminOut.build(r, user, account) for r in history["withdrawal"]],
    )


def _account_id(db: Session, user_id: int) -> int:
    _, account = admin_views.get_player(db, user_id)
    if account is None:
        raise ServiceError("account_not_found")
    return account.id


@router.get("", response_model=PageOut)
def list_players(
    account_status: str | None = Query(default=None, pattern="^(pending|approved|rejected)$"),
    user_status: str | None = Query(default=None, pattern="^(active|blocked)$"),
    q: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: StaffUser = Viewer,
    db: Session = Depends(get_db),
):
    page = admin_views.list_players(
        db, status=account_status, user_status=user_status, q=q, limit=limit, offset=offset
    )
    return PageOut(
        items=[PlayerRef.build(u, a) for u, a in page.items],
        total=page.total, limit=page.limit, offset=page.offset,
    )


@router.get("/{user_id}", response_model=PlayerDetailOut)
def get_player(user_id: int, _: StaffUser = Viewer, db: Session = Depends(get_db)):
    return _detail(db, user_id)


@router.post("/{user_id}/approve", response_model=PlayerDetailOut)
def approve(user_id: int, request: Request, staff: StaffUser = Moderator, db: Session = Depends(get_db)):
    """Q-3: админ принимает игрока в клуб."""
    players.approve_poker_account(
        db, account_id=_account_id(db, user_id), staff_id=staff.id, ip=client_ip(request)
    )
    return _detail(db, user_id)


@router.post("/{user_id}/reject", response_model=PlayerDetailOut)
def reject(
    user_id: int,
    payload: RejectRequest,
    request: Request,
    staff: StaffUser = Moderator,
    db: Session = Depends(get_db),
):
    players.reject_poker_account(
        db,
        account_id=_account_id(db, user_id),
        reason=payload.reason,
        staff_id=staff.id,
        ip=client_ip(request),
    )
    return _detail(db, user_id)


@router.post("/{user_id}/unblock", response_model=PlayerDetailOut)
def unblock(user_id: int, request: Request, staff: StaffUser = Moderator, db: Session = Depends(get_db)):
    players.unblock_user(db, user_id=user_id, staff_id=staff.id, ip=client_ip(request))
    return _detail(db, user_id)
