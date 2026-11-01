from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt, model_validator

from app.models import WithdrawalRequest


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class BankOut(BaseModel):
    id: int
    name: str


class CreateWithdrawalRequest(BaseModel):
    method: Literal["fiat", "crypto"]
    # Целые тенге; для crypto сумма тоже в тенге (Q-2), остальное запрашивает PSP (Q-31).
    amount: Annotated[StrictInt, Field(gt=0, le=10**12)]
    # Только fiat (Q-24): имя получателя и банк из списка.
    holder_name: str | None = Field(default=None, max_length=200)
    bank_id: StrictInt | None = None
    idempotency_key: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")

    @model_validator(mode="after")
    def _fields_match_method(self) -> "CreateWithdrawalRequest":
        if self.method == "fiat" and (self.holder_name is None or self.bank_id is None):
            raise ValueError("Для fiat укажите holder_name и bank_id")
        if self.method == "crypto" and (self.holder_name is not None or self.bank_id is not None):
            raise ValueError("Для crypto укажите только amount")
        return self


class WithdrawalOut(BaseModel):
    id: int
    method: str
    # Списывается с игрового счёта.
    amount: int
    # Процент клуба со знаком (+ бонус, − комиссия) и сколько игрок получит.
    commission_percent: str
    commission_amount: int
    payout_amount: int
    holder_name: str | None
    bank_name: str | None
    # crypto: данные от PSP.
    payment_details: dict | None
    status: str
    reject_reason: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, request: WithdrawalRequest) -> "WithdrawalOut":
        return cls(
            id=request.id,
            method=request.method,
            amount=request.amount,
            commission_percent=request.commission_percent,
            commission_amount=request.commission_amount,
            payout_amount=request.amount + request.commission_amount,
            holder_name=request.holder_name,
            bank_name=request.bank_name,
            payment_details=request.payment_details,
            status=request.status,
            reject_reason=request.reject_reason,
            created_at=_utc(request.created_at),
        )


class WithdrawalQuoteOut(BaseModel):
    amount: int
    min: int
    max: int
    within_limits: bool
    commission_percent: str
    commission_amount: int
    payout_amount: int
