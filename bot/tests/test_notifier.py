import asyncio

import pytest

pytest.importorskip("aiogram")

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter  # noqa: E402

from botapp import notifier  # noqa: E402


class FakeApi:
    def __init__(self, items=()):
        self.items, self.sent, self.failed = list(items), [], []

    async def claim_notifications(self, limit):
        items, self.items = self.items, []
        return items

    async def notification_sent(self, nid):
        self.sent.append(nid)

    async def notification_failed(self, nid, *, permanent, error="", retry_after=None):
        self.failed.append((nid, permanent, error, retry_after))


class FakeBot:
    def __init__(self, error=None):
        self.error, self.messages = error, []

    async def send_message(self, chat_id, text, reply_markup=None):
        if self.error:
            raise self.error
        self.messages.append((chat_id, text))


ITEM = {
    "id": 1, "kind": "account", "telegram_id": 42,
    "payload": {"status": "unblocked", "reason": None},
}


def run(coro):
    return asyncio.run(coro)


def test_successful_delivery_is_confirmed(monkeypatch):
    monkeypatch.setattr(notifier, "SEND_PAUSE", 0)
    api, bot = FakeApi([ITEM]), FakeBot()
    assert run(notifier.run_once(bot, api)) == 1
    assert bot.messages[0][0] == 42 and api.sent == [1] and api.failed == []


def test_blocked_bot_is_permanent_failure(monkeypatch):
    monkeypatch.setattr(notifier, "SEND_PAUSE", 0)
    api = FakeApi([ITEM])
    bot = FakeBot(TelegramForbiddenError(method=None, message="Forbidden: bot was blocked by the user"))
    run(notifier.run_once(bot, api))
    assert api.failed == [(1, True, "forbidden", None)] and api.sent == []


def test_flood_control_is_transient_with_retry_after(monkeypatch):
    monkeypatch.setattr(notifier, "SEND_PAUSE", 0)
    api = FakeApi([ITEM])
    bot = FakeBot(TelegramRetryAfter(method=None, message="Flood", retry_after=17))
    run(notifier.run_once(bot, api))
    assert api.failed == [(1, False, "flood_control", 17)]


def test_unknown_notification_type_is_closed_without_sending(monkeypatch):
    monkeypatch.setattr(notifier, "SEND_PAUSE", 0)
    api, bot = FakeApi([{**ITEM, "kind": "promo"}]), FakeBot()
    run(notifier.run_once(bot, api))
    assert bot.messages == [] and api.failed[0][:2] == (1, True)
