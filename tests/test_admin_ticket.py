from app.db import connect
from tests.conftest import csrf_from

def test_primera_respuesta_asigna_y_pone_en_curso(admin_client, admin, make_ticket, settings):
    tid = make_ticket(state="nueva")
    html = admin_client.get(f"/admin/incidencias/{tid}").text
    r = admin_client.post(f"/admin/incidencias/{tid}/responder",
        data={"body":"Lo reviso","is_internal":"0","csrf_token":csrf_from(html)})
    assert r.status_code == 303
    conn = connect(settings.db_path)
    t = conn.execute("select * from tickets where id=?", (tid,)).fetchone()
    assert (t["state"], t["assigned_admin_id"]) == ("en_curso", admin)
    assert conn.execute("select count(*) from ticket_events where ticket_id=? and event_type='assignment'", (tid,)).fetchone()[0] == 1
    conn.close()

def test_nota_interna_no_cambia_estado(admin_client, admin, make_ticket, settings):
    tid = make_ticket(state="nueva")
    html = admin_client.get(f"/admin/incidencias/{tid}").text
    admin_client.post(f"/admin/incidencias/{tid}/responder",
        data={"body":"Nota para mí","is_internal":"1","csrf_token":csrf_from(html)})
    conn = connect(settings.db_path)
    assert conn.execute("select state from tickets where id=?", (tid,)).fetchone()[0] == "nueva"
    assert conn.execute("select is_internal from messages where ticket_id=? order by id desc", (tid,)).fetchone()[0] == 1
    conn.close()

def test_resolver_crea_evento_y_mensaje_de_sistema(admin_client, make_ticket, settings):
    tid = make_ticket(state="en_curso")
    html = admin_client.get(f"/admin/incidencias/{tid}").text
    admin_client.post(f"/admin/incidencias/{tid}/estado",
        data={"state":"resuelta","csrf_token":csrf_from(html)})
    conn = connect(settings.db_path)
    t = conn.execute("select * from tickets where id=?", (tid,)).fetchone()
    assert t["state"] == "resuelta" and t["resolved_at"] is not None
    assert conn.execute("select count(*) from ticket_events where ticket_id=? and event_type='resolve'", (tid,)).fetchone()[0] == 1
    assert conn.execute("select count(*) from messages where ticket_id=? and author_type='system'", (tid,)).fetchone()[0] == 1
    conn.close()
