from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, StrictInt

from app.models import (
    AuditLog,
    Bank,
    DepositRequest,
    PokerAccount,
    User,
    WithdrawalRequest,
)
from app.services.deposits import format_usdt


def _utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class PlayerRef(BaseModel):
    user_id: int
    telegram_id: int
    username: str | None
    first_name: str
    user_status: str
    player_id: str | None
    account_status: str | None

    @classmethod
    def build(cls, user: User, account: PokerAccount | None) -> "PlayerRef":
        return cls(
            user_id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            user_status=user.status,
            player_id=account.player_id if account else None,
            account_status=account.status if account else None,
        )


class HistoryItem(BaseModel):
    from_status: str | None
    to_status: str
    actor_type: str
    actor_id: int | None
    comment: str | None
    created_at: datetime


def _history(rows) -> list[HistoryItem]:
    return [
        HistoryItem(
            from_status=r.from_status, to_status=r.to_status, actor_type=r.actor_type,
            actor_id=r.actor_id, comment=r.comment, created_at=_utc(r.created_at),
        )
        for r in rows
    ]


class ReceiptInfo(BaseModel):
    uploaded_at: datetime | None
    content_type: str | None
    size: int | None
    # False: чека не было или он уже удалён по сроку хранения (Q-23).
    available: bool


class DepositAdminOut(BaseModel):
    id: int
    status: str
    method: str
    amount: int
    usdt_amount: str | None
    exchange_rate: str | None
    commission_percent: str
    commission_amount: int
    credit_amount: int
    payment_details: dict | None
    player: PlayerRef
    assigned_staff_id: int | None
    reject_reason: str | None
    receipt: ReceiptInfo
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    history: list[HistoryItem] | None = None

    @classmethod
    def build(cls, r: DepositRequest, user: User, account: PokerAccount, history=None):
        return cls(
            id=r.id, status=r.status, method=r.method, amount=r.amount,
            usdt_amount=format_usdt(r.crypto_amount) if r.crypto_amount is not None else None,
            exchange_rate=r.exchange_rate, commission_percent=r.commission_percent,
            commission_amount=r.commission_amount, credit_amount=r.amount + r.commission_amount,
            payment_details=r.payment_details, player=PlayerRef.build(user, account),
            assigned_staff_id=r.assigned_staff_id, reject_reason=r.reject_reason,
            receipt=ReceiptInfo(
                uploaded_at=_utc(r.receipt_uploaded_at), content_type=r.receipt_content_type,
                size=r.receipt_size,
                available=r.receipt_filename is not None and r.receipt_deleted_at is None,
            ),
            expires_at=_utc(r.expires_at), created_at=_utc(r.created_at),
            updated_at=_utc(r.updated_at),
            history=_history(history) if history is not None else None,
        )


class WithdrawalAdminOut(BaseModel):
    id: int
    status: str
    method: str
    amount: int
    commission_percent: str
    commission_amount: int
    payout_amount: int
    holder_name: str | None
    bank_name: str | None
    payment_details: dict | None
    player: PlayerRef
    assigned_staff_id: int | None
    reject_reason: str | None
    created_at: datetime
    updated_at: datetime
    history: list[HistoryItem] | None = None

    @classmethod
    def build(cls, r: WithdrawalRequest, user: User, account: PokerAccount, history=None):
        return cls(
            id=r.id, status=r.status, method=r.method, amount=r.amount,
            commission_percent=r.commission_percent, commission_amount=r.commission_amount,
            payout_amount=r.amount + r.commission_amount, holder_name=r.holder_name,
            bank_name=r.bank_name, payment_details=r.payment_details,
            player=PlayerRef.build(user, account), assigned_staff_id=r.assigned_staff_id,
            reject_reason=r.reject_reason, created_at=_utc(r.created_at),
            updated_at=_utc(r.updated_at),
            history=_history(history) if history is not None else None,
        )


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class PlayerDetailOut(BaseModel):
    player: PlayerRef
    block_reason: str | None
    duplicate_id_attempts: int
    reject_reason: str | None
    registered_at: datetime
    deposits: list[DepositAdminOut]
    withdrawals: list[WithdrawalAdminOut]


class AuditOut(BaseModel):
    id: int
    staff_id: int | None
    action: str
    entity_type: str | None
    entity_id: str | None
    details: dict[str, Any] | None
    ip: str | None
    created_at: datetime

    @classmethod
    def build(cls, row: AuditLog) -> "AuditOut":
        return cls(
            id=row.id, staff_id=row.staff_id, action=row.action, entity_type=row.entity_type,
            entity_id=row.entity_id, details=row.details, ip=row.ip, created_at=_utc(row.created_at),
        )


class PageOut(BaseModel):
    items: list
    total: int
    limit: int
    offset: int


class SettingsUpdate(BaseModel):
    # Только изменяемые ключи; допустимые значения проверяет сервис.
    settings: dict[str, StrictInt | str] = Field(min_length=1)


class BankAdminOut(BaseModel):
    id: int
    name: str
    is_active: bool
    sort_order: int

    @classmethod
    def build(cls, bank: Bank) -> "BankAdminOut":
        return cls(id=bank.id, name=bank.name, is_active=bank.is_active, sort_order=bank.sort_order)


class CreateBank(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class UpdateBank(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10_000)
