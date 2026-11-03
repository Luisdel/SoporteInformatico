import pytest
from fastapi.testclient import TestClient
from app.config import Settings
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
