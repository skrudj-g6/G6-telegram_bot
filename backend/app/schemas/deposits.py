from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, StrictInt

from app.models import DepositRequest, DepositStatus


def _utc(value: datetime) -> datetime:
    # SQLite (тесты) возвращает даты без часового пояса; в БД они всегда в UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class CreateDepositRequest(BaseModel):
    method: Literal["fiat", "crypto"]
    # Целые тенге; строки и дроби не принимаются.
    amount: StrictInt = Field(gt=0, le=10**12)
    # Уникальный ключ попытки (бот генерирует UUID): повтор запроса не создаёт вторую заявку.
    idempotency_key: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class DepositOut(BaseModel):
    id: int
    method: str
    amount: int
    status: str
    # Реквизиты показываются, только пока ждём чек.
    payment_details: dict | None
    expires_at: datetime
    receipt_uploaded: bool
    reject_reason: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, request: DepositRequest) -> "DepositOut":
        awaiting = request.status == DepositStatus.AWAITING_RECEIPT
        return cls(
            id=request.id,
            method=request.method,
            amount=request.amount,
            status=request.status,
            payment_details=request.payment_details if awaiting else None,
            expires_at=_utc(request.expires_at),
            receipt_uploaded=request.receipt_uploaded_at is not None,
            reject_reason=request.reject_reason,
            created_at=_utc(request.created_at),
        )


class LimitOut(BaseModel):
    min: int
    max: int


class LimitsOut(BaseModel):
    deposit: LimitOut
    withdrawal: LimitOut
