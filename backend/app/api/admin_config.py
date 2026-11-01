from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.admin_deps import client_ip, require_permission
from app.core import permissions
from app.db.session import get_db
from app.models import StaffUser
from app.schemas.admin import (
    AuditOut,
    BankAdminOut,
    CreateBank,
    PageOut,
    SettingsUpdate,
    UpdateBank,
)
from app.services import admin_config, admin_views

router = APIRouter(prefix="/admin/v1", tags=["admin-config"])

SettingsViewer = Depends(require_permission(permissions.SETTINGS_VIEW))
SettingsEditor = Depends(require_permission(permissions.SETTINGS_EDIT))
AuditViewer = Depends(require_permission(permissions.AUDIT_VIEW))


@router.get("/settings")
def get_settings(_: StaffUser = SettingsViewer, db: Session = Depends(get_db)):
    return admin_config.view(db)


@router.put("/settings")
def update_settings(
    payload: SettingsUpdate,
    request: Request,
    staff: StaffUser = SettingsEditor,
    db: Session = Depends(get_db),
):
    """Лимиты, проценты, режим курса USDT. Тело: {"settings": {"deposit_min_amount": 2000}}."""
    return admin_config.update(db, staff=staff, changes=payload.settings, ip=client_ip(request))


@router.get("/banks", response_model=list[BankAdminOut])
def list_banks(_: StaffUser = SettingsViewer, db: Session = Depends(get_db)):
    return [BankAdminOut.build(b) for b in admin_config.list_banks(db)]


@router.post("/banks", response_model=BankAdminOut, status_code=status.HTTP_201_CREATED)
def create_bank(
    payload: CreateBank,
    request: Request,
    staff: StaffUser = SettingsEditor,
    db: Session = Depends(get_db),
):
    return BankAdminOut.build(
        admin_config.create_bank(db, staff=staff, name=payload.name, ip=client_ip(request))
    )


@router.patch("/banks/{bank_id}", response_model=BankAdminOut)
def update_bank(
    bank_id: int,
    payload: UpdateBank,
    request: Request,
    staff: StaffUser = SettingsEditor,
    db: Session = Depends(get_db),
):
    return BankAdminOut.build(
        admin_config.update_bank(
            db, staff=staff, bank_id=bank_id, name=payload.name, is_active=payload.is_active,
            sort_order=payload.sort_order, ip=client_ip(request),
        )
    )


@router.get("/audit", response_model=PageOut)
def list_audit(
    action: str | None = Query(default=None, max_length=64),
    staff_id: int | None = None,
    entity_type: str | None = Query(default=None, max_length=32),
    entity_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: StaffUser = AuditViewer,
    db: Session = Depends(get_db),
):
    page = admin_views.list_audit(
        db, action=action, staff_id=staff_id, entity_type=entity_type, entity_id=entity_id,
        limit=limit, offset=offset,
    )
    return PageOut(
        items=[AuditOut.build(r) for r in page.items],
        total=page.total, limit=page.limit, offset=page.offset,
    )
