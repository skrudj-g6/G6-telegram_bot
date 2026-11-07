from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_bot_token
from app.db.session import get_db
from app.schemas.notifications import FailedRequest, NotificationOut
from app.services import notifications

router = APIRouter(
    prefix="/bot/v1/notifications",
    tags=["bot-notifications"],
    dependencies=[Depends(require_bot_token)],
)


@router.post("/claim", response_model=list[NotificationOut])
def claim(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    """Бот забирает готовые уведомления. Они «арендуются» на 2 минуты: если бот не
    подтвердил доставку, запись вернётся в очередь."""
    return [NotificationOut.from_model(n) for n in notifications.claim(db, limit)]


@router.post("/{notification_id}/sent", status_code=status.HTTP_204_NO_CONTENT)
def sent(notification_id: int, db: Session = Depends(get_db)):
    notifications.mark_sent(db, notification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{notification_id}/failed", status_code=status.HTTP_204_NO_CONTENT)
def failed(notification_id: int, payload: FailedRequest, db: Session = Depends(get_db)):
    notifications.mark_failed(
        db,
        notification_id,
        permanent=payload.permanent,
        error=payload.error,
        retry_after=payload.retry_after_seconds,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
