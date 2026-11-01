from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.admin_deps import client_ip, require_permission
from app.core import permissions
from app.db.session import get_db
from app.models import StaffUser
from app.schemas.admin import DepositAdminOut, PageOut, RejectRequest, WithdrawalAdminOut
from app.services import admin_views, audit, receipt_storage, request_processing as rp
from app.services.errors import ServiceError

router = APIRouter(prefix="/admin/v1", tags=["admin-requests"])

Viewer = Depends(require_permission(permissions.REQUESTS_VIEW))
Processor = Depends(require_permission(permissions.REQUESTS_PROCESS))
ReceiptViewer = Depends(require_permission(permissions.RECEIPTS_VIEW))


def _register(kind: rp.Kind, plural: str, out_cls) -> None:
    prefix = f"/{plural}"

    @router.get(prefix, response_model=PageOut, name=f"list_{plural}")
    def list_items(
        status: str | None = Query(default=None, max_length=20),
        method: str | None = Query(default=None, pattern="^(fiat|crypto)$"),
        q: str | None = Query(default=None, max_length=64),
        oldest_first: bool = False,
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        _: StaffUser = Viewer,
        db: Session = Depends(get_db),
    ):
        page = admin_views.list_requests(
            db, kind, status=status, method=method, q=q, oldest_first=oldest_first,
            limit=limit, offset=offset,
        )
        return PageOut(
            items=[out_cls.build(r, u, a) for r, u, a in page.items],
            total=page.total, limit=page.limit, offset=page.offset,
        )

    @router.get(prefix + "/{request_id}", response_model=out_cls, name=f"get_{kind.name}")
    def get_item(request_id: int, _: StaffUser = Viewer, db: Session = Depends(get_db)):
        request, user, account, history = admin_views.get_request(db, kind, request_id)
        return out_cls.build(request, user, account, history)

    def _action(name: str):
        def handler(
            request_id: int,
            request: Request,
            staff: StaffUser = Processor,
            db: Session = Depends(get_db),
        ):
            getattr(rp, name)(db, kind, request_id, staff, ip=client_ip(request))
            row, user, account, history = admin_views.get_request(db, kind, request_id)
            return out_cls.build(row, user, account, history)

        handler.__name__ = f"{name}_{kind.name}"
        return handler

    for action in ("take", "release", "complete"):
        router.post(
            f"{prefix}/{{request_id}}/{action}", response_model=out_cls, name=f"{action}_{kind.name}"
        )(_action(action))

    @router.post(prefix + "/{request_id}/reject", response_model=out_cls, name=f"reject_{kind.name}")
    def reject_item(
        request_id: int,
        payload: RejectRequest,
        request: Request,
        staff: StaffUser = Processor,
        db: Session = Depends(get_db),
    ):
        rp.reject(db, kind, request_id, staff, payload.reason, ip=client_ip(request))
        row, user, account, history = admin_views.get_request(db, kind, request_id)
        return out_cls.build(row, user, account, history)


_register(rp.DEPOSIT, "deposits", DepositAdminOut)
_register(rp.WITHDRAWAL, "withdrawals", WithdrawalAdminOut)


@router.get("/deposits/{request_id}/receipt")
def get_receipt(
    request_id: int,
    request: Request,
    staff: StaffUser = ReceiptViewer,
    db: Session = Depends(get_db),
):
    """Чек игрока. Доступ только по праву receipts.view, каждый просмотр пишется в аудит."""
    deposit, _, _, _ = admin_views.get_request(db, rp.DEPOSIT, request_id)
    if deposit.receipt_filename is None or deposit.receipt_deleted_at is not None:
        raise ServiceError("receipt_not_available")
    path: Path = receipt_storage.path_for(deposit.receipt_filename)
    if not path.is_file():
        raise ServiceError("receipt_not_available")
    audit.record(
        db, staff_id=staff.id, action="receipt.view", entity_type="deposit",
        entity_id=request_id, ip=client_ip(request),
    )
    db.commit()
    return FileResponse(
        path,
        media_type=deposit.receipt_content_type or "application/octet-stream",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )
