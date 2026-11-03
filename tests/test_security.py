from datetime import timedelta
from app.db import connect, init_db
from app.security import (hash_password, verify_password, new_token, hash_token,
    create_admin_session, find_admin_session, touch_admin_session, RateLimiter)
from app.timeutil import utcnow, to_iso

def test_password_roundtrip():
    h = hash_password("clave-segura-1", iterations=1000)
    assert h.startswith("pbkdf2_sha256$1000$")
    assert verify_password("clave-segura-1", h)
    assert not verify_password("otra-clave-1", h)

def test_tokens_y_hash():
    t = new_token()
    assert len(t) >= 40 and hash_token(t) == hash_token(t) and hash_token(t) != t

def test_sesion_expira_por_inactividad_y_absoluta(tmp_path):
    p = tmp_path / "t.db"; init_db(p); c = connect(p)
    c.execute("insert into admins(username,display_name,password_hash,role,active,created_at,password_changed_at) values('a','A','x','admin',1,'x','x')")
    c.commit()
    now = utcnow()
    token, csrf = create_admin_session(c, 1, ip="1.2.3.4", user_agent="t", hours=12, now=now)
    assert find_admin_session(c, token, now=now + timedelta(hours=11))
    assert find_admin_session(c, token, now=now + timedelta(hours=13)) is None
    token2, _ = create_admin_session(c, 1, ip=None, user_agent=None, hours=12, now=now)
    assert find_admin_session(c, token2, now=now + timedelta(days=8)) is None

def test_rate_limiter():
    reloj = [0.0]
    rl = RateLimiter(clock=lambda: reloj[0])
    assert all(rl.hit("k", 2, 60) for _ in range(2))
    assert rl.hit("k", 2, 60) is False
    reloj[0] = 61
    assert rl.hit("k", 2, 60) is True
