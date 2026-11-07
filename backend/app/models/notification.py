from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notification(Base):
    """Очередь уведомлений игрокам (этап 7).

    Запись создаётся в той же транзакции, что и смена статуса, поэтому уведомление не
    теряется и не отправляется для отменённого действия. Бот забирает записи, отправляет
    сообщения в Telegram и подтверждает доставку. В `payload` только числа, статусы и
    причина отказа: ни реквизитов, ни токенов.
    """

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_queue", "sent_at", "failed_at", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(16))  # deposit | withdrawal | account
    payload: Mapped[dict] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Следующая попытка; пока запись выдана боту, здесь время окончания «аренды».
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
