from __future__ import annotations
import secrets, hashlib
from app.db import connect

def get_or_create_requester(conn, token_hash, *, ip, user_agent, now=None):
    from app.timeutil import utcnow, to_iso
    row = conn.execute("select * from requesters where device_token_hash=?", (token_hash,)).fetchone()
    if row:
        return row
    conn.execute("insert into requesters(device_token_hash,name,department_id,device_name,last_ip,last_user_agent,created_at,updated_at,last_seen_at) values(?,?,?,?,?,?,?, ?, ?)",
        (token_hash, "", None, "", ip, user_agent, to_iso(now or utcnow()), to_iso(now or utcnow()), to_iso(now or utcnow())))
    conn.commit()
    return conn.execute("select * from requesters where device_token_hash=?", (token_hash,)).fetchone()

def find_requester(conn, token_hash):
    return conn.execute("select * from requesters where device_token_hash=?", (token_hash,)).fetchone()

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

def update_requester(conn, requester_id, *, name, department_id, device_name):
    from app.timeutil import utcnow, to_iso
    conn.execute("update requesters set name=?, department_id=?, device_name=?, updated_at=? where id=?",
        (name, department_id, device_name, to_iso(utcnow()), requester_id))
    conn.commit()
