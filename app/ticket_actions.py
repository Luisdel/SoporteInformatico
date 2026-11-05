from __future__ import annotations

from app.tickets import PRIORITIES, STATES
from app.timeutil import utcnow, to_iso


def admin_unread(conn, admin_id):
    sin_asignar = conn.execute(
        "select count(*) from tickets where assigned_admin_id is null and state != 'resuelta'"
    ).fetchone()[0]
    mis = conn.execute(
        """
        select count(*) from tickets t
         where t.assigned_admin_id = ?
           and t.state != 'resuelta'
           and exists (
               select 1 from messages m
                where m.ticket_id = t.id
                  and m.author_type = 'requester'
                  and m.created_at > coalesce(
                      (select r.last_read_at from ticket_reads r
                        where r.admin_id = ? and r.ticket_id = t.id), '')
           )
        """,
        (admin_id, admin_id),
    ).fetchone()[0]
    return {"sin_asignar": sin_asignar, "mis_no_leidas": mis}


def mark_read_admin(conn, ticket_id, admin_id, *, now=None):
    stamp = to_iso(now or utcnow())
    conn.execute(
        """
        insert into ticket_reads(admin_id, ticket_id, last_read_at) values(?,?,?)
        on conflict(admin_id, ticket_id) do update set last_read_at = excluded.last_read_at
        """,
        (admin_id, ticket_id, stamp),
    )
    conn.commit()


def post_requester_message(conn, ticket_id, requester_id, body, *, attachments=(), now=None):
    body = (body or "").strip()
    if len(body) < 10:
        raise ValueError("el cuerpo debe tener al menos 10 caracteres")
    stamp = to_iso(now or utcnow())
    conn.execute(
        "insert into messages(ticket_id,author_type,author_requester_id,body,is_internal,created_at)"
        " values(?,?,?,?,?,?)",
        (ticket_id, "requester", requester_id, body, 0, stamp),
    )
    message_id = conn.execute("select last_insert_rowid()").fetchone()[0]
    for saved in attachments or ():
        conn.execute(
            "insert into attachments(ticket_id,message_id,original_name,stored_name,mime,size,created_at)"
            " values(?,?,?,?,?,?,?)",
            (ticket_id, message_id, saved.original_name, saved.stored_name,
             saved.mime, saved.size, stamp),
        )
    conn.execute("update tickets set updated_at=? where id=?", (stamp, ticket_id))
    conn.commit()


def post_admin_message(
    conn, ticket_id, admin_id, body, *, is_internal=False, attachments=(), now=None
):
    body = (body or "").strip()
    if not body:
        raise ValueError("el cuerpo no puede estar vacío")
    stamp = to_iso(now or utcnow())
    conn.execute(
        "insert into messages(ticket_id,author_type,author_admin_id,body,is_internal,created_at)"
        " values(?,?,?,?,?,?)",
        (ticket_id, "admin", admin_id, body, 1 if is_internal else 0, stamp),
    )
    message_id = conn.execute("select last_insert_rowid()").fetchone()[0]
    for saved in attachments or ():
        conn.execute(
            "insert into attachments(ticket_id,message_id,original_name,stored_name,mime,size,created_at)"
            " values(?,?,?,?,?,?,?)",
            (
                ticket_id,
                message_id,
                saved.original_name,
                saved.stored_name,
                saved.mime,
                saved.size,
                stamp,
            ),
        )
    ticket = conn.execute("select * from tickets where id=?", (ticket_id,)).fetchone()
    if ticket is not None and not is_internal:
        if ticket["assigned_admin_id"] is None:
            conn.execute(
                "update tickets set assigned_admin_id=? where id=?",
                (admin_id, ticket_id),
            )
            conn.execute(
                "insert into ticket_events(ticket_id,admin_id,event_type,old_value,new_value,created_at)"
                " values(?,?,?,?,?,?)",
                (ticket_id, admin_id, "assignment", None, str(admin_id), stamp),
            )
            ticket = conn.execute(
                "select * from tickets where id=?", (ticket_id,)
            ).fetchone()
        if ticket["state"] == "nueva":
            conn.execute(
                "update tickets set state='en_curso' where id=?", (ticket_id,)
            )
            conn.execute(
                "insert into ticket_events(ticket_id,admin_id,event_type,old_value,new_value,created_at)"
                " values(?,?,?,?,?,?)",
                (ticket_id, admin_id, "state", "nueva", "en_curso", stamp),
            )
    conn.execute("update tickets set updated_at=? where id=?", (stamp, ticket_id))
    conn.commit()
    return message_id


