from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt, model_validator

from app.models import DepositRequest, DepositStatus
from app.services.deposits import format_usdt


def _utc(value: datetime) -> datetime:
    # SQLite (тесты) возвращает даты без часового пояса; в БД они всегда в UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class CreateDepositRequest(BaseModel):
    method: Literal["fiat", "crypto"]
    # fiat: целые тенге (строки и дроби не принимаются).
    amount: Annotated[StrictInt, Field(gt=0, le=10**12)] | None = None
    # crypto: количество USDT, не более двух знаков после запятой. Сумма в тенге
    # считается на backend по курсу.
    usdt_amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)] | None = None
    # Уникальный ключ попытки (бот генерирует UUID): повтор запроса не создаёт вторую заявку.
    idempotency_key: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")

    @model_validator(mode="after")
    def _exactly_one_amount_for_method(self) -> "CreateDepositRequest":
        if self.method == "fiat" and (self.amount is None or self.usdt_amount is not None):
            raise ValueError("Для fiat укажите только amount (тенге)")
        if self.method == "crypto" and (self.usdt_amount is None or self.amount is not None):
            raise ValueError("Для crypto укажите только usdt_amount")
        return self


class DepositOut(BaseModel):
    id: int
    method: str
    # Всегда в тенге; для crypto — эквивалент по курсу заявки.
    amount: int
    # Только для crypto: сколько USDT оплатить и по какому курсу посчитаны тенге.
    usdt_amount: str | None
    exchange_rate: str | None
    # Комиссия клуба (Q-33): игрок платит amount, на счёт зачисляется credit_amount.
    commission_percent: str
    commission_amount: int
    credit_amount: int
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
            usdt_amount=(
                format_usdt(request.crypto_amount) if request.crypto_amount is not None else None
            ),
            exchange_rate=request.exchange_rate,
            commission_percent=request.commission_percent,
            commission_amount=request.commission_amount,
            credit_amount=request.amount - request.commission_amount,
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


class CommissionOut(BaseModel):
    # Проценты строкой, например "2.5".
    deposit: str
    withdrawal: str


class LimitsOut(BaseModel):
    deposit: LimitOut
    withdrawal: LimitOut
    commission: CommissionOut


class UsdtQuoteOut(BaseModel):
    usdt_amount: str
    # Тенге за 1 USDT.
    rate: str
    kzt_amount: int
    min: int
    max: int
    within_limits: bool
    commission_percent: str
    commission_amount: int
    credit_amount: int
