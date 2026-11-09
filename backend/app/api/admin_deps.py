from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import has_permission
from app.db.session import get_db
from app.models import StaffUser
from app.services import staff as staff_service

_bearer = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> str | None:
    """Адрес сотрудника для аудита. За доверенным nginx это X-Real-IP (Q-52), иначе адрес соединения."""
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-real-ip", "").strip()
        if forwarded and len(forwarded) <= 45:
            return forwarded
    return request.client.host if request.client else None


def current_staff(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> StaffUser:
    staff = (
        staff_service.staff_from_access_token(db, credentials.credentials)
        if credentials is not None
        else None
    )
    if staff is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "unauthorized"})
    return staff


def require_permission(permission: str):
    """Зависимость: сотрудник должен быть вошедшим и иметь право `permission`."""

    def dependency(staff: StaffUser = Depends(current_staff)) -> StaffUser:
        if not has_permission(staff.role, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "forbidden"})
        return staff

    return dependency
