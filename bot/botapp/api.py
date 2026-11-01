"""Клиент backend API. Бот не знает БД и бизнес-правил: он только показывает ответы backend."""

from decimal import Decimal

import httpx


class ApiError(Exception):
    """Ожидаемая ошибка backend: `code` стабилен, `extra` — дополнительные поля."""

    def __init__(self, code: str, status: int = 400, **extra):
        super().__init__(code)
        self.code = code
        self.status = status
        self.extra = extra


class ApiUnavailable(Exception):
    """Backend недоступен или ответил непонятно (сеть, 5xx без кода)."""


class BackendClient:
    def __init__(self, base_url: str, service_token: str, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=15.0)
        self._headers = {"X-Service-Token": service_token}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs):
        try:
            response = await self._client.request(method, path, headers=self._headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiUnavailable(type(exc).__name__) from exc
        if response.status_code < 400:
            return response.json()
        try:
            detail = response.json().get("detail")
        except (ValueError, AttributeError):
            detail = None
        if isinstance(detail, dict) and isinstance(detail.get("code"), str):
            extra = {k: v for k, v in detail.items() if k != "code"}
            raise ApiError(detail["code"], response.status_code, **extra)
        if response.status_code == 422:
            raise ApiError("validation_error", 422)
        raise ApiUnavailable(f"HTTP {response.status_code}")

    # --- Игрок ---

    async def register(self, telegram_id: int, username: str | None, first_name: str) -> dict:
        return await self._request(
            "POST",
            "/bot/v1/users/register",
            json={"telegram_id": telegram_id, "username": username, "first_name": first_name},
        )

    async def profile(self, telegram_id: int) -> dict | None:
        try:
            return await self._request("GET", f"/bot/v1/users/{telegram_id}")
        except ApiError as exc:
            if exc.code == "user_not_found":
                return None
            raise

    async def link_account(self, telegram_id: int, player_id: str) -> dict:
        return await self._request(
            "PUT", f"/bot/v1/users/{telegram_id}/poker-account", json={"player_id": player_id}
        )

    # --- Справочники ---

    async def limits(self) -> dict:
        return await self._request("GET", "/bot/v1/settings/limits")

    async def banks(self) -> list[dict]:
        return await self._request("GET", "/bot/v1/banks")

    async def usdt_quote(self, usdt_amount: Decimal | str) -> dict:
        return await self._request(
            "GET", "/bot/v1/quotes/usdt-deposit", params={"usdt_amount": str(usdt_amount)}
        )

    async def withdrawal_quote(self, amount: int) -> dict:
        return await self._request("GET", "/bot/v1/quotes/withdrawal", params={"amount": amount})

    # --- Пополнения ---

    async def create_deposit(
        self,
        telegram_id: int,
        *,
        method: str,
        key: str,
        amount: int | None = None,
        usdt_amount: str | None = None,
    ) -> dict:
        body: dict = {"method": method, "idempotency_key": key}
        if amount is not None:
            body["amount"] = amount
        if usdt_amount is not None:
            body["usdt_amount"] = usdt_amount
        return await self._request("POST", f"/bot/v1/users/{telegram_id}/deposits", json=body)

    async def list_deposits(self, telegram_id: int) -> list[dict]:
        return await self._request("GET", f"/bot/v1/users/{telegram_id}/deposits")

    async def get_deposit(self, telegram_id: int, request_id: int) -> dict:
        return await self._request("GET", f"/bot/v1/users/{telegram_id}/deposits/{request_id}")

    async def cancel_deposit(self, telegram_id: int, request_id: int) -> dict:
        return await self._request(
            "POST", f"/bot/v1/users/{telegram_id}/deposits/{request_id}/cancel"
        )

    async def upload_receipt(
        self, telegram_id: int, request_id: int, data: bytes, filename: str = "receipt"
    ) -> dict:
        return await self._request(
            "POST",
            f"/bot/v1/users/{telegram_id}/deposits/{request_id}/receipt",
            files={"file": (filename, data, "application/octet-stream")},
        )

    # --- Выводы ---

    async def create_withdrawal(
        self,
        telegram_id: int,
        *,
        method: str,
        amount: int,
        key: str,
        holder_name: str | None = None,
        bank_id: int | None = None,
    ) -> dict:
        body: dict = {"method": method, "amount": amount, "idempotency_key": key}
        if holder_name is not None:
            body["holder_name"] = holder_name
        if bank_id is not None:
            body["bank_id"] = bank_id
        return await self._request("POST", f"/bot/v1/users/{telegram_id}/withdrawals", json=body)

    async def list_withdrawals(self, telegram_id: int) -> list[dict]:
        return await self._request("GET", f"/bot/v1/users/{telegram_id}/withdrawals")

    async def get_withdrawal(self, telegram_id: int, request_id: int) -> dict:
        return await self._request("GET", f"/bot/v1/users/{telegram_id}/withdrawals/{request_id}")

    async def cancel_withdrawal(self, telegram_id: int, request_id: int) -> dict:
        return await self._request(
            "POST", f"/bot/v1/users/{telegram_id}/withdrawals/{request_id}/cancel"
        )
