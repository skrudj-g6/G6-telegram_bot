from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.admin_deps import client_ip, current_staff
from app.core.config import get_settings
from app.core.permissions import PERMISSIONS
from app.db.session import get_db
from app.models import StaffUser
from app.schemas.staff import ChangePasswordRequest, LoginRequest, StaffOut, TokenOut
from app.services import staff as staff_service

router = APIRouter(prefix="/admin/v1/auth", tags=["admin-auth"])

COOKIE_NAME = "refresh_token"


def _staff_out(staff: StaffUser) -> StaffOut:
    return StaffOut.from_model(staff, sorted(PERMISSIONS.get(staff.role, ())))


def _set_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.refresh_token_days * 24 * 3600,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        path="/admin/v1/auth",
    )


def _token_out(staff: StaffUser) -> TokenOut:
    access, ttl = staff_service.issue_access_token(staff)
    return TokenOut(access_token=access, expires_in=ttl, staff=_staff_out(staff))


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    staff, refresh_token = staff_service.login(
        db, login=payload.login, password=payload.password, ip=client_ip(request)
    )
    _set_cookie(response, refresh_token)
    return _token_out(staff)


@router.post("/refresh", response_model=TokenOut)
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    staff, new_token = staff_service.refresh(db, token=refresh_token or "", ip=client_ip(request))
    _set_cookie(response, new_token)
    return _token_out(staff)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    staff_service.logout(db, token=refresh_token or "")
    response.delete_cookie(COOKIE_NAME, path="/admin/v1/auth")


@router.get("/me", response_model=StaffOut)
def me(staff: StaffUser = Depends(current_staff)):
    return _staff_out(staff)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    staff: StaffUser = Depends(current_staff),
    db: Session = Depends(get_db),
):
    staff_service.change_own_password(
        db,
        staff=staff,
        current=payload.current_password,
        new=payload.new_password,
        ip=client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
