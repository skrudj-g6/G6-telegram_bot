from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.models import Notification


class NotificationOut(BaseModel):
    id: int
    telegram_id: int
    kind: str
    payload: dict
    attempts: int
    created_at: datetime

    @classmethod
    def from_model(cls, n: Notification) -> "NotificationOut":
        created = n.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return cls(
            id=n.id, telegram_id=n.telegram_id, kind=n.kind, payload=n.payload,
            attempts=n.attempts, created_at=created,
        )


class FailedRequest(BaseModel):
    # Повторять бессмысленно (например, игрок заблокировал бота).
    permanent: bool = False
    error: str = Field(default="", max_length=100)
    # Telegram просит подождать (flood control): не повторять раньше.
    retry_after_seconds: int | None = Field(default=None, ge=0, le=86400)
