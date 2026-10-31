from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppSetting(Base):
    """Настройки, которые владелец меняет в панели (лимиты, таймауты; Q-6, Q-9, Q-23)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Кто изменил. FK на staff_users добавится на этапе 5.
    updated_by_staff_id: Mapped[int | None] = mapped_column(BigInteger)
