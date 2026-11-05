from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.admins import create_admin
from app.db import connect
from app.timeutil import to_gfh
from tests.conftest import csrf_from


def test_gfh_formato_zulu():
    assert to_gfh(datetime(2026, 11, 5, 14, 30, tzinfo=timezone.utc)) == "051430ZNOV26"
    assert to_gfh(datetime(2024, 6, 15, 9, 5, tzinfo=timezone.utc)) == "150905ZJUN24"
    assert to_gfh("2026-01-02T03:04:05+00:00") == "020304ZJAN26"
    assert to_gfh(None) == "—"


def test_superadmin_crea_administrador(admin_client, settings):
    html = admin_client.get("/admin/administradores").text
    r = admin_client.post(
        "/admin/administradores",
        data={
            "username": "soporte2",
            "display_name": "Soporte Dos",
            "role": "admin",
            "password": "clave-soporte-2",
            "repeat_password": "clave-soporte-2",
            "csrf_token": csrf_from(html),
        },
    )
    assert r.status_code == 303
    conn = connect(settings.db_path)
    row = conn.execute(
        "select role, active from admins where username='soporte2'"
    ).fetchone()
    conn.close()
    assert row is not None and row["role"] == "admin" and row["active"] == 1


def test_crear_admin_rechaza_contrasenas_distintas(admin_client, settings):
    html = admin_client.get("/admin/administradores").text
    r = admin_client.post(
        "/admin/administradores",
        data={
            "username": "soporte3",
            "display_name": "Soporte Tres",
            "role": "admin",
            "password": "clave-soporte-3",
            "repeat_password": "otra-clave-3",
            "csrf_token": csrf_from(html),
        },
    )
    assert r.status_code == 303
    assert "error" in r.headers["location"]
    conn = connect(settings.db_path)
    assert conn.execute(
        "select count(*) from admins where username='soporte3'"
    ).fetchone()[0] == 0
    conn.close()


def test_admin_normal_no_puede_gestionar_admins(app, settings, admin):
    conn = connect(settings.db_path)
    create_admin(
        conn,
        username="normal",
        display_name="Admin Normal",
        password="clave-normal-1",
        role="admin",
        iterations=1000,
    )
    conn.commit()
    conn.close()

    client = TestClient(app, follow_redirects=False)
    client.get("/admin/login")
    token = client.cookies["login_csrf"]
    assert client.post(
        "/admin/login",
        data={
            "username": "normal",
            "password": "clave-normal-1",
            "csrf_token": token,
        },
    ).status_code == 303
    assert client.get("/admin/administradores").status_code == 403
    assert client.post(
        "/admin/administradores", data={"csrf_token": "x"}
    ).status_code == 403


def test_limpieza_total_conserva_al_superadmin(admin_client, admin, make_ticket, settings):
    make_ticket(token="tok-borrar")
    conn = connect(settings.db_path)
    create_admin(
        conn,
        username="otro",
        display_name="Otro Admin",
        password="clave-otro-11",
        iterations=1000,
    )
    conn.execute(
        "insert into admin_audit(admin_id, action, created_at) values (?, 'test', 'x')",
        (admin,),
    )
    attachment = settings.upload_dir / "borrar.png"
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_bytes(b"PNG")
    message_id = conn.execute("select id from messages limit 1").fetchone()[0]
    ticket_id = conn.execute("select id from tickets limit 1").fetchone()[0]
    conn.execute(
        "insert into attachments(ticket_id,message_id,original_name,stored_name,mime,size,created_at)"
        " values(?,?,?,?,?,?,?)",
        (ticket_id, message_id, "borrar.png", "borrar.png", "image/png", 3, "x"),
    )
    conn.commit()
    conn.close()

    html = admin_client.get("/admin/administradores").text
    token = csrf_from(html)

    assert admin_client.post(
        "/admin/administradores/borrar-todo",
        data={"confirm": "NO", "csrf_token": token},
    ).headers["location"].find("error") != -1

    r = admin_client.post(
        "/admin/administradores/borrar-todo",
        data={"confirm": "BORRAR", "csrf_token": token},
    )
    assert r.status_code == 303

    conn = connect(settings.db_path)
    assert conn.execute("select count(*) from tickets").fetchone()[0] == 0
    assert conn.execute("select count(*) from requesters").fetchone()[0] == 0
    assert conn.execute("select count(*) from messages").fetchone()[0] == 0
    assert conn.execute("select count(*) from admin_audit").fetchone()[0] == 0
    admins = conn.execute("select id from admins").fetchall()
    conn.close()
    assert [row["id"] for row in admins] == [admin]
    assert not attachment.exists()
    assert admin_client.get("/admin").status_code == 200
