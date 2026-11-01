import pytest
from sqlalchemy import select

from app.core import permissions
from app.models import AuditLog, StaffUser
from tests.conftest import PASSWORD


def detail(response) -> dict:
    return response.json()["detail"]


def create(client, headers, login="new1", role="operator", password="long-enough-password"):
    return client.post(
        "/admin/v1/staff",
        json={"login": login, "display_name": "Новый", "role": role, "password": password},
        headers=headers,
    )


# ---------- права ----------


@pytest.mark.parametrize("role", ["operator", "finance"])
def test_operator_and_finance_cannot_manage_staff(client, auth, role):
    headers, _ = auth(role, f"{role}1")
    assert client.get("/admin/v1/staff", headers=headers).status_code == 403
    assert create(client, headers).status_code == 403


def test_staff_endpoints_require_login(client):
    assert client.get("/admin/v1/staff").status_code == 401
    assert client.post("/admin/v1/staff", json={}).status_code == 401


def test_permission_matrix():
    assert permissions.has_permission("owner", permissions.STAFF_MANAGE)
    assert permissions.has_permission("operator", permissions.REQUESTS_PROCESS)
    assert permissions.has_permission("operator", permissions.PLAYERS_MODERATE)
    assert not permissions.has_permission("operator", permissions.SETTINGS_EDIT)
    assert not permissions.has_permission("operator", permissions.STAFF_MANAGE)
    assert not permissions.has_permission("operator", permissions.AUDIT_VIEW)
    assert not permissions.has_permission("finance", permissions.REQUESTS_PROCESS)
    assert permissions.has_permission("finance", permissions.REQUESTS_VIEW)
    assert not permissions.has_permission("unknown", permissions.PLAYERS_VIEW)


def test_owner_creates_any_role_and_it_is_audited(client, db, auth):
    headers, owner = auth("owner", "own1")
    for role in ("owner", "admin", "operator", "finance"):
        response = create(client, headers, login=f"user-{role}", role=role)
        assert response.status_code == 201, response.text
        assert response.json()["role"] == role
        assert "password" not in response.text
    rows = db.scalars(select(AuditLog).where(AuditLog.action == "staff.created")).all()
    assert len(rows) == 4 and {r.staff_id for r in rows} == {owner.id}
    assert "long-enough-password" not in str([r.details for r in rows])


def test_admin_cannot_create_owner_or_admin(client, auth):
    headers, _ = auth("admin", "adm1")
    assert create(client, headers, role="operator", login="u1").status_code == 201
    assert create(client, headers, role="finance", login="u2").status_code == 201
    for role in ("owner", "admin"):
        response = create(client, headers, role=role, login=f"x-{role}")
        assert (response.status_code, detail(response)["code"]) == (403, "forbidden")


def test_create_validation(client, auth):
    headers, _ = auth("owner", "own1")
    assert create(client, headers, login="ab").status_code == 422  # короткий логин
    assert create(client, headers, login="bad login!").status_code == 422
    weak = create(client, headers, password="short")
    assert (weak.status_code, detail(weak)["code"]) == (422, "weak_password")
    assert create(client, headers, role="superuser").status_code == 422
    assert create(client, headers, login="dup1").status_code == 201
    taken = create(client, headers, login="DUP1")
    assert (taken.status_code, detail(taken)["code"]) == (409, "login_taken")


def test_new_staff_can_login(client, auth):
    headers, _ = auth("owner", "own1")
    create(client, headers, login="fresh1", password="long-enough-password")
    response = client.post(
        "/admin/v1/auth/login", json={"login": "fresh1", "password": "long-enough-password"}
    )
    assert response.status_code == 200


def test_list_staff_hides_secrets(client, auth):
    headers, _ = auth("owner", "own1")
    response = client.get("/admin/v1/staff", headers=headers)
    assert response.status_code == 200
    assert "password" not in response.text and "token" not in response.text


# ---------- изменение ----------


def test_owner_changes_role_and_deactivates(client, db, auth, make_staff):
    headers, _ = auth("owner", "own1")
    target = make_staff("operator", login="op1")
    r = client.patch(f"/admin/v1/staff/{target.id}", json={"role": "finance"}, headers=headers)
    assert (r.status_code, r.json()["role"]) == (200, "finance")
    r = client.patch(f"/admin/v1/staff/{target.id}", json={"is_active": False}, headers=headers)
    assert r.json()["is_active"] is False
    actions = [a.action for a in db.scalars(select(AuditLog)).all()]
    assert actions.count("staff.updated") == 2


