from datetime import timedelta
from app.db import connect, init_db
from app.security import (hash_password, verify_password, new_token, hash_token,
    create_admin_session, find_admin_session, touch_admin_session,
    delete_admin_session, RateLimiter)
from app.timeutil import utcnow


def _admin(conn):
    conn.execute("insert into admins(username,display_name,password_hash,role,active,created_at,password_changed_at) values('a','A','x','admin',1,'x','x')")
    conn.commit()


def test_password_roundtrip():
    h = hash_password("clave-segura-1", iterations=1000)
    assert h.startswith("pbkdf2_sha256$1000$")
    assert verify_password("clave-segura-1", h)
    assert not verify_password("otra-clave-1", h)


def test_verify_password_rechaza_formatos_corruptos():
    corruptos = [
        "",
        "x",
        "pbkdf2_sha256$1000$abc",
        "pbkdf2_sha256$mil$YWJj$ZGVm",
        "pbkdf2_sha256$0$YWJj$ZGVm",
        "pbkdf2_sha256$2000001$YWJj$ZGVm",
        "pbkdf2_sha256$1000$!!!$ZGVm",
        "pbkdf2_sha256$1000$YWJj$!!!",
        "otro_algoritmo$1000$YWJj$ZGVm",
        "pbkdf2_sha256$1000$YWJj$ZGVm$extra",
    ]
    for encoded in corruptos:
        assert verify_password("clave-segura-1", encoded) is False


def test_tokens_y_hash():
    t = new_token()
    assert len(t) >= 40 and hash_token(t) == hash_token(t) and hash_token(t) != t


def test_sesion_expira_por_inactividad_y_absoluta(tmp_path):
    p = tmp_path / "t.db"; init_db(p); c = connect(p)
    _admin(c)
    now = utcnow()
    token, csrf = create_admin_session(c, 1, ip="1.2.3.4", user_agent="t", hours=12, now=now)
    assert find_admin_session(c, token, now=now + timedelta(hours=11))
    assert find_admin_session(c, token, now=now + timedelta(hours=12)) is None
    assert find_admin_session(c, token, now=now + timedelta(hours=12, seconds=1)) is None

    token2, _ = create_admin_session(c, 1, ip=None, user_agent=None, hours=12, now=now)
    assert find_admin_session(c, token2, now=now + timedelta(days=7, seconds=-1),
                              idle_hours=10_000)
    assert find_admin_session(c, token2, now=now + timedelta(days=7),
                              idle_hours=10_000) is None
    assert find_admin_session(c, token2, now=now + timedelta(days=8)) is None
    assert c.execute(
        "select token_hash from admin_sessions where admin_id = 1"
    ).fetchone()[0] != token


def test_touch_extiende_inactividad_pero_no_la_absoluta(tmp_path):
    p = tmp_path / "t.db"; init_db(p); c = connect(p)
    _admin(c)
    now = utcnow()
    token, _ = create_admin_session(c, 1, ip=None, user_agent=None, hours=12, now=now)
    row = find_admin_session(c, token, now=now + timedelta(hours=11))
    assert row is not None
    touch_admin_session(c, row["session_id"], now=now + timedelta(hours=11))
    c.commit()
    assert find_admin_session(c, token, now=now + timedelta(hours=22))
    assert find_admin_session(c, token, now=now + timedelta(hours=23, seconds=1)) is None
    assert find_admin_session(c, token, now=now + timedelta(days=7),
                              idle_hours=10_000) is None


def test_delete_admin_session_revoca_el_token(tmp_path):
    p = tmp_path / "t.db"; init_db(p); c = connect(p)
    _admin(c)
    now = utcnow()
    token, _ = create_admin_session(c, 1, ip=None, user_agent=None, hours=12, now=now)
    delete_admin_session(c, token)
    c.commit()
    assert find_admin_session(c, token, now=now) is None
    assert c.execute("select count(*) from admin_sessions").fetchone()[0] == 0


def test_admin_desactivado_no_tiene_sesion(tmp_path):
    p = tmp_path / "t.db"; init_db(p); c = connect(p)
    _admin(c)
    now = utcnow()
    token, _ = create_admin_session(c, 1, ip=None, user_agent=None, hours=12, now=now)
    c.execute("update admins set active = 0 where id = 1")
    c.commit()
    assert find_admin_session(c, token, now=now) is None


def test_rate_limiter():
    reloj = [0.0]
    rl = RateLimiter(clock=lambda: reloj[0])
    assert all(rl.hit("k", 2, 60) for _ in range(2))
    assert rl.hit("k", 2, 60) is False
    reloj[0] = 61
    assert rl.hit("k", 2, 60) is True


def test_rate_limiter_purga_claves_obsoletas():
    reloj = [0.0]
    rl = RateLimiter(clock=lambda: reloj[0])
    for i in range(500):
        assert rl.hit(f"k{i}", 2, 60)
    assert len(rl._hits) == 500
    reloj[0] = 100_000
    assert rl.hit("vigente", 2, 60)
    assert len(rl._hits) == 1 and "vigente" in rl._hits


def test_rate_limiter_purga_con_muchas_claves():
    reloj = [0.0]
    rl = RateLimiter(clock=lambda: reloj[0])
    for i in range(5_000):
        rl.hit(f"k{i}", 2, 60)
    reloj[0] = 100_000
    assert rl.hit("vigente", 2, 60)
    assert len(rl._hits) == 1 and "vigente" in rl._hits
