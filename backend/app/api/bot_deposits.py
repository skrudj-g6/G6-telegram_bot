from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_bot_token
from app.db.session import get_db
from app.schemas.deposits import CreateDepositRequest, DepositOut, LimitsOut, UsdtQuoteOut
from app.services import app_settings, deposits
from app.services.receipt_storage import MAX_RECEIPT_BYTES

# Внутренний API для бота; все маршруты требуют токен сервиса (D-3).
router = APIRouter(
    prefix="/bot/v1",
    tags=["bot-deposits"],
    dependencies=[Depends(require_bot_token)],
)

TelegramId = Annotated[int, Path(gt=0)]
RequestId = Annotated[int, Path(gt=0)]


@router.get("/settings/limits", response_model=LimitsOut)
def get_limits(db: Session = Depends(get_db)):
    """Лимиты сумм, настраиваемые в панели (Q-6): бот показывает их игроку."""
    return app_settings.get_limits(db)


@router.get("/quotes/usdt-deposit", response_model=UsdtQuoteOut)
def quote_usdt_deposit(
    usdt_amount: Annotated[Decimal, Query(gt=0, max_digits=12, decimal_places=2)],
    db: Session = Depends(get_db),
):
    """Сколько тенге получится за введённые USDT: бот показывает это до подтверждения."""
    return deposits.quote_usdt(db, usdt_amount)


@router.post("/users/{telegram_id}/deposits", response_model=DepositOut)
def create_deposit(
    telegram_id: TelegramId,
    payload: CreateDepositRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """201 — заявка создана, 200 — повтор запроса с тем же idempotency_key."""
    request, created = deposits.create_deposit(
        db,
        telegram_id=telegram_id,
        method=payload.method,
        amount=payload.amount,
        usdt_amount=payload.usdt_amount,
        idempotency_key=payload.idempotency_key,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return DepositOut.from_model(request)


@router.get("/users/{telegram_id}/deposits", response_model=list[DepositOut])
def list_deposits(telegram_id: TelegramId, db: Session = Depends(get_db)):
    """«Мои заявки»: последние 20, новые первыми."""
    return [
        DepositOut.from_model(r) for r in deposits.list_deposits(db, telegram_id=telegram_id)
    ]


@router.get("/users/{telegram_id}/deposits/{request_id}", response_model=DepositOut)
def get_deposit(telegram_id: TelegramId, request_id: RequestId, db: Session = Depends(get_db)):
    return DepositOut.from_model(
        deposits.get_deposit(db, telegram_id=telegram_id, request_id=request_id)
    )


@router.post("/users/{telegram_id}/deposits/{request_id}/cancel", response_model=DepositOut)
def cancel_deposit(telegram_id: TelegramId, request_id: RequestId, db: Session = Depends(get_db)):
    """Отмена игроком — только до отправки чека (Q-5)."""
    return DepositOut.from_model(
        deposits.cancel_deposit(db, telegram_id=telegram_id, request_id=request_id)
    )


@router.post("/users/{telegram_id}/deposits/{request_id}/receipt", response_model=DepositOut)
def upload_receipt(
    telegram_id: TelegramId,
    request_id: RequestId,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Чек: JPEG, PNG или PDF до 10 МБ. После этого заявка уходит оператору."""
    data = file.file.read(MAX_RECEIPT_BYTES + 1)
    return DepositOut.from_model(
        deposits.attach_receipt(db, telegram_id=telegram_id, request_id=request_id, data=data)
    )
