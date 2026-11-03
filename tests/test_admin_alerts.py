from app.db import connect
from app.timeutil import utcnow, to_iso
from tests.conftest import csrf_from

def test_asignar_liberar_y_reasignar(admin_client, admin, make_ticket, settings):
    tid = make_ticket()
    html = admin_client.get(f"/admin/incidencias/{tid}").text
    admin_client.post(f"/admin/incidencias/{tid}/asignar", data={"assignee":"me","csrf_token":csrf_from(html)})
    conn = connect(settings.db_path)
    assert conn.execute("select assigned_admin_id from tickets where id=?", (tid,)).fetchone()[0] == admin
    conn.close()
    admin_client.post(f"/admin/incidencias/{tid}/asignar", data={"assignee":"none","csrf_token":csrf_from(html)})
    conn = connect(settings.db_path)
    assert conn.execute("select assigned_admin_id from tickets where id=?", (tid,)).fetchone()[0] is None
    conn.close()

def test_avisos_sin_asignar_y_mis_no_leidas(admin_client, admin, make_ticket, settings):
    libre = make_ticket(state="nueva")
    mia = make_ticket(state="en_curso", assigned_admin_id=admin)
    conn = connect(settings.db_path)
    conn.execute("delete from messages where ticket_id=?", (mia,))
    conn.execute("insert into messages(ticket_id,author_type,body,is_internal,created_at) values(?,'requester','Nueva respuesta',0,?)", (mia, to_iso(utcnow())))
    conn.commit(); conn.close()
    body = admin_client.get("/api/admin/avisos").json()
    assert body == {"sin_asignar": 1, "mis_no_leidas": 1}
    admin_client.get(f"/admin/incidencias/{mia}")
    assert admin_client.get("/api/admin/avisos").json()["mis_no_leidas"] == 0

def test_api_avisos_sin_sesion(client):
    assert client.get("/api/admin/avisos").status_code == 401
