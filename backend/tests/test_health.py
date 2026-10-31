from sqlalchemy.exc import OperationalError

from app.db.session import get_db


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_ok_when_db_available(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_503_when_db_down(client):
    class BrokenSession:
        def execute(self, *_args, **_kwargs):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    def broken_db():
        yield BrokenSession()

    client.app.dependency_overrides[get_db] = broken_db
    response = client.get("/health/ready")
    assert response.status_code == 503
    # Детали ошибки (хост, пароль) наружу не отдаются.
    assert response.json() == {"detail": "database unavailable"}


def test_unknown_route_404(client):
    assert client.get("/no-such-route").status_code == 404
