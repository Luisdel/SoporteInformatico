from app.db import connect
from app.timeutil import utcnow, to_iso

def admin_unread(conn, admin_id):
    # sin asignar: nuevas sin admin
    sin_asignar = conn.execute("select count(*) from tickets where assigned_admin_id is null and state!='resuelta'").fetchone()[0]
    # mis no leídas: asignadas al admin con mensaje nuevo después de last read
    mis = conn.execute("""select count(*) from tickets where assigned_admin_id=? and (requester_last_read_at is null or updated_at > requester_last_read_at)""", (admin_id,)).fetchone()[0]
    return {"sin_asignar": sin_asignar, "mis_no_leidas": mis}

def mark_read_admin(conn, ticket_id, admin_id, *, now=None):
    conn.execute("update tickets set requester_last_read_at=? where id=?", (to_iso(now or utcnow()), ticket_id))
    conn.commit()

def post_requester_message(conn, ticket_id, requester_id, body, *, attachments=(), now=None):
    if len(body) < 10 or not body.strip():
        raise ValueError("el cuerpo debe tener al menos 10 caracteres")
    now = now or utcnow()
    conn.execute("insert into messages(ticket_id,author_type,author_admin_id,body,is_internal,created_at) values(?,?,?,?,?,?)",
        (ticket_id, "requester", None, body, False, to_iso(now)))
    conn.commit()

def mark_read_requester(conn, ticket_id, *, now=None):
    conn.execute("update tickets set requester_last_read_at=? where id=?",
        (to_iso(now or utcnow()), ticket_id))
    conn.commit()

def requester_unread(conn, requester_id):
    row = conn.execute("""
        select count(*) from messages m
        where m.ticket_id in (select id from tickets where requester_id=?)
          and m.author_type='admin' and m.is_internal=0
          and (m.created_at > (select coalesce(requester_last_read_at,'') from tickets where id=m.ticket_id))
        """, (requester_id,)).fetchone()
    return row[0] if row else 0

def get_ticket_for_requester(conn, ticket_id, requester_id):
    return conn.execute("select * from tickets where id=? and requester_id=?", (ticket_id, requester_id)).fetchone()

def list_messages(conn, ticket_id, *, include_internal=False):
    sql = "select * from messages where ticket_id=?"
    params = (ticket_id,)
    if not include_internal:
        sql += " and is_internal=0"
    sql += " order by created_at"
    return conn.execute(sql, params).fetchall()
