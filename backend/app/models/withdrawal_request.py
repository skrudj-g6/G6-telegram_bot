from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WithdrawalStatus:
    PENDING = "pending"  # создана игроком, ждёт оператора
    PROCESSING = "processing"  # оператор взял в работу (этап 5)
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"  # отменена игроком, пока оператор не взял в работу

    OPEN = (PENDING, PROCESSING)


class WithdrawalMethod:
    FIAT = "fiat"
    CRYPTO = "crypto"

    ALL = (FIAT, CRYPTO)


class WithdrawalRequest(Base):
    __tablename__ = "withdrawal_requests"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_withdrawal_requests_user_idempotency"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'rejected', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint("method IN ('fiat', 'crypto')", name="method_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "status <> 'rejected' OR reject_reason IS NOT NULL", name="reject_reason_required"
        ),
        Index("ix_withdrawal_requests_status_created_at", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    poker_account_id: Mapped[int] = mapped_column(ForeignKey("poker_accounts.id"))
    method: Mapped[str] = mapped_column(String(16))
    # Целые тенге, которые игрок выводит с игрового счёта (ТЗ §2).
    amount: Mapped[int] = mapped_column(BigInteger)
    # Процент клуба на вывод со знаком (+ бонус, − комиссия) и корректировка в тенге на момент
    # создания заявки (Q-33/Q-34/Q-35). Игрок получает amount + commission_amount.
    commission_percent: Mapped[str] = mapped_column(String(8), default="0", server_default="0")
    commission_amount: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    # Только fiat (Q-24): имя получателя и банк (название сохраняется как было на момент заявки).
    holder_name: Mapped[str | None] = mapped_column(String(120))
    bank_id: Mapped[int | None] = mapped_column(ForeignKey("banks.id"))
    bank_name: Mapped[str | None] = mapped_column(String(100))
    # Только crypto (Q-31): данные, которые вернул PSP.
    payment_details: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(20), default=WithdrawalStatus.PENDING, server_default=WithdrawalStatus.PENDING
    )
    idempotency_key: Mapped[str] = mapped_column(String(64))
    assigned_staff_id: Mapped[int | None] = mapped_column(BigInteger)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
