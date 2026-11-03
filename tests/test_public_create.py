from datetime import datetime, timezone
from app.db import connect
from app.pcinfo import ClientInfo


def congelar(monkeypatch):
    monkeypatch.setattr("app.routes.public.utcnow",
        lambda: datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc))


def preparar(app):
    app.state.pcinfo_collector = lambda request, settings: ClientInfo(
        ip="192.168.20.57", mac="3C:7C:3F:1A:2B:9D", hostname="PC-CONTAB-03",
        browser="Chrome", os="Windows")


def formulario(dept_id, cat_id, nombre="María López", asunto="No funciona el correo"):
    return {"name": nombre, "department_id": str(dept_id), "device_name": "PC-CONTAB-03",
            "category_id": str(cat_id), "priority": "alta", "subject": asunto,
            "description": "Me pide la contraseña una y otra vez."}


def ids(settings):
    conn = connect(settings.db_path)
    d = conn.execute("select id from departments order by sort_order limit 1").fetchone()[0]
    c = conn.execute("select id from categories order by sort_order limit 1").fetchone()[0]
    conn.close()
    return d, c


def test_get_emite_cookie_y_muestra_catalogos(app, client, settings):
    preparar(app)
    r = client.get("/")
    assert r.status_code == 200 and "device" in r.cookies
    assert "Administración" in r.text and "Correo / Outlook" in r.text


def test_crear_incidencia_con_codigo_y_datos(app, client, settings, monkeypatch):
    preparar(app)
    congelar(monkeypatch)
    d, c = ids(settings)
    r = client.post("/incidencias", data=formulario(d, c))
    assert r.status_code == 303
    conn = connect(settings.db_path)
    t = conn.execute("select * from tickets").fetchone()
    m = conn.execute("select * from messages where ticket_id=?", (t["id"],)).fetchone()
    assert t["code"] == "INC-2026-0001"
    assert t["requester_name"] == "María López" and t["client_mac"] == "3C:7C:3F:1A:2B:9D"
    assert (t["state"], t["priority"], t["client_ip"]) == ("nueva", "alta", "192.168.20.57")
    assert m["author_type"] == "requester" and m["body"] == "Me pide la contraseña una y otra vez."
    conn.close()


def test_segunda_incidencia_incrementa_y_recuerda(app, client, settings, monkeypatch):
    preparar(app)
    congelar(monkeypatch)
    d, c = ids(settings)
    client.post("/incidencias", data=formulario(d, c))
    r = client.get("/")
    assert 'value="María López"' in r.text
    client.post("/incidencias", data=formulario(d, c, asunto="Otra cosa"))
    conn = connect(settings.db_path)
    assert [x[0] for x in conn.execute("select code from tickets order by id")] == [
        "INC-2026-0001", "INC-2026-0002"]
    conn.close()


def test_validacion_rechaza_sin_crear(app, client, settings):
    preparar(app)
    d, c = ids(settings)
    datos = formulario(d, c, nombre="")
    r = client.post("/incidencias", data=datos)
    assert r.status_code == 400
    conn = connect(settings.db_path)
    assert conn.execute("select count(*) from tickets").fetchone()[0] == 0
    conn.close()


def test_codigos_unicos_en_paralelo(app, settings):
    from concurrent.futures import ThreadPoolExecutor
    from app.tickets import next_code
    def emitir(_):
        c = connect(settings.db_path)
        try:
            code = next_code(c, now=datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc))
            c.commit()
            return code
        finally:
            c.close()
    with ThreadPoolExecutor(max_workers=8) as ex:
        codes = list(ex.map(emitir, range(8)))
    assert len(set(codes)) == 8
    assert all(c.startswith("INC-2026-") for c in codes)
