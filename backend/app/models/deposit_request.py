from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column


from app.db.base import Base


class DepositStatus:
    AWAITING_RECEIPT = "awaiting_receipt"  # реквизиты выданы, ждём чек
    PENDING = "pending"  # чек получен, заявка в очереди оператора
    PROCESSING = "processing"  # оператор взял в работу
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"  # отменена игроком до чека (Q-5)
    EXPIRED = "expired"  # чек не прислан за отведённое время (Q-9)


class DepositMethod:
    FIAT = "fiat"
    CRYPTO = "crypto"

    ALL = (FIAT, CRYPTO)


class DepositRequest(Base):
    __tablename__ = "deposit_requests"
    __table_args__ = (
        # Повтор того же запроса бота (ретрай, двойной тап) не создаёт вторую заявку.
        UniqueConstraint("user_id", "idempotency_key", name="uq_deposit_requests_user_idempotency"),
        CheckConstraint(
            "status IN ('awaiting_receipt', 'pending', 'processing', 'completed',"
            " 'rejected', 'cancelled', 'expired')",
            name="status_valid",
        ),
        CheckConstraint("method IN ('fiat', 'crypto')", name="method_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "status <> 'rejected' OR reject_reason IS NOT NULL", name="reject_reason_required"
        ),
        # Выборка для таймера автозакрытия.
        Index("ix_deposit_requests_status_expires_at", "status", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Какой игровой аккаунт пополняется (на момент создания заявки).
    poker_account_id: Mapped[int] = mapped_column(ForeignKey("poker_accounts.id"))
    method: Mapped[str] = mapped_column(String(16))
    # Целые тенге (ТЗ §2). Для крипты — эквивалент введённой суммы USDT по курсу заявки.
    amount: Mapped[int] = mapped_column(BigInteger)
    # Только для crypto: сумма USDT в сотых (1 USDT = 100) и курс на момент создания
    # (тенге за 1 USDT, строкой). Курс фиксируется: позже он на заявку не влияет.
    crypto_amount: Mapped[int | None] = mapped_column(BigInteger)
    exchange_rate: Mapped[str | None] = mapped_column(String(32))
    # Комиссия клуба на пополнение (Q-33): процент на момент создания заявки и сумма в
    # целых тенге. На игровой счёт зачисляется amount - commission_amount.
    commission_percent: Mapped[str] = mapped_column(String(8), default="0", server_default="0")
    commission_amount: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    status: Mapped[str] = mapped_column(
        String(20),
        default=DepositStatus.AWAITING_RECEIPT,
        server_default=DepositStatus.AWAITING_RECEIPT,
    )
    # Снимок реквизитов, присланных платёжкой (Q-8). Меняться потом не должен.
    payment_details: Mapped[dict] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    # До этого момента игрок может прислать чек; позже заявка закрывается (Q-9).
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Чек (Q-23): файл лежит на диске, в БД — только имя и метаданные.
    receipt_filename: Mapped[str | None] = mapped_column(String(64))
    receipt_content_type: Mapped[str | None] = mapped_column(String(32))
    receipt_size: Mapped[int | None] = mapped_column(Integer)
    receipt_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Заполняется, когда файл удалён по сроку хранения.
    receipt_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Оператор. FK на staff_users добавится на этапе 5.
    assigned_staff_id: Mapped[int | None] = mapped_column(BigInteger)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
