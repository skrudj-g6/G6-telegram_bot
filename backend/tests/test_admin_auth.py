from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import AuditLog, StaffSession, StaffUser
from app.services import staff as staff_service
from app.services.errors import ServiceError
from tests.conftest import PASSWORD


def detail(response) -> dict:
    return response.json()["detail"]


def login(client, login, password=PASSWORD):
    return client.post("/admin/v1/auth/login", json={"login": login, "password": password})


def test_login_returns_token_staff_and_sets_cookie(client, make_staff):
    make_staff("operator", login="op1")
    response = login(client, "op1")
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 15 * 60
    assert body["staff"]["login"] == "op1" and body["staff"]["role"] == "operator"
    assert "requests.process" in body["staff"]["permissions"]
    assert "password_hash" not in response.text
    cookie = response.headers["set-cookie"]
    assert "refresh_token=" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Path=/admin/v1/auth" in cookie


def test_login_is_case_insensitive_for_login(client, make_staff):
    make_staff("operator", login="op1")
    assert login(client, "  OP1 ").status_code == 200


def test_wrong_password_and_unknown_login_look_the_same(client, make_staff):
    make_staff("operator", login="op1")
    wrong = login(client, "op1", "wrong-password-1")
    unknown = login(client, "nobody")
    assert (wrong.status_code, unknown.status_code) == (401, 401)
    assert detail(wrong) == detail(unknown) == {"code": "invalid_credentials"}


def test_inactive_staff_cannot_login(client, make_staff):
    make_staff("operator", login="op1", active=False)
    assert login(client, "op1").status_code == 401


def test_account_locks_after_repeated_failures(client, make_staff):
    make_staff("operator", login="op1")
    for _ in range(5):
        assert login(client, "op1", "wrong-password-1").status_code == 401
    locked = login(client, "op1")  # даже верный пароль
    assert (locked.status_code, detail(locked)["code"]) == (429, "too_many_attempts")


def test_lock_expires_and_success_resets_counter(db, make_staff):
    make_staff("operator", login="op1")
    now = datetime.now(timezone.utc)
    for _ in range(5):
        try:
            staff_service.login(db, login="op1", password="wrong-password-1", now=now)
        except ServiceError:
            pass
    try:
        staff_service.login(db, login="op1", password=PASSWORD, now=now)
        assert False, "должна быть блокировка"
    except ServiceError as exc:
        assert exc.code == "too_many_attempts"
    staff, _ = staff_service.login(
        db, login="op1", password=PASSWORD, now=now + timedelta(minutes=16)
    )
    assert staff.failed_attempts == 0 and staff.locked_until is None


def test_failed_and_successful_logins_are_audited_without_secrets(client, db, make_staff):
    make_staff("operator", login="op1")
    login(client, "op1", "wrong-password-1")
    login(client, "ghost", "wrong-password-2")
    login(client, "op1")
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id)).all()
    assert [r.action for r in rows] == ["auth.login_failed", "auth.login_failed", "auth.login"]
    dump = " ".join(str(r.details) for r in rows)
    assert "wrong-password" not in dump and "ghost" not in dump and PASSWORD not in dump


def test_me_requires_valid_token(client, auth):
    headers, staff = auth("operator", "op1")
    assert client.get("/admin/v1/auth/me", headers=headers).json()["login"] == "op1"
    assert client.get("/admin/v1/auth/me").status_code == 401
    bad = {"Authorization": "Bearer abc.def.ghi"}
    assert client.get("/admin/v1/auth/me", headers=bad).status_code == 401


def test_expired_token_is_refused(client, db, make_staff):
    staff = make_staff("operator", login="op1")
    token, _ = staff_service.issue_access_token(
        staff, now=datetime.now(timezone.utc) - timedelta(minutes=20)
    )
    response = client.get("/admin/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_deactivated_staff_token_stops_working_immediately(client, db, auth):
    headers, staff = auth("operator", "op1")
    db.get(StaffUser, staff.id).is_active = False
    db.commit()
    assert client.get("/admin/v1/auth/me", headers=headers).status_code == 401


def test_role_comes_from_database_not_token(client, db, auth):
    headers, staff = auth("operator", "op1")
    db.get(StaffUser, staff.id).role = "finance"
    db.commit()
    assert client.get("/admin/v1/auth/me", headers=headers).json()["role"] == "finance"


def test_refresh_rotates_token(client, make_staff):
    make_staff("operator", login="op1")
    login(client, "op1")
    old_cookie = client.cookies.get("refresh_token")
    response = client.post("/admin/v1/auth/refresh")
    assert response.status_code == 200 and response.json()["access_token"]
    assert client.cookies.get("refresh_token") != old_cookie


def test_reusing_old_refresh_token_closes_all_sessions(client, db, make_staff):
    make_staff("operator", login="op1")
    login(client, "op1")
    stolen = client.cookies.get("refresh_token")
    assert client.post("/admin/v1/auth/refresh").status_code == 200
    try:
        staff_service.refresh(db, token=stolen)
        assert False, "старый токен не должен приниматься"
    except ServiceError as exc:
        assert exc.code == "invalid_refresh"
    # Теперь не работает и свежий токен, выданный при ротации.
    assert client.post("/admin/v1/auth/refresh").status_code == 401
    assert all(s.revoked_at is not None for s in db.scalars(select(StaffSession)).all())
    assert "auth.refresh_reuse" in [r.action for r in db.scalars(select(AuditLog)).all()]


def test_refresh_without_cookie_is_401(client):
    response = client.post("/admin/v1/auth/refresh")
    assert (response.status_code, detail(response)["code"]) == (401, "invalid_refresh")


def test_refresh_token_is_stored_only_as_hash(client, db, make_staff):
    make_staff("operator", login="op1")
    login(client, "op1")
    token = client.cookies.get("refresh_token")
    assert db.scalars(select(StaffSession.token_hash)).all() != [token]
    assert token not in db.scalars(select(StaffSession.token_hash)).all()


def test_logout_revokes_session(client, db, make_staff):
    make_staff("operator", login="op1")
    login(client, "op1")
    token = client.cookies.get("refresh_token")
    assert client.post("/admin/v1/auth/logout").status_code == 204
    try:
        staff_service.refresh(db, token=token)
        assert False, "токен закрыт выходом"
    except ServiceError as exc:
        assert exc.code == "invalid_refresh"


def test_change_password(client, auth):
    headers, _ = auth("operator", "op1")
    body = {"current_password": PASSWORD, "new_password": "brand-new-password"}
    assert client.post("/admin/v1/auth/change-password", json=body, headers=headers).status_code == 204
    assert login(client, "op1", PASSWORD).status_code == 401
    assert login(client, "op1", "brand-new-password").status_code == 200


def test_change_password_checks_current_and_policy(client, auth):
    headers, _ = auth("operator", "op1")
    wrong = {"current_password": "nope-nope-nope", "new_password": "brand-new-password"}
    assert client.post("/admin/v1/auth/change-password", json=wrong, headers=headers).status_code == 401
    weak = {"current_password": PASSWORD, "new_password": "short"}
    response = client.post("/admin/v1/auth/change-password", json=weak, headers=headers)
    assert (response.status_code, detail(response)["code"]) == (422, "weak_password")


def test_bot_endpoints_do_not_accept_staff_token_and_vice_versa(client, auth, bot_headers):
    headers, _ = auth("owner", "own1")
    assert client.get("/bot/v1/settings/limits", headers=headers).status_code == 401
    assert client.get("/admin/v1/auth/me", headers=bot_headers).status_code == 401
