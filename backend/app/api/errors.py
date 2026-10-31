from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.errors import ServiceError

# Код бизнес-ошибки → HTTP-статус. Бот ориентируется на `detail.code`.
STATUS_BY_CODE = {
    "user_not_found": 404,
    "account_not_found": 404,
    "invalid_player_id": 422,
    "reason_required": 422,
    "player_id_taken": 409,
    "account_locked": 409,
    "invalid_transition": 409,
    "user_blocked": 403,
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=STATUS_BY_CODE.get(exc.code, 400),
            content={"detail": {"code": exc.code}},
        )
