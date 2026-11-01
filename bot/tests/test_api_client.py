import asyncio

import pytest

httpx = pytest.importorskip("httpx")

from botapp.api import ApiError, ApiUnavailable, BackendClient  # noqa: E402


def client_with(handler) -> BackendClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(base_url="http://backend", transport=transport)
    return BackendClient("http://backend", "service-token-0123456789", client=http)


def run(coro):
    return asyncio.run(coro)


def test_sends_service_token_and_json():
    seen = {}

    def handler(request):
        seen["token"] = request.headers["x-service-token"]
        seen["body"] = request.content
        return httpx.Response(201, json={"id": 1})

    api = client_with(handler)
    assert run(api.create_deposit(5, method="fiat", amount=5000, key="k" * 8)) == {"id": 1}
    assert seen["token"] == "service-token-0123456789"
    assert b'"amount":5000' in seen["body"].replace(b" ", b"")


def test_backend_error_becomes_api_error_with_extra():
    api = client_with(
        lambda r: httpx.Response(
            422, json={"detail": {"code": "amount_out_of_range", "min": 1000, "max": 2000000}}
        )
    )
    with pytest.raises(ApiError) as exc:
        run(api.create_deposit(5, method="fiat", amount=1, key="k" * 8))
    assert exc.value.code == "amount_out_of_range" and exc.value.extra == {"min": 1000, "max": 2000000}


def test_503_with_code_is_api_error_but_without_code_is_unavailable():
    coded = client_with(lambda r: httpx.Response(503, json={"detail": {"code": "no_requisites_available"}}))
    with pytest.raises(ApiError) as exc:
        run(coded.create_deposit(5, method="fiat", amount=5000, key="k" * 8))
    assert exc.value.code == "no_requisites_available"
    plain = client_with(lambda r: httpx.Response(503, text="Service Unavailable"))
    with pytest.raises(ApiUnavailable):
        run(plain.limits())


def test_network_error_is_unavailable():
    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(ApiUnavailable):
        run(client_with(handler).limits())


def test_unknown_user_profile_is_none():
    api = client_with(lambda r: httpx.Response(404, json={"detail": {"code": "user_not_found"}}))
    assert run(api.profile(5)) is None


def test_other_profile_errors_propagate():
    api = client_with(lambda r: httpx.Response(401, json={"detail": {"code": "unauthorized"}}))
    with pytest.raises(ApiError):
        run(api.profile(5))


def test_receipt_is_uploaded_as_multipart():
    seen = {}

    def handler(request):
        seen["type"] = request.headers["content-type"]
        seen["body"] = request.content
        return httpx.Response(200, json={"id": 1})

    run(client_with(handler).upload_receipt(5, 1, b"\xff\xd8\xffDATA"))
    assert seen["type"].startswith("multipart/form-data") and b"DATA" in seen["body"]


def test_crypto_amount_is_sent_as_string():
    seen = {}

    def handler(request):
        seen["body"] = request.content
        return httpx.Response(201, json={})

    run(client_with(handler).create_deposit(5, method="crypto", usdt_amount="12.50", key="k" * 8))
    assert b'"usdt_amount":"12.50"' in seen["body"].replace(b" ", b"")