def test_admin_cannot_touch_owner_or_other_admin(client, auth, make_staff):
    headers, _ = auth("admin", "adm1")
    for role in ("owner", "admin"):
        target = make_staff(role, login=f"t-{role}")
        r = client.patch(f"/admin/v1/staff/{target.id}", json={"is_active": False}, headers=headers)
        assert (r.status_code, detail(r)["code"]) == (403, "forbidden")
        r = client.post(
            f"/admin/v1/staff/{target.id}/reset-password",
            json={"new_password": "long-enough-password"},
            headers=headers,
        )
        assert r.status_code == 403


def test_admin_cannot_promote_operator_to_admin(client, auth, make_staff):
    headers, _ = auth("admin", "adm1")
    target = make_staff("operator", login="op1")
    r = client.patch(f"/admin/v1/staff/{target.id}", json={"role": "admin"}, headers=headers)
    assert r.status_code == 403


def test_cannot_change_own_role_or_deactivate_self(client, auth):
    headers, owner = auth("owner", "own1")
    for body in ({"role": "operator"}, {"is_active": False}):
        r = client.patch(f"/admin/v1/staff/{owner.id}", json=body, headers=headers)
        assert (r.status_code, detail(r)["code"]) == (409, "cannot_modify_self")


def test_last_active_owner_is_protected(client, db, auth, make_staff):
    headers, owner = auth("owner", "own1")
    other = make_staff("owner", login="own2")
    # Двое владельцев: можно отключить другого, оставшийся — последний.
    r = client.patch(f"/admin/v1/staff/{other.id}", json={"is_active": False}, headers=headers)
    assert r.status_code == 200
    third = make_staff("owner", login="own3", active=False)
    r = client.patch(f"/admin/v1/staff/{third.id}", json={"role": "admin"}, headers=headers)
    assert r.status_code == 200  # он и так отключён, активных владельцев не стало меньше
    db.get(StaffUser, other.id).is_active = True
    db.commit()
    # Один из двух активных владельцев меняет роль другого — допустимо.
    r = client.patch(f"/admin/v1/staff/{other.id}", json={"role": "admin"}, headers=headers)
    assert r.status_code == 200
    # Теперь owner один: понизить его некому, кроме него самого (запрещено).
    assert client.patch(
        f"/admin/v1/staff/{owner.id}", json={"role": "admin"}, headers=headers
    ).status_code == 409


def test_unknown_staff_is_404(client, auth):
    headers, _ = auth("owner", "own1")
    r = client.patch("/admin/v1/staff/9999", json={"is_active": False}, headers=headers)
    assert (r.status_code, detail(r)["code"]) == (404, "staff_not_found")


def test_deactivation_kills_sessions(client, db, auth, make_staff):
    owner_headers, _ = auth("owner", "own1")
    target = make_staff("operator", login="op1")
    client.cookies.clear()
    assert client.post("/admin/v1/auth/login", json={"login": "op1", "password": PASSWORD}).status_code == 200
    client.patch(f"/admin/v1/staff/{target.id}", json={"is_active": False}, headers=owner_headers)
    assert client.post("/admin/v1/auth/refresh").status_code == 401


# ---------- сброс пароля (Q-13) ----------


def test_reset_password_unlocks_and_changes_login(client, db, auth, make_staff):
    headers, _ = auth("owner", "own1")
    target = make_staff("operator", login="op1")
    for _ in range(5):
        client.post("/admin/v1/auth/login", json={"login": "op1", "password": "wrong-password-1"})
    r = client.post(
        f"/admin/v1/staff/{target.id}/reset-password",
        json={"new_password": "temporary-password-9"},
        headers=headers,
    )
    assert r.status_code == 204
    ok = client.post("/admin/v1/auth/login", json={"login": "op1", "password": "temporary-password-9"})
    assert ok.status_code == 200
    assert "temporary-password-9" not in str([a.details for a in db.scalars(select(AuditLog)).all()])
