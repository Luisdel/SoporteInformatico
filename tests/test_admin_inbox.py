from app.db import connect
from app.auth import AdminContext

def test_admin_inbox(admin_client, admin, settings):
    # Crear incidencia
    conn = connect(settings.db_path)
    d = conn.execute("select id from departments limit 1").fetchone()[0]
    c = conn.execute("select id from categories limit 1").fetchone()[0]
    conn.execute("insert into tickets(code, state, priority, requester_name, requester_id, department_id, category_id, subject, description, created_at, updated_at) values('INC-2026-9999', 'nueva', 'alta', 'Test', 1, ?, ?, 'asunto', 'descripcion', 'x', 'x')", (d, c))
    conn.commit()
    conn.close()

    r = admin_client.get("/admin")
    assert r.status_code == 200
    assert "INC-2026-9999" in r.text

def test_ticket_detail(admin_client, admin, settings):
    conn = connect(settings.db_path)
    # Crear ticket con mensaje
    t_id = conn.execute("insert into tickets(code, state, priority, requester_name, requester_id, department_id, category_id, subject, description, created_at, updated_at) values('INC-2026-1000', 'nueva', 'alta', 'Test', 1, 1, 1, 'asunto', 'desc', 'x', 'x') returning id").fetchone()[0]
    conn.execute("insert into messages(ticket_id, author_type, body, created_at) values(?, 'requester', 'Hola', 'x')", (t_id,))
    conn.commit()
    conn.close()

    r = admin_client.get(f"/admin/tickets/{t_id}")
    assert r.status_code == 200
    assert "asunto" in r.text
    assert "Hola" in r.text
