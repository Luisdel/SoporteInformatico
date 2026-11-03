import re
import pytest
from fastapi.testclient import TestClient
from app.admins import create_admin
from app.config import Settings
from app.db import connect
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        host="127.0.0.1", port=8000,
        db_path=tmp_path / "test.db", upload_dir=tmp_path / "uploads",
        timezone="Europe/Madrid", trusted_proxies=(),
        tls_cert=None, tls_key=None, session_hours=12,
        max_upload_mb=5, secure_cookies=False,
        pbkdf2_iterations=1_000, resolve_hostnames=False,
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def admin(app, settings):
    conn = connect(settings.db_path)
    admin_id = create_admin(conn, username="javier", display_name="Javier Pérez",
                            password="clave-segura-1", role="superadmin",
                            iterations=1000)
    conn.commit(); conn.close()
    return admin_id


@pytest.fixture
def admin_client(client, admin):
    client.get("/admin/login")
    token = client.cookies["login_csrf"]
    r = client.post("/admin/login", data={
        "username": "javier", "password": "clave-segura-1", "csrf_token": token})
    assert r.status_code == 303
    return client


def csrf_from(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
