from app.admins import create_admin
from app.db import connect
from tests.conftest import csrf_from


def test_crear_admin_valida_password(settings):
    conn = connect(settings.db_path)
    try:
        create_admin(conn, username="x", display_name="X", password="corta")
    except ValueError:
        pass
    else:
        raise AssertionError("debe exigir 10 caracteres")


def test_login_y_logout(admin, client):
    r = client.get("/admin/login")
    assert r.status_code == 200 and "login_csrf" in r.cookies
    token = r.cookies["login_csrf"]
    r = client.post("/admin/login", data={
        "username": "javier", "password": "clave-segura-1", "csrf_token": token})
    assert r.status_code == 303 and r.headers["location"] == "/admin"
    assert client.get("/admin").status_code == 200
    html = client.get("/admin").text
    assert client.post("/admin/logout", data={"csrf_token": csrf_from(html)}).status_code == 303
    assert client.get("/admin").status_code == 303


def test_sin_sesion_redirige_al_login(client):
    r = client.get("/admin")
    assert r.status_code == 303
    assert r.headers["location"].startswith("/admin/login")


def test_password_incorrecta(admin, client):
    client.get("/admin/login")
    token = client.cookies["login_csrf"]
    r = client.post("/admin/login", data={
        "username": "javier", "password": "incorrecta-1", "csrf_token": token})
    assert r.status_code == 401
    assert "Usuario o contraseña incorrectos" in r.text


def test_login_sin_csrf(admin, client):
    client.get("/admin/login")
    r = client.post("/admin/login", data={
        "username": "javier", "password": "clave-segura-1", "csrf_token": "malo"})
    assert r.status_code == 400


def test_limite_de_intentos(admin, client):
    for _ in range(5):
        client.get("/admin/login")
        client.post("/admin/login", data={
            "username": "javier", "password": "mala-clave-1",
            "csrf_token": client.cookies["login_csrf"]})
    client.get("/admin/login")
    r = client.post("/admin/login", data={
        "username": "javier", "password": "clave-segura-1",
        "csrf_token": client.cookies["login_csrf"]})
    assert r.status_code == 429