def assign(conn, ticket_id, admin_id, assignee_id, *, now=None):
    ticket = conn.execute("select * from tickets where id=?", (ticket_id,)).fetchone()
    if ticket is None:
        raise ValueError("Incidencia no encontrada")
    if assignee_id is not None:
        row = conn.execute(
            "select id from admins where id=? and active=1", (assignee_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Administrador inválido")
    stamp = to_iso(now or utcnow())
    conn.execute(
        "update tickets set assigned_admin_id=?, updated_at=? where id=?",
        (assignee_id, stamp, ticket_id),
    )
    conn.execute(
        "insert into ticket_events(ticket_id,admin_id,event_type,old_value,new_value,created_at)"
        " values(?,?,?,?,?,?)",
        (
            ticket_id,
            admin_id,
            "assignment",
            str(ticket["assigned_admin_id"])
            if ticket["assigned_admin_id"] is not None
            else None,
            str(assignee_id) if assignee_id is not None else None,
            stamp,
        ),
    )
    conn.commit()


def change_state(conn, ticket_id, admin_id, state, *, now=None):
    if state not in STATES or state == "nueva":
        raise ValueError("Estado inválido")
    ticket = conn.execute("select * from tickets where id=?", (ticket_id,)).fetchone()
    if ticket is None:
        raise ValueError("Incidencia no encontrada")
    if ticket["state"] == state:
        return
    stamp = to_iso(now or utcnow())
    resolved_at = stamp if state == "resuelta" else None
    conn.execute(
        "update tickets set state=?, resolved_at=?, updated_at=? where id=?",
        (state, resolved_at, stamp, ticket_id),
    )
    conn.execute(
        "insert into ticket_events(ticket_id,admin_id,event_type,old_value,new_value,created_at)"
        " values(?,?,?,?,?,?)",
        (
            ticket_id,
            admin_id,
            "resolve" if state == "resuelta" else "state",
            ticket["state"],
            state,
            stamp,
        ),
    )
    body = {
        "resuelta": "Incidencia marcada como resuelta por el administrador.",
        "en_espera": "Incidencia en espera de respuesta del usuario.",
        "en_curso": "Incidencia reabierta por el administrador.",
    }[state]
    conn.execute(
        "insert into messages(ticket_id,author_type,body,is_internal,created_at)"
        " values(?,'system',?,0,?)",
        (ticket_id, body, stamp),
    )
    conn.commit()


def change_priority(conn, ticket_id, admin_id, priority, *, now=None):
    if priority not in PRIORITIES:
        raise ValueError("Prioridad inválida")
    ticket = conn.execute("select * from tickets where id=?", (ticket_id,)).fetchone()
    if ticket is None:
        raise ValueError("Incidencia no encontrada")
    stamp = to_iso(now or utcnow())
    conn.execute(
        "update tickets set priority=?, updated_at=? where id=?",
        (priority, stamp, ticket_id),
    )
    conn.execute(
        "insert into ticket_events(ticket_id,admin_id,event_type,old_value,new_value,created_at)"
        " values(?,?,?,?,?,?)",
        (ticket_id, admin_id, "priority", ticket["priority"], priority, stamp),
    )
    conn.commit()


def change_department(conn, ticket_id, admin_id, department_id, *, now=None):
    ticket = conn.execute("select * from tickets where id=?", (ticket_id,)).fetchone()
    if ticket is None:
        raise ValueError("Incidencia no encontrada")
    stamp = to_iso(now or utcnow())
    conn.execute(
        "update tickets set department_id=?, updated_at=? where id=?",
        (department_id, stamp, ticket_id),
    )
    conn.execute(
        "insert into ticket_events(ticket_id,admin_id,event_type,old_value,new_value,created_at)"
        " values(?,?,?,?,?,?)",
        (
            ticket_id,
            admin_id,
            "department",
            str(ticket["department_id"]),
            str(department_id),
            stamp,
        ),
    )
    conn.commit()


def change_category(conn, ticket_id, admin_id, category_id, *, now=None):
    ticket = conn.execute("select * from tickets where id=?", (ticket_id,)).fetchone()
    if ticket is None:
        raise ValueError("Incidencia no encontrada")
    stamp = to_iso(now or utcnow())
    conn.execute(
        "update tickets set category_id=?, updated_at=? where id=?",
        (category_id, stamp, ticket_id),
    )
    conn.execute(
        "insert into ticket_events(ticket_id,admin_id,event_type,old_value,new_value,created_at)"
        " values(?,?,?,?,?,?)",
        (
            ticket_id,
            admin_id,
            "category",
            str(ticket["category_id"]),
            str(category_id),
            stamp,
        ),
    )
    conn.commit()


def list_attachments(conn, ticket_id):
    rows = conn.execute(
        "select * from attachments where ticket_id=? order by id", (ticket_id,)
    ).fetchall()
    grouped: dict[int, list] = {}
    for row in rows:
        grouped.setdefault(row["message_id"], []).append(row)
    return grouped


def mark_read_requester(conn, ticket_id, *, now=None):
    conn.execute(
        "update tickets set requester_last_read_at=? where id=?",
        (to_iso(now or utcnow()), ticket_id),
    )
    conn.commit()


def requester_unread(conn, requester_id):
    row = conn.execute(
        """
        select count(*) from messages m
        where m.ticket_id in (select id from tickets where requester_id=?)
          and m.author_type='admin' and m.is_internal=0
          and (m.created_at > (select coalesce(requester_last_read_at,'') from tickets where id=m.ticket_id))
        """,
        (requester_id,),
    ).fetchone()
    return row[0] if row else 0


def get_ticket_for_requester(conn, ticket_id, requester_id):
    return conn.execute(
        "select * from tickets where id=? and requester_id=?",
        (ticket_id, requester_id),
    ).fetchone()


def list_messages(conn, ticket_id, *, include_internal=False):
    sql = "select * from messages where ticket_id=?"
    params = (ticket_id,)
    if not include_internal:
        sql += " and is_internal=0"
    sql += " order by created_at, id"
    return conn.execute(sql, params).fetchall()
