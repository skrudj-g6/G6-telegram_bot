from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.errors import ServiceError

# Код бизнес-ошибки → HTTP-статус. Бот ориентируется на `detail.code`.
STATUS_BY_CODE = {
    "user_not_found": 404,
    "account_not_found": 404,
    "request_not_found": 404,
    "invalid_player_id": 422,
    "reason_required": 422,
    "invalid_method": 422,
    "invalid_amount": 422,
    "amount_out_of_range": 422,
    "invalid_receipt": 422,
    "receipt_too_large": 413,
    "player_id_taken": 409,
    "account_locked": 409,
    "invalid_transition": 409,
    "deposit_awaiting_receipt": 409,
    "request_expired": 409,
    "user_blocked": 403,
    "account_not_approved": 403,
    # Платёжка не подключена или нет свободных реквизитов: попробовать позже (Q-22).
    "no_requisites_available": 503,
    # Владелец ещё не задал курс USDT в панели: крипта временно недоступна.
    "exchange_rate_unavailable": 503,
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=STATUS_BY_CODE.get(exc.code, 400),
            content={"detail": {"code": exc.code, **exc.extra}},
        )
