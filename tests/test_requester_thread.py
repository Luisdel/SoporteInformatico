from app.db import connect
from app.pcinfo import ClientInfo
from app.timeutil import utcnow, to_iso


def crear_propia(app, client, settings):
    app.state.pcinfo_collector = lambda r, s: ClientInfo(
        ip="1.1.1.1", mac=None, hostname=None, browser="Chrome", os="Windows")
    conn = connect(settings.db_path)
    d = conn.execute("select id from departments order by sort_order limit 1").fetchone()[0]
    c = conn.execute("select id from categories order by sort_order limit 1").fetchone()[0]
    conn.close()
    r = client.post("/incidencias", data={
        "name": "María López", "department_id": str(d), "device_name": "PC-1",
        "category_id": str(c), "priority": "alta", "subject": "No funciona el correo",
        "description": "Me pide la contraseña una y otra vez."})
    assert r.status_code == 303
    return r.headers["location"].rstrip("/").split("/")[-1]


def test_lista_solo_las_suyas(app, client, settings, make_ticket):
    propia = crear_propia(app, client, settings)
    make_ticket(subject="Incidencia de otra persona")
    r = client.get("/mis-incidencias")
    assert "No funciona el correo" in r.text
    assert "Incidencia de otra persona" not in r.text
    assert propia in r.text


def test_no_puede_ver_ajena(app, client, make_ticket):
    ajena = make_ticket(subject="Privada")
    assert client.get(f"/mis-incidencias/{ajena}").status_code == 404


def test_responder_resuelta_reabre_una_vez(app, client, make_ticket, settings):
    tid = make_ticket(state="resuelta", subject="Se reabre", token="tok-reabre")
    conn = connect(settings.db_path)
    conn.execute("insert into messages(ticket_id,author_type,author_admin_id,body,is_internal,created_at)"
                 " values(?,'admin',NULL,'Resuelto','0',?)", (tid, to_iso(utcnow())))
    conn.commit(); conn.close()
    client.cookies.set("device", "tok-reabre")
    r = client.post(f"/mis-incidencias/{tid}/responder", data={"body": "Sigue fallando"})
    assert r.status_code == 303
    conn = connect(settings.db_path)
    t = conn.execute("select * from tickets where id=?", (tid,)).fetchone()
    assert (t["state"], t["resolved_at"], t["reopened_count"]) == ("en_curso", None, 1)
    assert conn.execute("select count(*) from ticket_events where ticket_id=? and event_type='reopen'", (tid,)).fetchone()[0] == 1
    assert conn.execute("select count(*) from messages where ticket_id=? and author_type='system'", (tid,)).fetchone()[0] == 1
    conn.close()


def test_nota_interna_nunca_se_muestra(app, client, make_ticket, settings):
    tid = make_ticket(token="tok-nota")
    conn = connect(settings.db_path); conn.execute(
        "insert into messages(ticket_id,author_type,body,is_internal,created_at)"
        " values(?,'admin','SECRETO INTERNO',1,?)", (tid, to_iso(utcnow()))); conn.commit(); conn.close()
    client.cookies.set("device", "tok-nota")
    assert "SECRETO INTERNO" not in client.get(f"/mis-incidencias/{tid}").text


def test_aviso_de_respuesta_nueva(app, client, make_ticket, settings):
    tid = make_ticket(token="tok-aviso")
    client.cookies.set("device", "tok-aviso")
    assert client.get("/api/avisos").json()["unread"] == 0
    conn = connect(settings.db_path); conn.execute(
        "insert into messages(ticket_id,author_type,body,is_internal,created_at)"
        " values(?,'admin','Te respondo',0,?)", (tid, to_iso(utcnow()))); conn.commit(); conn.close()
    assert client.get("/api/avisos").json()["unread"] == 1
    client.get(f"/mis-incidencias/{tid}")
    assert client.get("/api/avisos").json()["unread"] == 0
