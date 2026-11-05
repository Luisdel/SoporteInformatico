import re
import pytest
from fastapi.testclient import TestClient
from app.admins import create_admin
from app.config import Settings
from app.db import connect, init_db
from app.main import create_app
from app.pcinfo import ClientInfo
from app.security import hash_token
from app.tickets import create_ticket
from app.timeutil import utcnow, to_iso
from uuid import uuid4


@pytest.fixture
def settings(tmp_path):
    settings = Settings(
        host="127.0.0.1", port=8000,
        db_path=tmp_path / "test.db", upload_dir=tmp_path / "uploads",
        timezone="Europe/Madrid", trusted_proxies=(),
        tls_cert=None, tls_key=None, session_hours=12,
        max_upload_mb=5, secure_cookies=False,
        pbkdf2_iterations=1_000, resolve_hostnames=False,
    )
    init_db(settings.db_path)
    return settings


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


@pytest.fixture
def make_ticket(app, settings):
    def _make(*, subject="Incidencia de prueba", state="nueva", priority="normal",
              requester_name="Ana Torres", department_id=None, category_id=None,
              assigned_admin_id=None, token=None):
        token = token or f"tok-{uuid4().hex}"
        conn = connect(settings.db_path)
        d = department_id or conn.execute(
            "select id from departments order by sort_order limit 1").fetchone()[0]
        c = category_id or conn.execute(
            "select id from categories order by sort_order limit 1").fetchone()[0]
        r = conn.execute(
            "insert into requesters(device_token_hash,name,department_id,created_at,updated_at,last_seen_at)"
            " values(?,?,?,?,?,?)",
            (hash_token(token), requester_name, d, "x", "x", "x")).lastrowid
        tid = create_ticket(conn, requester_id=r, requester_name=requester_name,
            department_id=d, category_id=c, priority=priority, subject=subject,
            description="Descripción de prueba suficientemente larga.",
            client=ClientInfo(ip="192.168.1.10", mac=None, hostname=None,
                              browser="Chrome", os="Windows"))
        conn.execute(
            "update tickets set state=?, assigned_admin_id=?, resolved_at=?, requester_last_read_at=? where id=?",
            (state, assigned_admin_id,
             to_iso(utcnow()) if state == "resuelta" else None,
             to_iso(utcnow()), tid))
        conn.commit(); conn.close(); return tid
    return _make
