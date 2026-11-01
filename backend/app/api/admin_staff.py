from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.admin_deps import client_ip, require_permission
from app.core import permissions
from app.db.session import get_db
from app.models import StaffUser
from app.schemas.staff import (
    CreateStaffRequest,
    ResetPasswordRequest,
    StaffOut,
    UpdateStaffRequest,
)
from app.services import staff as staff_service

router = APIRouter(prefix="/admin/v1/staff", tags=["admin-staff"])

Manager = Depends(require_permission(permissions.STAFF_MANAGE))


@router.get("", response_model=list[StaffOut])
def list_staff(_: StaffUser = Manager, db: Session = Depends(get_db)):
    return [StaffOut.from_model(s) for s in staff_service.list_staff(db)]


@router.post("", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
def create_staff(
    payload: CreateStaffRequest,
    request: Request,
    actor: StaffUser = Manager,
    db: Session = Depends(get_db),
):
    created = staff_service.create_staff(
        db,
        actor=actor,
        login=payload.login,
        display_name=payload.display_name,
        role=payload.role,
        password=payload.password,
        ip=client_ip(request),
    )
    return StaffOut.from_model(created)


@router.patch("/{staff_id}", response_model=StaffOut)
def update_staff(
    staff_id: int,
    payload: UpdateStaffRequest,
    request: Request,
    actor: StaffUser = Manager,
    db: Session = Depends(get_db),
):
    updated = staff_service.update_staff(
        db,
        actor=actor,
        staff_id=staff_id,
        role=payload.role,
        display_name=payload.display_name,
        is_active=payload.is_active,
        ip=client_ip(request),
    )
    return StaffOut.from_model(updated)


@router.post("/{staff_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    staff_id: int,
    payload: ResetPasswordRequest,
    request: Request,
    actor: StaffUser = Manager,
    db: Session = Depends(get_db),
):
    staff_service.reset_password(
        db,
        actor=actor,
        staff_id=staff_id,
        new_password=payload.new_password,
        ip=client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
