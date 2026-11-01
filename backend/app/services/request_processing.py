"""Обработка заявок оператором (ТЗ §5–6): взять в работу, вернуть, выполнить, отклонить.

Одинаково для пополнений и выводов. Каждый переход — условный UPDATE (D-6): из двух
одновременных действий (два оператора берут одну заявку) успешным будет только одно.
Работать с любой заявкой может любой сотрудник с правом requests.process (Q-42):
исполнитель фиксируется для справки, но не ограничивает остальных. Статус, история и
аудит пишутся в одной транзакции.

Деньги система не двигает (ТЗ §12): «выполнено» означает, что оператор вручную провёл
операцию и фишки/выплата отражены.
"""

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    DepositRequest,
    DepositStatus,
    DepositStatusHistory,
    StaffUser,
    WithdrawalRequest,
    WithdrawalStatus,
    WithdrawalStatusHistory,
)
from app.services import audit
from app.services.errors import ServiceError

MAX_REASON = 500


@dataclass(frozen=True)
class Kind:
    name: str  # "deposit" | "withdrawal"
    model: type
    history: type
    pending: str
    processing: str
    completed: str
    rejected: str


DEPOSIT = Kind(
    "deposit",
    DepositRequest,
    DepositStatusHistory,
    DepositStatus.PENDING,
    DepositStatus.PROCESSING,
    DepositStatus.COMPLETED,
    DepositStatus.REJECTED,
)
WITHDRAWAL = Kind(
    "withdrawal",
    WithdrawalRequest,
    WithdrawalStatusHistory,
    WithdrawalStatus.PENDING,
    WithdrawalStatus.PROCESSING,
    WithdrawalStatus.COMPLETED,
    WithdrawalStatus.REJECTED,
)


def _load(db: Session, kind: Kind, request_id: int):
    return db.scalar(
        select(kind.model).where(kind.model.id == request_id).execution_options(populate_existing=True)
    )


def _failure(db: Session, kind: Kind, request_id: int) -> ServiceError:
    """Почему условный UPDATE ничего не изменил."""
    current = _load(db, kind, request_id)
    if current is None:
        return ServiceError("request_not_found")
    return ServiceError("invalid_transition", status=current.status)


def _move(
    db: Session,
    kind: Kind,
    request_id: int,
    staff: StaffUser,
    *,
    action: str,
    from_status: str,
    to_status: str,
    values: dict,
    comment: str | None = None,
    ip: str | None = None,
):
    model = kind.model
    result = db.execute(
        update(model)
        .where(model.id == request_id, model.status == from_status)
        .values(status=to_status, **values)
    )
    if result.rowcount == 0:
        db.rollback()
        raise _failure(db, kind, request_id)
    db.add(
        kind.history(
            request_id=request_id,
            from_status=from_status,
            to_status=to_status,
            actor_type="staff",
            actor_id=staff.id,
            comment=comment,
        )
    )
    audit.record(
        db,
        staff_id=staff.id,
        action=f"{kind.name}.{action}",
        entity_type=kind.name,
        entity_id=request_id,
        details={"from": from_status, "to": to_status, **({"reason": comment} if action == "reject" else {})},
        ip=ip,
    )
    db.commit()
    return _load(db, kind, request_id)


def take(db: Session, kind: Kind, request_id: int, staff: StaffUser, ip: str | None = None):
    """pending → processing. Два оператора не возьмут одну заявку: второй получит
    invalid_transition."""
    return _move(
        db, kind, request_id, staff, action="take", from_status=kind.pending,
        to_status=kind.processing, values={"assigned_staff_id": staff.id}, ip=ip,
    )


def release(db: Session, kind: Kind, request_id: int, staff: StaffUser, ip: str | None = None):
    """processing → pending: вернуть в очередь (любой сотрудник с правом обработки)."""
    return _move(
        db, kind, request_id, staff, action="release", from_status=kind.processing,
        to_status=kind.pending, values={"assigned_staff_id": None}, ip=ip,
    )


def complete(db: Session, kind: Kind, request_id: int, staff: StaffUser, ip: str | None = None):
    """processing → completed."""
    return _move(
        db, kind, request_id, staff, action="complete", from_status=kind.processing,
        to_status=kind.completed, values={}, ip=ip,
    )


def reject(
    db: Session, kind: Kind, request_id: int, staff: StaffUser, reason: str, ip: str | None = None
):
    """processing → rejected. Причина обязательна, её увидит игрок."""
    reason = " ".join((reason or "").split())
    if not reason:
        raise ServiceError("reason_required")
    reason = reason[:MAX_REASON]
    return _move(
        db, kind, request_id, staff, action="reject", from_status=kind.processing,
        to_status=kind.rejected, values={"reject_reason": reason}, comment=reason,
        ip=ip,
    )
