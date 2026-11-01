"""Проверка, что бот собирается: роутеры импортируются, фильтры строятся."""

import pytest

pytest.importorskip("aiogram")
pytest.importorskip("httpx")

from botapp.api import BackendClient  # noqa: E402
from botapp.config import Config  # noqa: E402
from botapp.main import build_dispatcher  # noqa: E402


def test_dispatcher_builds_with_all_routers():
    config = Config.from_env({"BOT_TOKEN": "123:abc", "BOT_SERVICE_TOKEN": "x" * 20})
    api = BackendClient(config.backend_url, config.service_token)
    dp = build_dispatcher(config, api)
    names = {r.name for r in dp.sub_routers}
    assert names == {"start", "registration", "deposit", "withdraw", "requests", "receipts"}
    assert {"message", "callback_query"} <= set(dp.resolve_used_update_types())
