from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_bot_token
from app.db.session import get_db
from app.schemas.withdrawals import (
    BankOut,
    CreateWithdrawalRequest,
    WithdrawalOut,
    WithdrawalQuoteOut,
)
from app.services import withdrawals

router = APIRouter(
    prefix="/bot/v1",
    tags=["bot-withdrawals"],
    dependencies=[Depends(require_bot_token)],
)

TelegramId = Annotated[int, Path(gt=0)]
RequestId = Annotated[int, Path(gt=0)]


@router.get("/banks", response_model=list[BankOut])
def list_banks(db: Session = Depends(get_db)):
    """Банки для вывода (Q-28), список редактируется в панели."""
    return withdrawals.list_banks(db)


@router.get("/quotes/withdrawal", response_model=WithdrawalQuoteOut)
def quote_withdrawal(amount: Annotated[int, Query(gt=0, le=10**12)], db: Session = Depends(get_db)):
    """Сколько игрок получит с учётом процента клуба: бот показывает до подтверждения."""
    return withdrawals.quote(db, amount)


@router.post("/users/{telegram_id}/withdrawals", response_model=WithdrawalOut)
def create_withdrawal(
    telegram_id: TelegramId,
    payload: CreateWithdrawalRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """201 — заявка создана, 200 — повтор запроса с тем же idempotency_key."""
    request, created = withdrawals.create_withdrawal(
        db,
        telegram_id=telegram_id,
        method=payload.method,
        amount=payload.amount,
        holder_name=payload.holder_name,
        bank_id=payload.bank_id,
        idempotency_key=payload.idempotency_key,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return WithdrawalOut.from_model(request)


@router.get("/users/{telegram_id}/withdrawals", response_model=list[WithdrawalOut])
def list_withdrawals(telegram_id: TelegramId, db: Session = Depends(get_db)):
    return [
        WithdrawalOut.from_model(r)
        for r in withdrawals.list_withdrawals(db, telegram_id=telegram_id)
    ]


@router.get("/users/{telegram_id}/withdrawals/{request_id}", response_model=WithdrawalOut)
def get_withdrawal(telegram_id: TelegramId, request_id: RequestId, db: Session = Depends(get_db)):
    return WithdrawalOut.from_model(
        withdrawals.get_withdrawal(db, telegram_id=telegram_id, request_id=request_id)
    )


@router.post("/users/{telegram_id}/withdrawals/{request_id}/cancel", response_model=WithdrawalOut)
def cancel_withdrawal(
    telegram_id: TelegramId, request_id: RequestId, db: Session = Depends(get_db)
):
    return WithdrawalOut.from_model(
        withdrawals.cancel_withdrawal(db, telegram_id=telegram_id, request_id=request_id)
    )
