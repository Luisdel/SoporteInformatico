with open('app/routes/auth.py') as f:
    c = f.read()
# Move admin lookup before insert
old = '    limiter.reset(f"{ip}:{username.lower()}")\n    token, csrf = new_token(), new_token()'
new = '    limiter.reset(f"{ip}:{username.lower()}")\n    admin_row = conn.execute("select id from admins where lower(username)=lower(?) and active=1", (username,)).fetchone()\n    if admin_row is None:\n        raise HTTPException(status_code=401, detail="No autenticado")\n    admin_id = admin_row[0]\n    token, csrf = new_token(), new_token()'
c = c.replace(old, new)
# Remove duplicated update after insert (we already have admin_id in insert now)
old2 = """    conn.execute(
            "update admin_sessions set admin_id = ? where token_hash = ?",
            (admin_id, hash_token(token)),
        )
    conn.commit()"""
new2 = "    conn.commit()"
c = c.replace(old2, new2)
with open('app/routes/auth.py', 'w') as f:
    f.write(c)
print('fixed')
