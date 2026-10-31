from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.club import Club
    from app.models.user import User


class PokerAccountStatus:
    PENDING = "pending"      # привязан игроком, ждёт подтверждения админом
    APPROVED = "approved"    # принят в клуб
    REJECTED = "rejected"    # отклонён админом


class PokerAccount(Base):
    __tablename__ = "poker_accounts"
    __table_args__ = (
        # Один игровой ID — один игрок (ТЗ §4.3).
        UniqueConstraint("club_id", "player_id", name="uq_poker_accounts_club_player"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')", name="status_valid"
        ),
        CheckConstraint("length(player_id) = 9", name="player_id_length"),
        CheckConstraint(
            "status <> 'rejected' OR reject_reason IS NOT NULL", name="reject_reason_required"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # unique=True: Q-1, один Telegram-игрок — один игровой аккаунт.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    player_id: Mapped[str] = mapped_column(String(9))
    status: Mapped[str] = mapped_column(
        String(20),
        default=PokerAccountStatus.PENDING,
        server_default=PokerAccountStatus.PENDING,
        index=True,
    )
    reject_reason: Mapped[str | None] = mapped_column(String(500))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="poker_account")
    club: Mapped["Club"] = relationship()
