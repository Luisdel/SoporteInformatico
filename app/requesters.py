from __future__ import annotations

import hashlib
import secrets

from app.db import connect
from app.timeutil import to_iso, utcnow


def get_or_create_requester(conn, token_hash, *, ip, user_agent, now=None):
    row = conn.execute(
        "select * from requesters where device_token_hash=?", (token_hash,)
    ).fetchone()
    if row:
        return row
    stamp = to_iso(now or utcnow())
    conn.execute(
        "insert into requesters(device_token_hash,name,department_id,device_name,"
        "last_ip,last_user_agent,created_at,updated_at,last_seen_at)"
        " values(?,?,?,?,?,?,?,?,?)",
        (token_hash, "", None, "", ip, user_agent, stamp, stamp, stamp),
    )
    conn.commit()
    return conn.execute(
        "select * from requesters where device_token_hash=?", (token_hash,)
    ).fetchone()


def find_requester(conn, token_hash):
    return conn.execute(
        "select * from requesters where device_token_hash=?", (token_hash,)
    ).fetchone()


def ensure_requester(request, conn, *, ip, user_agent):
    token = request.cookies.get("device")
    if token:
        h = hashlib.sha256(token.encode()).hexdigest()
        row = find_requester(conn, h)
        if row:
            return row, None
    new_token = secrets.token_urlsafe(32)
    h = hashlib.sha256(new_token.encode()).hexdigest()
    row = get_or_create_requester(conn, h, ip=ip, user_agent=user_agent)
    return row, new_token


def list_requesters(conn, *, q="", only_open=False, active_since=None):
    clauses = []
    params: list = []
    if q:
        clauses.append("(lower(name) like lower(?) or lower(device_name) like lower(?))")
        params.extend([f"%{q}%", f"%{q}%"])
    if only_open:
        clauses.append(
            "id in (select requester_id from tickets where state != 'resuelta')"
        )
    if active_since:
        clauses.append("last_seen_at >= ?")
        params.append(active_since)
    sql = "select * from requesters"
    if clauses:
        sql += " where " + " and ".join(clauses)
    sql += " order by last_seen_at desc, lower(name)"
    return list(conn.execute(sql, params))


def requester_history(conn, requester_id):
    return list(
        conn.execute(
            "select * from tickets where requester_id=? order by created_at desc",
            (requester_id,),
        )
    )


def update_requester(
    conn,
    requester_id,
    *,
    name=None,
    department_id=None,
    device_name=None,
    apply_history=False,
    actor_id=None,
    now=None,
):
    current = conn.execute(
        "select * from requesters where id=?", (requester_id,)
    ).fetchone()
    if current is None:
        raise ValueError("Solicitante no encontrado")
    new_name = current["name"] if name is None else (name or "").strip()
    new_department = (
        current["department_id"] if department_id is None else department_id
    )
    new_device = (
        current["device_name"] if device_name is None else (device_name or "").strip()
    )
    stamp = to_iso(now or utcnow())
    conn.execute(
        "update requesters set name=?, department_id=?, device_name=?, updated_at=?"
        " where id=?",
        (new_name, new_department, new_device, stamp, requester_id),
    )
    if apply_history:
        conn.execute(
            "update tickets set requester_name=? where requester_id=?",
            (new_name, requester_id),
        )
        if new_department is not None:
            conn.execute(
                "update tickets set department_id=? where requester_id=?",
                (new_department, requester_id),
            )
    conn.commit()
