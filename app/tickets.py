from __future__ import annotations

PRIORITIES = ["baja", "normal", "alta", "urgente"]
STATES = ["nueva", "en_curso", "en_espera", "resuelta"]

def next_code(conn, *, now):
    year = now.year
    conn.execute("update ticket_counters set value = value + 1 where year=?", (year,))
    conn.execute("insert into ticket_counters(year,value) values(?,1) on conflict(year) do nothing", (year,))
    row = conn.execute("select value from ticket_counters where year=?", (year,)).fetchone()
    return f"INC-{year}-{row[0]:04d}"

def create_ticket(conn, *, requester_id, requester_name, department_id, category_id, priority, subject, description, client, now=None):
    import datetime
    from app.timeutil import utcnow, to_iso
    if priority not in PRIORITIES:
        raise ValueError("prioridad invalida")
    if not (3 <= len(subject) <= 120):
        raise ValueError("asunto debe tener 3-120 caracteres")
    if len(description) < 10:
        raise ValueError("descripcion debe tener al menos 10 caracteres")
    now = now or utcnow()
    code = next_code(conn, now=now)
    conn.execute(
        "insert into tickets(code, state, priority, requester_name, requester_id, department_id, category_id, subject, description, client_ip, client_mac, client_hostname, client_user_agent, created_at, updated_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (code, "nueva", priority, requester_name, requester_id, department_id, category_id, subject, description,
         getattr(client, "ip", None) or "", getattr(client, "mac", None) or "", getattr(client, "hostname", None) or "", getattr(client, "user_agent", None) or "", to_iso(now), to_iso(now))
    )
    ticket_id = conn.execute("select last_insert_rowid()").fetchone()[0]
    conn.execute("insert into messages(ticket_id, author_type, author_requester_id, body, created_at) values(?, 'requester', ?, ?, ?)", (ticket_id, requester_id, description, to_iso(now)))
    conn.commit()
    return ticket_id

def get_ticket(conn, ticket_id):
    return conn.execute("select * from tickets where id=?", (ticket_id,)).fetchone()

def list_for_requester(conn, requester_id):
    return conn.execute("select * from tickets where requester_id=? order by updated_at desc", (requester_id,)).fetchall()
