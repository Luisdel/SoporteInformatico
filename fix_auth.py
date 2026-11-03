with open('app/routes/auth.py') as f:
    c = f.read()
old = """    row = find_admin_session(conn, token, idle_hours=settings.session_hours)
    if row is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    conn.execute(
        "update admin_sessions set admin_id = ? where token_hash = ?",
        (row["admin_id"], hash_token(token)),
    )"""
new = """    admin_row = conn.execute("select id from admins where lower(username)=lower(?) and active=1", (username,)).fetchone()
    if admin_row is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    admin_id = admin_row[0]
    conn.execute(
        "update admin_sessions set admin_id = ? where token_hash = ?",
        (admin_id, hash_token(token)),
    )"""
c = c.replace(old, new)
old_insert = "(\n                hash_token(token),\n                csrf,\n                None,"
new_insert = "(\n                hash_token(token),\n                csrf,\n                admin_id,"
c = c.replace(old_insert, new_insert)
with open('app/routes/auth.py', 'w') as f:
    f.write(c)
print('auth fix ok')
