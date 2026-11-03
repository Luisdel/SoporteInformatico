# Aplicación de incidencias — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir una aplicación web interna de incidencias: los usuarios abren y siguen sus incidencias sin contraseña desde el navegador, y los administradores las gestionan con login, asignación, catálogos y datos del equipo.

**Architecture:** Servidor FastAPI con plantillas Jinja2 y SQLite en un único proceso Uvicorn. Todo el frontend es HTML/CSS/JS propio servido desde el mismo servidor, sin CDN ni build. Los usuarios se identifican con una cookie de dispositivo; los admins con sesión en servidor y contraseña. Los adjuntos viven en disco y se sirven con comprobación de permisos.

**Tech Stack:** Python 3.13, FastAPI, Uvicorn, Jinja2, python-multipart, python-dotenv, SQLite (`sqlite3`), pytest y `TestClient` (httpx).

**Spec:** `docs/superpowers/specs/2026-11-03-gestion-incidencias-design.md`

---

## Global Constraints

- Python 3.11 o superior; entorno probado con 3.13.
- Dependencias permitidas: `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`, `python-dotenv`; en tests, `pytest` y `httpx`. Sin ORM.
- Nada de frameworks de frontend ni recursos externos/CDN. CSS y JS propios.
- Toda la interfaz en español.
- Fechas en UTC en la base (`isoformat()` con zona UTC) y mostradas en `Europe/Madrid` con formato `dd/mm/aaaa HH:MM`.
- SQLite en WAL, `busy_timeout=5000`, un solo worker de Uvicorn.
- Contraseñas PBKDF2-SHA256, 600 000 iteraciones en producción, sal de 16 bytes, mínimo 10 caracteres. Iteraciones configurables para tests.
- Sesión de admin: 12 h de inactividad y 7 días absolutos.
- Adjuntos: máximo 5 MB y 3 por mensaje; PNG, JPEG, WebP o PDF validados por firma real.
- Límites: login 5 intentos por IP+usuario cada 15 min; formulario público 10 incidencias por IP y hora.
- Rutas `/admin` y `/api/admin` exigen sesión; las de cuentas exigen rol `superadmin`.
- Nunca mostrar MAC o nombre de equipo inventados: si no se pueden obtener, `No disponible`.
- Código de incidencia `INC-YYYY-NNNN`, contador por año.
- Puerto por defecto 8000; sin TLS por defecto.
- Tests: `python -m pytest -q`. Cada tarea termina en commit.

## Review Focus

1. Equipo en otra subred o detrás de proxy: debe mostrarse la IP real o `No disponible`, nunca la MAC del router.
2. Incidencia con departamento o tipo ya archivado: el historial debe seguir mostrando su nombre, no romper la página.
3. El usuario responde a una incidencia resuelta: debe reabrirse una sola vez, con su evento y aviso, sin duplicar mensajes de sistema.
4. Adjunto con extensión falsa, HTML disfrazado o mayor de 5 MB: rechazo claro y sin archivo huérfano en disco.
5. Sesión caducada mientras se envía un formulario de admin: redirección al login, sin error 500 y sin perder silenciosamente lo escrito.

---

### Task 1: Esqueleto, configuración, fechas y `/salud`

**Files:**
- Create: `.gitignore`, `requirements.txt`, `.env.example`, `app/__init__.py`, `app/config.py`, `app/timeutil.py`, `app/main.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_health.py`, `tests/test_timeutil.py`, `README.md`

**Interfaces:**
- Produces: `Settings` (dataclass con `host`, `port`, `db_path`, `upload_dir`, `timezone`, `trusted_proxies`, `tls_cert`, `tls_key`, `session_hours`, `max_upload_mb`, `secure_cookies`, `pbkdf2_iterations`, `resolve_hostnames`), `load_settings(env=None) -> Settings`, `create_app(settings=None) -> FastAPI`, `utcnow()`, `to_iso(dt)`, `from_iso(s)`, `fmt_local(iso_ts, tz)`.

- [ ] **Step 1: Inicializar el repositorio y las dependencias**

```bash
git init
```

`.gitignore`: `.venv/`, `__pycache__/`, `.pytest_cache/`, `.env`, `data/`, `.superpowers/`, `*.pyc`.

`requirements.txt`:

```
fastapi>=0.115,<1
uvicorn[standard]>=0.30,<1
jinja2>=3.1,<4
python-multipart>=0.0.9,<1
python-dotenv>=1.0,<2
pytest>=8,<9
httpx>=0.27,<1
```

Instalar: `python -m pip install -r requirements.txt`.

- [ ] **Step 2: Escribir los tests que fallan**

```python
# tests/test_health.py
from app.config import load_settings

def test_salud(client):
    r = client.get("/salud")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

def test_settings_defaults(tmp_path):
    s = load_settings({"DB_PATH": str(tmp_path / "i.db"), "UPLOAD_DIR": str(tmp_path / "up")})
    assert (s.host, s.port, s.timezone, s.session_hours, s.max_upload_mb) == (
        "0.0.0.0", 8000, "Europe/Madrid", 12, 5)
    assert s.trusted_proxies == ()
    assert s.pbkdf2_iterations == 600_000
```

```python
# tests/test_timeutil.py
from app.timeutil import fmt_local

def test_fmt_local_usa_madrid():
    assert fmt_local("2026-11-03T08:12:00+00:00", "Europe/Madrid") == "03/11/2026 09:12"

def test_fmt_local_none():
    assert fmt_local(None, "Europe/Madrid") == "—"
```

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        host="127.0.0.1", port=8000,
        db_path=tmp_path / "test.db", upload_dir=tmp_path / "uploads",
        timezone="Europe/Madrid", trusted_proxies=(),
        tls_cert=None, tls_key=None, session_hours=12,
        max_upload_mb=5, secure_cookies=False,
        pbkdf2_iterations=1_000, resolve_hostnames=False,
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    return TestClient(app, follow_redirects=False)
```

- [ ] **Step 3: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_health.py tests/test_timeutil.py -q`
Expected: FAIL por `ModuleNotFoundError: No module named 'app'` / `create_app`.

- [ ] **Step 4: Implementar configuración, fechas y app**

`app/config.py`: dataclass `Settings` con los campos del bloque Interfaces. `load_settings(env=None)` usa `os.environ` si `env is None`; lee `APP_HOST`, `APP_PORT`, `DB_PATH`, `UPLOAD_DIR`, `TIMEZONE`, `TRUSTED_PROXIES` (lista separada por comas de CIDR), `TLS_CERT`, `TLS_KEY`, `SESSION_HOURS`, `MAX_UPLOAD_MB`, `SECURE_COOKIES` (`1`/`true`), `PBKDF2_ITERATIONS` (por defecto 600000), `RESOLVE_HOSTNAMES` (por defecto `1`). Convierte rutas a `Path` y CIDR a `ipaddress.ip_network`.

`app/timeutil.py`: `utcnow()` devuelve `datetime.now(timezone.utc)`; `to_iso(dt)` usa `dt.astimezone(timezone.utc).isoformat()`; `from_iso(s)` usa `datetime.fromisoformat`; `fmt_local` devuelve `—` para `None` y formatea con `ZoneInfo(tz)`.

`app/main.py`:

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="Soporte Informático", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    @app.get("/salud")
    def salud():
        return {"status": "ok"}
    return app

app = create_app()
```

`.env.example` con todas las variables y sus valores por defecto. `README.md` mínimo con el nombre y "ver docs/superpowers/specs/2026-11-03-gestion-incidencias-design.md".

- [ ] **Step 5: Ejecutar y comprobar que pasa**

Run: `python -m pytest tests/test_health.py tests/test_timeutil.py -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add .gitignore requirements.txt .env.example app tests README.md
git commit -m "chore: esqueleto, configuracion y healthcheck"
```

---

### Task 2: Base de datos, esquema, migraciones y semilla

**Files:**
- Create: `app/db.py`, `app/catalogs.py`, `tests/test_db.py`
- Modify: `app/main.py`, `tests/conftest.py`

**Interfaces:**
- Produces: `connect(db_path) -> sqlite3.Connection` (Row factory, FK activas, WAL, busy_timeout 5000), `init_db(db_path) -> None`, `get_db(request) -> Iterator[Connection]`, `seed_defaults(conn) -> None`, `list_catalogs(conn, kind, active_only) -> list[Row]`.
- Consumes: `Settings` de Task 1.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_db.py
import sqlite3
from app.db import connect, init_db

def test_init_crea_tablas_y_siembra(tmp_path):
    p = tmp_path / "t.db"
    init_db(p)
    conn = connect(p)
    tablas = {r["name"] for r in conn.execute(
        "select name from sqlite_master where type='table'")}
    assert {"admins", "admin_sessions", "departments", "categories", "requesters",
            "tickets", "messages", "attachments", "ticket_events",
            "ticket_reads", "admin_audit", "ticket_counters"} <= tablas
    assert conn.execute("select count(*) from departments").fetchone()[0] == 5
    assert conn.execute("select count(*) from categories").fetchone()[0] == 7
    assert conn.execute("pragma journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("pragma foreign_keys").fetchone()[0] == 1

def test_init_es_idempotente(tmp_path):
    p = tmp_path / "t.db"
    init_db(p)
    init_db(p)
    conn = connect(p)
    assert conn.execute("select count(*) from departments").fetchone()[0] == 5

def test_nombre_de_departamento_duplicado(tmp_path):
    p = tmp_path / "t.db"
    init_db(p)
    conn = connect(p)
    try:
        conn.execute("insert into departments(name,active,sort_order,created_at) values('Administración',1,9,'x')")
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("debería rechazar duplicados sin distinguir mayúsculas")
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_db.py -q`
Expected: FAIL, `app.db` no existe.

- [ ] **Step 3: Implementar `app/db.py` con el esquema**

`connect` abre con `sqlite3.connect(path, timeout=5)`, `row_factory = sqlite3.Row`, ejecuta `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`.

`init_db` crea el directorio padre, lee `PRAGMA user_version`, aplica `MIGRATIONS[version:]` con `executescript`, actualiza `user_version`, y llama a `seed_defaults(conn)`.

Esquema v1 (copiar tal cual, nombres y CHECK incluidos):

```sql
CREATE TABLE admins (
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL,
  display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('superadmin','admin')),
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  last_login_at TEXT,
  password_changed_at TEXT NOT NULL
);
CREATE UNIQUE INDEX admins_username_uq ON admins(lower(username));

CREATE TABLE admin_sessions (
  id INTEGER PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  csrf_token TEXT NOT NULL,
  admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  ip TEXT,
  user_agent TEXT
);
CREATE INDEX admin_sessions_admin_idx ON admin_sessions(admin_id);

CREATE TABLE departments (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX departments_name_uq ON departments(lower(name));

CREATE TABLE categories (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX categories_name_uq ON categories(lower(name));

CREATE TABLE requesters (
  id INTEGER PRIMARY KEY,
  device_token_hash TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL DEFAULT '',
  department_id INTEGER REFERENCES departments(id),
  device_name TEXT NOT NULL DEFAULT '',
  last_ip TEXT,
  last_mac TEXT,
  last_user_agent TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

CREATE TABLE tickets (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  requester_id INTEGER NOT NULL REFERENCES requesters(id),
  requester_name TEXT NOT NULL,
  department_id INTEGER NOT NULL REFERENCES departments(id),
  category_id INTEGER NOT NULL REFERENCES categories(id),
  priority TEXT NOT NULL CHECK (priority IN ('baja','normal','alta','urgente')),
  state TEXT NOT NULL CHECK (state IN ('nueva','en_curso','en_espera','resuelta')),
  subject TEXT NOT NULL,
  description TEXT NOT NULL,
  assigned_admin_id INTEGER REFERENCES admins(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  resolved_at TEXT,
  requester_last_read_at TEXT,
  client_ip TEXT,
  client_mac TEXT,
  client_hostname TEXT,
  client_user_agent TEXT,
  reopened_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX tickets_requester_idx ON tickets(requester_id, created_at DESC);
CREATE INDEX tickets_state_idx ON tickets(state, updated_at DESC);
CREATE INDEX tickets_assigned_idx ON tickets(assigned_admin_id, state);

CREATE TABLE messages (
  id INTEGER PRIMARY KEY,
  ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  author_type TEXT NOT NULL CHECK (author_type IN ('requester','admin','system')),
  author_requester_id INTEGER REFERENCES requesters(id),
  author_admin_id INTEGER REFERENCES admins(id),
  body TEXT NOT NULL,
  is_internal INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX messages_ticket_idx ON messages(ticket_id, created_at);

CREATE TABLE attachments (
  id INTEGER PRIMARY KEY,
  ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  original_name TEXT NOT NULL,
  stored_name TEXT NOT NULL,
  mime TEXT NOT NULL,
  size INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE ticket_events (
  id INTEGER PRIMARY KEY,
  ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  admin_id INTEGER REFERENCES admins(id),
  event_type TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE ticket_reads (
  admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
  ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  last_read_at TEXT NOT NULL,
  PRIMARY KEY (admin_id, ticket_id)
);

CREATE TABLE admin_audit (
  id INTEGER PRIMARY KEY,
  admin_id INTEGER REFERENCES admins(id),
  action TEXT NOT NULL,
  detail TEXT,
  ip TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE ticket_counters (
  year INTEGER PRIMARY KEY,
  value INTEGER NOT NULL
);
```

`get_db(request)`:

```python
def get_db(request: Request):
    settings = request.app.state.settings
    conn = connect(settings.db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

`seed_defaults(conn)` inserta solo si la tabla está vacía: departamentos `Administración, Comercial, Producción, Almacén, Dirección`; tipos `Correo / Outlook, Hardware, Software, Red / Internet, Impresora, Accesos y contraseñas, Otro`; `sort_order` 10, 20, 30…; `created_at = to_iso(utcnow())`.

`app/catalogs.py` en esta tarea solo tiene `seed_defaults` y `list_catalogs(conn, kind, active_only)`. `kind` debe validarse contra `{"departments", "categories"}` y lanzar `CatalogError`.

Modificar `create_app` para llamar `init_db(settings.db_path)` (las plantillas y `/static` llegan en Task 4).

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `python -m pytest tests/test_db.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/catalogs.py app/main.py tests/test_db.py
git commit -m "feat: esquema sqlite, migraciones y semilla de catalogos"
```

---

### Task 3: Contraseñas, sesiones, CSRF y límites de intentos

**Files:**
- Create: `app/security.py`, `tests/test_security.py`
- Modify: `app/config.py` (si falta algún campo)

**Interfaces:**
- Produces: `hash_password(password, iterations=600000) -> str`, `verify_password(password, encoded) -> bool`, `new_token(nbytes=32) -> str`, `hash_token(token) -> str`, `create_admin_session(conn, admin_id, *, ip, user_agent, hours, now=None) -> tuple[str, str]` (token, csrf), `find_admin_session(conn, token, *, now=None, idle_hours=12) -> Row | None`, `touch_admin_session(conn, session_id, *, now=None) -> None`, `delete_admin_session(conn, token) -> None`, `RateLimiter(clock=time.monotonic)` con `hit(key, limit, window) -> bool` y `reset(key)`.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_security.py
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
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_security.py -q`
Expected: FAIL, `app.security` no existe.

- [ ] **Step 3: Implementar**

Formato de hash: `pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>` con `base64.b64encode`, sal de 16 bytes y `hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)`. `verify_password` parsea, limita iteraciones a un rango seguro (1..2_000_000) y compara con `hmac.compare_digest`.

`create_admin_session` genera `token = new_token()`, `csrf = new_token()`, guarda `hash_token(token)`, `last_seen_at = now`, `expires_at = now + 7 días`. `find_admin_session` une `admin_sessions` con `admins`, rechaza `active=0`, `expires_at <= now` o `last_seen_at <= now - idle_hours*3600`; devuelve la fila con alias `s.id AS session_id`, `s.csrf_token`, `a.id AS admin_id`, `a.username`, `a.display_name`, `a.role`. `touch_admin_session` actualiza `last_seen_at`. `delete_admin_session` borra por hash.

`RateLimiter` usa `dict[str, deque[float]]`; en `hit` descarta marcas fuera de la ventana, comprueba longitud y añade la marca actual solo si permite.

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `python -m pytest tests/test_security.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/security.py tests/test_security.py
git commit -m "feat: hash de contrasenas, sesiones y rate limiter"
```

---

### Task 4: Cuentas de admin, login, logout y guardia de sesión

**Files:**
- Create: `app/admins.py`, `app/auth.py`, `app/routes/__init__.py`, `app/routes/auth.py`, `app/routes/admin.py`, `app/manage.py`, `app/templates/base.html`, `app/templates/admin/login.html`, `app/templates/admin/index.html`, `app/static/app.css`, `app/static/app.js`, `tests/test_auth.py`
- Modify: `app/main.py`, `tests/conftest.py`

**Interfaces:**
- Produces: `create_admin(conn, *, username, display_name, password, role="admin", iterations=600_000, now=None) -> int`, `create_superadmin(conn, username, password, *, iterations=600_000) -> int`, `authenticate(conn, username, password) -> Row | None`, `list_admins(conn) -> list[Row]`, `set_active(conn, admin_id, active, *, actor_id)`, `set_role(conn, admin_id, role, *, actor_id)`, `reset_password(conn, admin_id, new_password, *, actor_id, iterations=600_000)`, `change_own_password(conn, admin_id, current, new, *, keep_session_id, iterations=600_000)`, `audit(conn, actor_id, action, detail, ip)`, `AdminRuleError(ValueError)`.
- Produces: `require_admin(request, conn=Depends(get_db)) -> AdminContext`, `require_superadmin(admin=Depends(require_admin)) -> AdminContext`, `verify_csrf(admin, token) -> None`.
- `AdminContext`: `id`, `username`, `display_name`, `role`, `csrf_token`, `session_id`.
- Cookie de sesión: `admin_session`; cookie de CSRF de login: `login_csrf`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
# tests/test_auth.py
from app.admins import create_admin
from app.db import connect
from tests.conftest import csrf_from

def test_crear_admin_valida_password(settings):
    conn = connect(settings.db_path)
    try:
        create_admin(conn, username="x", display_name="X", password="corta")
    except ValueError:
        pass
    else:
        raise AssertionError("debe exigir 10 caracteres")

def test_login_y_logout(admin, client):
    r = client.get("/admin/login")
    assert r.status_code == 200 and "login_csrf" in r.cookies
    token = r.cookies["login_csrf"]
    r = client.post("/admin/login", data={
        "username": "javier", "password": "clave-segura-1", "csrf_token": token})
    assert r.status_code == 303 and r.headers["location"] == "/admin"
    assert client.get("/admin").status_code == 200
    html = client.get("/admin").text
    assert client.post("/admin/logout", data={"csrf_token": csrf_from(html)}).status_code == 303
    assert client.get("/admin").status_code == 303

def test_sin_sesion_redirige_al_login(client):
    r = client.get("/admin")
    assert r.status_code == 303
    assert r.headers["location"].startswith("/admin/login")

def test_password_incorrecta(admin, client):
    client.get("/admin/login")
    token = client.cookies["login_csrf"]
    r = client.post("/admin/login", data={
        "username": "javier", "password": "incorrecta-1", "csrf_token": token})
    assert r.status_code == 401
    assert "Usuario o contraseña incorrectos" in r.text

def test_login_sin_csrf(admin, client):
    client.get("/admin/login")
    r = client.post("/admin/login", data={
        "username": "javier", "password": "clave-segura-1", "csrf_token": "malo"})
    assert r.status_code == 400

def test_limite_de_intentos(admin, client):
    for _ in range(5):
        client.get("/admin/login")
        client.post("/admin/login", data={
            "username": "javier", "password": "mala-clave-1",
            "csrf_token": client.cookies["login_csrf"]})
    client.get("/admin/login")
    r = client.post("/admin/login", data={
        "username": "javier", "password": "clave-segura-1",
        "csrf_token": client.cookies["login_csrf"]})
    assert r.status_code == 429
```

`tests/conftest.py` añade:

```python
from app.admins import create_admin
from app.db import connect

@pytest.fixture
def admin(app, settings):
    conn = connect(settings.db_path)
    admin_id = create_admin(conn, username="javier", display_name="Javier Pérez",
                            password="clave-segura-1", role="superadmin",
                            iterations=1000)
    conn.commit(); conn.close()
    return admin_id

@pytest.fixture
def admin_client(client, admin):
    client.get("/admin/login")
    token = client.cookies["login_csrf"]
    r = client.post("/admin/login", data={
        "username": "javier", "password": "clave-segura-1", "csrf_token": token})
    assert r.status_code == 303
    return client

def csrf_from(html: str) -> str:
    import re
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_auth.py -q`
Expected: FAIL, `app.admins` no existe.

- [ ] **Step 3: Implementar cuentas, login y guardia**

`app/admins.py`: validaciones de usuario (3–40 caracteres, `[a-z0-9._-]` en minúsculas), nombre visible no vacío, contraseña ≥10. `active` como entero. `authenticate` busca por `lower(username)`, exige `active=1` y `verify_password`, y actualiza `last_login_at`. `list_admins` devuelve todas las cuentas ordenadas por rol y usuario. `audit` inserta en `admin_audit`. `set_active`/`set_role` cuentan superadmins activos y lanzan `AdminRuleError` si la operación dejaría cero, si el actor se degrada/desactiva a sí mismo, o si el objetivo no existe. `reset_password` y `change_own_password` usan `hash_password` con las iteraciones recibidas (600 000 por defecto); `manage.py` usa 600000 y los tests 1000.

`app/auth.py`:

```python
def require_admin(request: Request, conn=Depends(get_db)) -> AdminContext:
    token = request.cookies.get("admin_session")
    row = find_admin_session(conn, token, idle_hours=request.app.state.settings.session_hours) if token else None
    if row is None:
        if request.url.path.startswith("/api/"):
            raise HTTPException(status_code=401, detail="No autenticado")
        raise HTTPException(status_code=303,
            headers={"Location": f"/admin/login?next={quote(request.url.path, safe='')}"})
    touch_admin_session(conn, row["session_id"])
    return AdminContext(id=row["admin_id"], username=row["username"],
        display_name=row["display_name"], role=row["role"],
        csrf_token=row["csrf_token"], session_id=row["session_id"])

def require_superadmin(admin=Depends(require_admin)) -> AdminContext:
    if admin.role != "superadmin":
        raise HTTPException(status_code=403, detail="Solo para superadmins")
    return admin

def verify_csrf(admin: AdminContext, token: str) -> None:
    if not hmac.compare_digest(admin.csrf_token, token or ""):
        raise HTTPException(status_code=400, detail="Token CSRF inválido")
```

`app/routes/auth.py`: `GET /admin/login` (si ya hay sesión, 303 a `/admin`), `POST /admin/login`, `POST /admin/logout`. Login compara primero el CSRF de doble envío (`login_csrf` cookie vs campo) y luego `RateLimiter.hit(f"{ip}:{username.lower()}", 5, 900)`; en éxito `limiter.reset`. Sesión con `settings.session_hours` y cookie `admin_session` `HttpOnly`, `SameSite=Lax`, `max_age=7*24*3600`, `secure=settings.secure_cookies`. `next` solo se acepta si empieza por `/admin`. Logout requiere sesión y CSRF, borra la sesión y la cookie.

`app/routes/admin.py` (nuevo): `GET /admin` con `Depends(require_admin)`, render `admin/index.html` con “Bandeja de incidencias (pendiente de la tarea 9)” y el formulario de logout.

`app/main.py`: incluir routers, montar `/static` con `StaticFiles`, crear `app.state.templates = Jinja2Templates(directory=...)` con el filtro `localdt` (usa `fmt_local` y la zona de `Settings`) y definir `app.state.login_limiter` / `app.state.public_limiter`.

`app/templates/base.html`: `<!DOCTYPE html>`, `<html lang="es">`, `<meta viewport>`, enlace a `/static/app.css`, cabecera con marca “Soporte Informático”, bloque `nav`, bloque `content`, y `<script src="/static/app.js" defer>` (el archivo puede estar vacío hasta Task 8). Todos los formularios de admin incluyen `<input type="hidden" name="csrf_token" value="{{ csrf_token }}">`. `admin/login.html` extiende base y muestra el formulario con `csrf_token`. `admin/index.html` extiende base.

`app/static/app.css`: tokens exactos `--bg:#eef2f7; --card:#fff; --ink:#0f172a; --muted:#64748b; --line:#dbe3ec; --blue:#1f6feb; --blue-soft:#e8f0fe; --green:#15803d; --green-soft:#e7f6ec; --amber:#b45309; --amber-soft:#fdf1dc; --red:#b91c1c; --red-soft:#fdeaea; --gray-soft:#eef2f7;`. Fuente `"Segoe UI", system-ui, sans-serif`. Clases base: `.app`, `.topbar`, `.body`, `.card`, `.btn`, `.btn-primary`, `.btn-ghost`, `.btn-danger`, `.badge`, `.field input/select/textarea`, `.flash`, `.table`. Todos los campos llevan `<label for>`; `:focus-visible` con contorno visible; navegación completa por teclado. Referencia visual: `.superpowers/mockups/mockup-v1.html`.

`app/manage.py`: `create_admin`/`create_superadmin` con `argparse`; `create-superadmin [--username] [--from-env]` pide contraseña con `getpass` (o `SUPERADMIN_USER`/`SUPERADMIN_PASSWORD`); `reset-password --username`; llama antes a `init_db`, usa 600000 iteraciones y hace commit.

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `python -m pytest tests/test_auth.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add app/admins.py app/auth.py app/routes app/manage.py app/templates app/static app/main.py tests/test_auth.py tests/conftest.py
git commit -m "feat: login de admin, sesiones y comando de superadmin"
```

---

### Task 5: Captura honesta de datos del equipo

**Files:**
- Create: `app/pcinfo.py`, `tests/test_pcinfo.py`

**Interfaces:**
- Produces: `ClientInfo(ip, mac, hostname, browser, os, user_agent="")` (dataclass congelado), `client_ip(request, trusted_proxies)`, `lookup_mac(ip, *, runner=None, system=None)`, `lookup_hostname(ip, *, resolver=socket.gethostbyaddr, timeout=1.0)`, `default_gateway_mac(*, runner=None, system=None)`, `parse_user_agent(ua) -> tuple[str, str]`, `collect(request, settings, *, mac_lookup=None, hostname_lookup=None, gateway_mac_fn=None) -> ClientInfo`.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_pcinfo.py
import subprocess
from ipaddress import ip_network
from app.pcinfo import client_ip, lookup_mac, lookup_hostname, parse_user_agent, collect

def fake_request(peer, headers=None):
    from starlette.requests import Request
    raw = [(b"host", b"test")] + [(k.encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {"type": "http", "method": "GET", "path": "/", "headers": raw,
             "client": (peer, 1234), "query_string": b"", "scheme": "http", "server": ("t", 80)}
    return Request(scope)

def test_xff_solo_desde_proxy_confiable():
    req = fake_request("10.0.0.5", {"x-forwarded-for": "1.2.3.4, 10.0.0.5"})
    assert client_ip(req, (ip_network("10.0.0.0/8"),)) == "1.2.3.4"
    assert client_ip(req, ()) == "10.0.0.5"

def test_mac_linux_y_windows():
    out = "192.168.1.20 dev eth0 lladdr 3c:7c:3f:1a:2b:9d REACHABLE\n"
    run = lambda cmd: subprocess.CompletedProcess(cmd, 0, out, "")
    assert lookup_mac("192.168.1.20", runner=run, system="Linux") == "3C:7C:3F:1A:2B:9D"
    out2 = "  192.168.1.20          3c-7c-3f-1a-2b-9d     dinámico\n"
    run2 = lambda cmd: subprocess.CompletedProcess(cmd, 0, out2, "")
    assert lookup_mac("192.168.1.20", runner=run2, system="Windows") == "3C:7C:3F:1A:2B:9D"

def test_mac_ausente():
    run = lambda cmd: subprocess.CompletedProcess(cmd, 0, "", "")
    assert lookup_mac("10.8.4.23", runner=run, system="Linux") is None

def test_hostname_falla_sin_romper():
    def boom(ip):
        raise OSError("sin dns")
    assert lookup_hostname("1.2.3.4", resolver=boom) is None

def test_user_agent():
    assert parse_user_agent("Mozilla/5.0 (Windows NT 10.0) Chrome/141.0 Safari/537.36") == ("Chrome", "Windows")
    assert parse_user_agent("Mozilla/5.0 (X11; Linux) Firefox/128.0") == ("Firefox", "Linux")

def test_collect_descarta_mac_de_puerta_de_enlace():
    req = fake_request("192.168.1.20", {"user-agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/141.0"})
    info = collect(req, type("S", (), {"trusted_proxies": (), "resolve_hostnames": False})(),
        mac_lookup=lambda ip: "3C:7C:3F:1A:2B:9D",
        hostname_lookup=lambda ip: "PC-01",
        gateway_mac_fn=lambda: "3C:7C:3F:1A:2B:9D")
    assert info.ip == "192.168.1.20"
    assert info.mac is None
    assert info.hostname == "PC-01"
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_pcinfo.py -q`
Expected: FAIL, `app.pcinfo` no existe.

- [ ] **Step 3: Implementar**

`client_ip`: si el peer pertenece a `trusted_proxies` y hay `x-forwarded-for`, devuelve el primer valor recortado; si no, el peer. Ignora valores no parseables.

`lookup_mac`: en Linux ejecuta `["ip","neigh","show",ip]`; en Windows `["arp","-a",ip]`; `system` por defecto `platform.system()`. Busca `([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}` en la salida, normaliza a mayúsculas con `:` y devuelve `None` si no hay. Nunca lanza: cualquier `OSError`/`TimeoutExpired` devuelve `None`.

`lookup_hostname`: ejecuta el resolver en un `ThreadPoolExecutor` con `future.result(timeout=timeout)`; cualquier excepción o timeout devuelve `None`.

`default_gateway_mac`: obtiene la IP de la puerta de enlace (`ip route show default` en Linux; `powershell -NoProfile -Command "(Get-NetRoute -DestinationPrefix 0.0.0.0/0 | Select-Object -First 1).NextHop"` en Windows) y llama a `lookup_mac`; cachea el resultado con `functools.lru_cache(maxsize=1)`; si falla, `None`.

`parse_user_agent`: devuelve `("Edge","Windows")`, `("Chrome","Windows")`, `("Firefox","Linux")`, `("Safari","macOS")` o `("Navegador","Desconocido")` según subcadenas; el orden importa (Edge antes que Chrome).

`collect`: obtiene `ip`, `ua`, `browser/os`; si `settings.resolve_hostnames` llama a `hostname_lookup`; MAC con `mac_lookup`, y si coincide con `gateway_mac_fn()` la descarta. Devuelve `ClientInfo(ip=..., mac=..., hostname=..., browser=..., os=..., user_agent=ua)`. Ninguna captura puede propagar excepción: todo `try/except` devuelve `None`.

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `python -m pytest tests/test_pcinfo.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add app/pcinfo.py tests/test_pcinfo.py
git commit -m "feat: captura de ip, mac, hostname y user-agent"
```

---

### Task 6: Formulario público, cookie de dispositivo y creación de incidencia

**Files:**
- Create: `app/requesters.py`, `app/tickets.py`, `app/routes/public.py`, `app/templates/public/new.html`, `app/templates/public/created.html`, `tests/test_public_create.py`
- Modify: `app/main.py`, `tests/conftest.py`

**Interfaces:**
- Produces: `get_or_create_requester(conn, token_hash, *, ip, user_agent, now=None) -> Row`, `find_requester(conn, token_hash) -> Row | None`, `ensure_requester(request, conn, *, ip, user_agent) -> tuple[Row, str | None]` (fila y token nuevo si se creó), `update_requester(conn, requester_id, *, name, department_id, device_name) -> None`.
- Produces: `next_code(conn, *, now) -> str`, `create_ticket(conn, *, requester_id, requester_name, department_id, category_id, priority, subject, description, client, now=None) -> int`, `get_ticket(conn, ticket_id) -> Row | None`, `list_for_requester(conn, requester_id) -> list[Row]`.
- Produce: `GET /`, `POST /incidencias`, `GET /mis-incidencias/{id}` redirige al detalle de Task 8 (mientras tanto, confirma la creación).

- [ ] **Step 1: Escribir los tests que fallan**

```python
# tests/test_public_create.py
from datetime import datetime, timezone
from app.db import connect
from app.pcinfo import ClientInfo

def congelar(monkeypatch):
    monkeypatch.setattr("app.routes.public.utcnow",
        lambda: datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc))

def preparar(app):
    app.state.pcinfo_collector = lambda request, settings: ClientInfo(
        ip="192.168.20.57", mac="3C:7C:3F:1A:2B:9D", hostname="PC-CONTAB-03",
        browser="Chrome", os="Windows")

def formulario(dept_id, cat_id, nombre="María López", asunto="No funciona el correo"):
    return {"name": nombre, "department_id": str(dept_id), "device_name": "PC-CONTAB-03",
            "category_id": str(cat_id), "priority": "alta", "subject": asunto,
            "description": "Me pide la contraseña una y otra vez."}

def ids(settings):
    conn = connect(settings.db_path)
    d = conn.execute("select id from departments order by sort_order limit 1").fetchone()[0]
    c = conn.execute("select id from categories order by sort_order limit 1").fetchone()[0]
    conn.close(); return d, c

def test_get_emite_cookie_y_muestra_catalogos(app, client, settings):
    preparar(app)
    r = client.get("/")
    assert r.status_code == 200 and "device" in r.cookies
    assert "Administración" in r.text and "Correo / Outlook" in r.text

def test_crear_incidencia_con_codigo_y_datos(app, client, settings, monkeypatch):
    preparar(app)
    congelar(monkeypatch)
    d, c = ids(settings)
    r = client.post("/incidencias", data=formulario(d, c))
    assert r.status_code == 303
    conn = connect(settings.db_path)
    t = conn.execute("select * from tickets").fetchone()
    m = conn.execute("select * from messages where ticket_id=?", (t["id"],)).fetchone()
    assert t["code"] == "INC-2026-0001"
    assert t["requester_name"] == "María López" and t["client_mac"] == "3C:7C:3F:1A:2B:9D"
    assert (t["state"], t["priority"], t["client_ip"]) == ("nueva", "alta", "192.168.20.57")
    assert m["author_type"] == "requester" and m["body"] == "Me pide la contraseña una y otra vez."
    conn.close()

def test_segunda_incidencia_incrementa_y_recuerda(app, client, settings, monkeypatch):
    preparar(app)
    congelar(monkeypatch)
    d, c = ids(settings)
    client.post("/incidencias", data=formulario(d, c))
    r = client.get("/")
    assert 'value="María López"' in r.text
    client.post("/incidencias", data=formulario(d, c, asunto="Otra cosa"))
    conn = connect(settings.db_path)
    assert [x[0] for x in conn.execute("select code from tickets order by id")] == [
        "INC-2026-0001", "INC-2026-0002"]
    conn.close()

def test_validacion_rechaza_sin_crear(app, client, settings):
    preparar(app)
    d, c = ids(settings)
    datos = formulario(d, c, nombre="")
    r = client.post("/incidencias", data=datos)
    assert r.status_code == 400
    conn = connect(settings.db_path)
    assert conn.execute("select count(*) from tickets").fetchone()[0] == 0
    conn.close()

def test_codigos_unicos_en_paralelo(app, settings):
    from concurrent.futures import ThreadPoolExecutor
    from app.tickets import next_code
    def emitir(_):
        c = connect(settings.db_path)
        try:
            code = next_code(c, now=datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc))
            c.commit()
            return code
        finally:
            c.close()
    with ThreadPoolExecutor(max_workers=8) as ex:
        codes = list(ex.map(emitir, range(8)))
    assert len(set(codes)) == 8
    assert all(c.startswith("INC-2026-") for c in codes)
```

La ruta calcula `now = utcnow()` una vez y lo pasa a `create_ticket(..., now=now)`; `next_code` usa ese mismo `now`. Los tests congelan el reloj con el helper `congelar(monkeypatch)`.

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_public_create.py -q`
Expected: FAIL, rutas y módulos no existen.

- [ ] **Step 3: Implementar**

`app/requesters.py`: `find_requester` por `device_token_hash`; `get_or_create_requester` crea con nombre vacío y `last_ip`/`last_user_agent`; `ensure_requester` lee la cookie `device` y devuelve la fila existente o crea una nueva con token aleatorio (devuelve `(row, token)` solo en ese caso); `update_requester` actualiza nombre, departamento y equipo (sin tocar incidencias pasadas). No hace commit.

`app/tickets.py`: constantes `PRIORITIES` y `STATES`. `next_code` hace upsert en `ticket_counters` para el año y devuelve `f"INC-{year}-{value:04d}"`. `create_ticket` valida prioridad y longitudes (asunto 3–120, descripción 10–4000), inserta ticket con `requester_name` congelado y `client_ip/mac/hostname/user_agent`, y crea el primer mensaje `author_type='requester'` con la descripción. `list_for_requester` ordena por `updated_at DESC`. En `create_app`: `app.state.pcinfo_collector = pcinfo.collect`.

`app/routes/public.py`:

- `GET /`: `ensure_requester` (devuelve fila y token nuevo si lo creó), catálogos activos, render `public/new.html`; si hay token nuevo, `set_cookie("device", token, max_age=31_536_000, httponly=True, samesite="lax", secure=settings.secure_cookies)`. Si el requester no tiene `device_name` y `settings.resolve_hostnames`, intenta `lookup_hostname(client_ip(request, settings.trusted_proxies))` para precargar el campo; si falla, se deja vacío.
- `POST /incidencias`: `RateLimiter.hit(client_ip(request, settings.trusted_proxies) or "desconocido", 10, 3600)` → 429 si no; valida nombre (2–80), ids existentes y activos, prioridad, asunto y descripción; captura `client = request.app.state.pcinfo_collector(request, settings)`; actualiza requester; `now = utcnow()` y lo pasa a `create_ticket(..., now=now)`; redirige 303 a `/mis-incidencias/{id}`.
- Errores de validación: render del formulario con `error` y estado 400, conservando lo escrito en un dict `form`.

`public/new.html`: formulario `method="post" action="/incidencias"`, campos nombre, departamento (select de activos), nombre del equipo, tipo, urgencia, asunto, descripción y botón “Enviar incidencia”. Muestra un bloque informativo con “Los datos del equipo se capturan automáticamente al enviar”.

`public/created.html`: “Incidencia registrada”, código, enlace a “Mis incidencias” y aviso de que se puede seguir por ahí.

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `python -m pytest tests/test_public_create.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/requesters.py app/tickets.py app/routes/public.py app/templates/public app/main.py tests/test_public_create.py tests/conftest.py
git commit -m "feat: formulario publico y creacion de incidencias"
```

---

### Task 7: Adjuntos validados y descarga con permisos

**Files:**
- Create: `app/uploads.py`, `app/routes/files.py`, `app/templates/partials/attachments.html`, `tests/test_uploads.py`
- Modify: `app/tickets.py` (firma de `create_ticket`), `app/routes/public.py`, `app/templates/public/new.html`, `app/main.py`

**Interfaces:**
- Produces: `SavedFile(original_name, stored_name, mime, size)`, `UploadError(ValueError)`, `save_upload(file: UploadFile, dest: Path, *, max_bytes: int) -> SavedFile` (async), `remove_saved(dest, saved) -> None`.
- `create_ticket` pasa a aceptar `attachments: list[SavedFile] = ()` e inserta una fila por adjunto ligada al primer mensaje.
- Ruta `GET /adjuntos/{attachment_id}`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
# tests/test_uploads.py
import asyncio
import pytest
from fastapi import UploadFile
from io import BytesIO
from app.uploads import save_upload, UploadError

def test_png_valido(tmp_path):
    f = UploadFile(filename="captura.png", file=BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 20))
    s = asyncio.run(save_upload(f, tmp_path, max_bytes=1024))
    assert s.mime == "image/png" and (tmp_path / s.stored_name).exists()

def test_html_disfrazado(tmp_path):
    f = UploadFile(filename="captura.png", file=BytesIO(b"<html>hola</html>"))
    with pytest.raises(UploadError):
        asyncio.run(save_upload(f, tmp_path, max_bytes=1024))
    assert list(tmp_path.iterdir()) == []

def test_demasiado_grande(tmp_path):
    f = UploadFile(filename="captura.png", file=BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 2048))
    with pytest.raises(UploadError):
        asyncio.run(save_upload(f, tmp_path, max_bytes=1024))
    assert list(tmp_path.iterdir()) == []
```

Test de integración en `tests/test_public_create.py`: enviar `files={"attachments": ("c.png", b"\x89PNG\r\n\x1a\n"+b"x"*10, "image/png")}`; comprobar fila en `attachments` y que `GET /adjuntos/{id}` devuelve 200 para el dueño y 404 para otro cliente (cookie distinta); el admin devuelve 200.

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_uploads.py -q`
Expected: FAIL, `app.uploads` no existe.

- [ ] **Step 3: Implementar**

`save_upload` crea `dest` con `mkdir(parents=True, exist_ok=True)`, lee en trozos de 64 KB a un archivo temporal `dest / (token + ".part")`, acumulando tamaño; si supera `max_bytes` o la firma no coincide lanza `UploadError` y borra el temporal. Firmas: PNG `\x89PNG\r\n\x1a\n`, JPEG `\xff\xd8\xff`, WebP `RIFF`+`WEBP` en bytes 8–12, PDF `%PDF-`. Renombra a `token + extension` y devuelve `SavedFile`.

`GET /adjuntos/{id}`: busca el adjunto y su ticket; si hay admin válido, permite; si no, exige cookie `device` cuyo requester sea el dueño; en cualquier otro caso 404. Devuelve `FileResponse` con `filename`, `media_type`, `X-Content-Type-Options: nosniff` y `Content-Disposition: attachment`.

`create_ticket`: tras insertar el primer mensaje, inserta las filas de `attachments` con `ticket_id`, `message_id`, nombre original, almacenado, mime y tamaño.

En `POST /incidencias`: recoge `form.getlist("attachments")`, descarta los vacíos, rechaza más de 3, guarda cada uno con `max_bytes = settings.max_upload_mb * 1024 * 1024`; si algo falla, elimina los ya guardados y renderiza error 400. Si la transacción de base falla, elimina los archivos.

`public/new.html`: `<form enctype="multipart/form-data">`, `<input type="file" name="attachments" multiple accept=".png,.jpg,.jpeg,.webp,.pdf">`, texto “Hasta 3 archivos, 5 MB cada uno”. `partials/attachments.html` pinta enlaces a `/adjuntos/{id}`.

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `python -m pytest tests/test_uploads.py tests/test_public_create.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/uploads.py app/routes/files.py app/templates tests
git commit -m "feat: adjuntos con validacion por firma y descarga autorizada"
```

---

### Task 8: «Mis incidencias»: historial, hilo, respuesta y reapertura

**Files:**
- Create: `app/ticket_actions.py`, `app/templates/public/list.html`, `app/templates/public/detail.html`, `app/static/app.js`, `tests/test_requester_thread.py`
- Modify: `app/routes/public.py`, `app/tickets.py`, `tests/conftest.py`

**Interfaces:**
- Produces: `post_requester_message(conn, ticket_id, requester_id, body, *, attachments=(), now=None) -> None`, `mark_read_requester(conn, ticket_id, *, now=None)`, `requester_unread(conn, requester_id) -> int`, `get_ticket_for_requester(conn, ticket_id, requester_id) -> Row | None`, `list_messages(conn, ticket_id, *, include_internal=False) -> list[Row]`.
- Rutas: `GET /mis-incidencias`, `GET /mis-incidencias/{id}`, `POST /mis-incidencias/{id}/responder`, `GET /api/avisos`.
- `tests/conftest.py` añade el fixture `make_ticket`.

- [ ] **Step 1: Añadir el fixture de datos y escribir los tests**

```python
# tests/conftest.py (añadir)
import pytest
from app.pcinfo import ClientInfo
from app.security import hash_token
from app.tickets import create_ticket
from app.timeutil import utcnow, to_iso
from uuid import uuid4

@pytest.fixture
def make_ticket(app, settings):
    def _make(*, subject="Incidencia de prueba", state="nueva", priority="normal",
              requester_name="Ana Torres", department_id=None, category_id=None,
              assigned_admin_id=None, token=None):
        token = token or f"tok-{uuid4().hex}"
        conn = connect(settings.db_path)
        d = department_id or conn.execute("select id from departments order by sort_order limit 1").fetchone()[0]
        c = category_id or conn.execute("select id from categories order by sort_order limit 1").fetchone()[0]
        r = conn.execute(
            "insert into requesters(device_token_hash,name,department_id,created_at,updated_at,last_seen_at)"
            " values(?,?,?,?,?,?)",
            (hash_token(token), requester_name, d, "x", "x", "x")).lastrowid
        tid = create_ticket(conn, requester_id=r, requester_name=requester_name,
            department_id=d, category_id=c, priority=priority, subject=subject,
            description="Descripción de prueba suficientemente larga.",
            client=ClientInfo(ip="192.168.1.10", mac=None, hostname=None,
                              browser="Chrome", os="Windows"))
        conn.execute("update tickets set state=?, assigned_admin_id=?, resolved_at=? where id=?",
                     (state, assigned_admin_id,
                      to_iso(utcnow()) if state == "resuelta" else None, tid))
        conn.commit(); conn.close(); return tid
    return _make
```

```python
# tests/test_requester_thread.py
from app.db import connect
from app.pcinfo import ClientInfo
from app.timeutil import utcnow, to_iso

def crear_propia(app, client, settings):
    app.state.pcinfo_collector = lambda r, s: ClientInfo(
        ip="1.1.1.1", mac=None, hostname=None, browser="Chrome", os="Windows")
    conn = connect(settings.db_path)
    d = conn.execute("select id from departments order by sort_order limit 1").fetchone()[0]
    c = conn.execute("select id from categories order by sort_order limit 1").fetchone()[0]
    conn.close()
    r = client.post("/incidencias", data={
        "name": "María López", "department_id": str(d), "device_name": "PC-1",
        "category_id": str(c), "priority": "alta", "subject": "No funciona el correo",
        "description": "Me pide la contraseña una y otra vez."})
    assert r.status_code == 303
    return r.headers["location"].rstrip("/").split("/")[-1]

def test_lista_solo_las_suyas(app, client, settings, make_ticket):
    propia = crear_propia(app, client, settings)
    make_ticket(subject="Incidencia de otra persona")
    r = client.get("/mis-incidencias")
    assert "No funciona el correo" in r.text
    assert "Incidencia de otra persona" not in r.text
    assert propia in r.text

def test_no_puede_ver_ajena(app, client, make_ticket):
    ajena = make_ticket(subject="Privada")
    assert client.get(f"/mis-incidencias/{ajena}").status_code == 404

def test_responder_resuelta_reabre_una_vez(app, client, make_ticket, settings):
    tid = make_ticket(state="resuelta", subject="Se reabre", token="tok-reabre")
    conn = connect(settings.db_path)
    conn.execute("insert into messages(ticket_id,author_type,author_admin_id,body,is_internal,created_at)"
                 " values(?,'admin',NULL,'Resuelto','0',?)", (tid, to_iso(utcnow())))
    conn.commit(); conn.close()
    client.cookies.set("device", "tok-reabre")
    r = client.post(f"/mis-incidencias/{tid}/responder", data={"body": "Sigue fallando"})
    assert r.status_code == 303
    conn = connect(settings.db_path)
    t = conn.execute("select * from tickets where id=?", (tid,)).fetchone()
    assert (t["state"], t["resolved_at"], t["reopened_count"]) == ("en_curso", None, 1)
    assert conn.execute("select count(*) from ticket_events where ticket_id=? and event_type='reopen'", (tid,)).fetchone()[0] == 1
    assert conn.execute("select count(*) from messages where ticket_id=? and author_type='system'", (tid,)).fetchone()[0] == 1
    conn.close()

def test_nota_interna_nunca_se_muestra(app, client, make_ticket, settings):
    tid = make_ticket(token="tok-nota")
    conn = connect(settings.db_path); conn.execute(
        "insert into messages(ticket_id,author_type,body,is_internal,created_at)"
        " values(?,'admin','SECRETO INTERNO',1,?)", (tid, to_iso(utcnow()))); conn.commit(); conn.close()
    client.cookies.set("device", "tok-nota")
    assert "SECRETO INTERNO" not in client.get(f"/mis-incidencias/{tid}").text

def test_aviso_de_respuesta_nueva(app, client, make_ticket, settings):
    tid = make_ticket(token="tok-aviso")
    client.cookies.set("device", "tok-aviso")
    assert client.get("/api/avisos").json()["unread"] == 0
    conn = connect(settings.db_path); conn.execute(
        "insert into messages(ticket_id,author_type,body,is_internal,created_at)"
        " values(?,'admin','Te respondo',0,?)", (tid, to_iso(utcnow()))); conn.commit(); conn.close()
    assert client.get("/api/avisos").json()["unread"] == 1
    client.get(f"/mis-incidencias/{tid}")
    assert client.get("/api/avisos").json()["unread"] == 0
```

`make_ticket` acepta `token=` y guarda su `hash_token`; así el test puede fijar la cookie `device` con el token en claro. `crear_propia` usa el flujo público real para que el cliente reciba la cookie.

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_requester_thread.py -q`
Expected: FAIL, rutas y `app.ticket_actions` no existen.

- [ ] **Step 3: Implementar**

`app/tickets.py` añade las consultas del bloque Interfaces. `list_messages` excluye `is_internal=1` salvo que se pida.

`app/ticket_actions.py`: `post_requester_message` valida cuerpo (1–4000), inserta mensaje `author_type='requester'` y una fila por cada `SavedFile` de `attachments`; si el estado es `resuelta` pasa a `en_curso`, limpia `resolved_at`, incrementa `reopened_count`, inserta evento `reopen` y mensaje de sistema “Incidencia reabierta por el usuario.”; si es `en_espera` pasa a `en_curso` y evento `state`. Actualiza `updated_at`.

`app/routes/public.py`: lista y detalle con `ensure_requester` y filtro por `requester_id`; el detalle marca leído y pasa `messages`, `attachments` y `ticket`; `POST .../responder` comprueba propiedad, guarda hasta 3 adjuntos con `save_upload` y los pasa a `post_requester_message`, y redirige 303 al detalle. `GET /api/avisos` devuelve `{"unread": requester_unread(conn, requester.id)}` sin crear requester si no hay cookie (0).

`public/list.html`: tarjetas con código, asunto, estado, última actividad y punto de no leídas. `public/detail.html`: cabecera con código y estado, datos básicos, hilo (mensajes y adjuntos), caja de respuesta multipart con hasta 3 adjuntos y enlace de vuelta.

`app/static/app.js`: cada 30 s consulta el endpoint indicado en `document.body.dataset.poll` (`/api/avisos` o `/api/admin/avisos`), actualiza `[data-badge]` y pone `(n)` en `document.title`. Si no hay endpoint, no hace nada.

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `python -m pytest tests/test_requester_thread.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ticket_actions.py app/tickets.py app/routes/public.py app/templates/public app/static/app.js tests
git commit -m "feat: historial del usuario, respuestas y reapertura"
```

---

### Task 9: Bandeja de admin con filtros, búsqueda, paginación y contadores

**Files:**
- Create: `app/templates/admin/inbox.html`, `tests/test_admin_inbox.py`
- Modify: `app/tickets.py`, `app/routes/admin.py`, `app/templates/base.html` (nav de admin), `app/static/app.css`

**Interfaces:**
- Produces: `TicketFilters(q="", state=None, priority=None, department_id=None, category_id=None, assignment="todas", page=1, per_page=50)`, `list_admin(conn, filters, admin_id) -> list[Row]`, `count_admin(conn, filters, admin_id) -> int`, `stats(conn, admin_id) -> dict[str, int]` con claves `open`, `unassigned`, `urgent`, `resolved_week`, `mine`.
- Ruta: `GET /admin` con query params `q`, `state`, `priority`, `department_id`, `category_id`, `assignment`, `page`.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_admin_inbox.py
from app.tickets import TicketFilters, list_admin, stats
from app.db import connect

def test_filtros_y_busqueda(admin, make_ticket, settings):
    a = make_ticket(subject="Correo roto", state="nueva", priority="urgente")
    b = make_ticket(subject="Impresora", state="resuelta", priority="baja")
    conn = connect(settings.db_path)
    assert [r["id"] for r in list_admin(conn, TicketFilters(), admin)] [0] == a
    assert [r["id"] for r in list_admin(conn, TicketFilters(state="resuelta"), admin)] == [b]
    assert [r["id"] for r in list_admin(conn, TicketFilters(q="correo"), admin)] == [a]
    assert [r["id"] for r in list_admin(conn, TicketFilters(priority="urgente"), admin)] == [a]
    conn.close()

def test_stats(admin, make_ticket, settings):
    make_ticket(state="nueva")
    make_ticket(state="en_curso", priority="urgente")
    make_ticket(state="resuelta")
    conn = connect(settings.db_path)
    s = stats(conn, admin)
    assert (s["open"], s["unassigned"], s["urgent"], s["resolved_week"]) == (2, 2, 1, 1)
    conn.close()

def test_bandeja_muestra_incidencias(admin_client, make_ticket):
    make_ticket(subject="Correo roto")
    r = admin_client.get("/admin")
    assert r.status_code == 200
    assert "Correo roto" in r.text and "INC-2026-" in r.text
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_admin_inbox.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar**

`list_admin`: SELECT con joins a `departments`, `categories`, `admins` y subconsulta del último mensaje público; filtros dinámicos con parámetros (nunca interpolar valores), `LIKE '%'||?||'%'` sobre `code`, `subject`, `description`, `requester_name`; `assignment` `sin_asignar` → `assigned_admin_id IS NULL`, `mis` → `= admin_id`; orden por estado (nueva, en_curso, en_espera, resuelta), urgencia (urgente, alta, normal, baja) y `updated_at DESC`; `LIMIT per_page OFFSET (page-1)*per_page`.

`stats`: cinco consultas agregadas con las claves indicadas. `resolved_week` usa `resolved_at >= ahora - 7 días`.

`GET /admin`: parsea filtros, valida valores contra `STATES/PRIORITIES` (ignora inválidos), calcula `total` y páginas, render `admin/inbox.html`.

`inbox.html`: layout `.inbox-grid` de dos columnas en escritorio (lista a la izquierda, detalle a la derecha) que colapsa a una columna en pantallas estrechas. Contadores en tarjetas, formulario de filtros (búsqueda, estado, prioridad, asignación, departamento, tipo), lista de incidencias con código, asunto, solicitante, departamento, estado, urgencia, asignado y fecha, y paginación anterior/siguiente. Cada fila enlaza a `/admin?id={id}` para abrir el detalle en el panel derecho; un botón “Abrir” enlaza a `/admin/incidencias/{id}` para la vista completa/imprimible. Sin selección, el panel derecho muestra “Selecciona una incidencia”.

`base.html`: si `admin` está en el contexto, nav “Incidencias / Usuarios / Departamentos y tipos / Cuentas / Exportar CSV” y menú con nombre y “Salir”. Usuarios/Cuentas/Exportar se activan en tareas posteriores; por ahora enlazan a `#` salvo Incidencias.

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `python -m pytest tests/test_admin_inbox.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/tickets.py app/routes/admin.py app/templates/admin/inbox.html app/templates/base.html app/static/app.css tests/test_admin_inbox.py
git commit -m "feat: bandeja de admin con filtros y contadores"
```

---

### Task 10: Detalle de admin: respuesta, nota interna, estados y corrección de campos

**Files:**
- Create: `app/templates/admin/ticket.html`, `app/templates/partials/ticket_detail.html`, `tests/test_admin_ticket.py`
- Modify: `app/ticket_actions.py`, `app/tickets.py`, `app/routes/admin.py`, `app/templates/partials/attachments.html`

**Interfaces:**
- Produces: `post_admin_message(conn, ticket_id, admin_id, body, is_internal=False, attachments=(), *, now=None) -> None`, `assign(conn, ticket_id, admin_id, assignee_id, *, now=None) -> None`, `change_state(conn, ticket_id, admin_id, state, *, now=None) -> None`, `change_priority(conn, ticket_id, admin_id, priority, *, now=None) -> None`, `change_department(conn, ticket_id, admin_id, department_id, *, now=None) -> None`, `change_category(conn, ticket_id, admin_id, category_id, *, now=None) -> None`.
- Rutas: `GET /admin/incidencias/{id}`, `POST .../responder`, `POST .../estado`, `POST .../campos`.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_admin_ticket.py
from app.db import connect
from tests.conftest import csrf_from

def test_primera_respuesta_asigna_y_pone_en_curso(admin_client, admin, make_ticket, settings):
    tid = make_ticket(state="nueva")
    html = admin_client.get(f"/admin/incidencias/{tid}").text
    r = admin_client.post(f"/admin/incidencias/{tid}/responder",
        data={"body": "Lo reviso", "is_internal": "0", "csrf_token": csrf_from(html)})
    assert r.status_code == 303
    conn = connect(settings.db_path)
    t = conn.execute("select * from tickets where id=?", (tid,)).fetchone()
    assert (t["state"], t["assigned_admin_id"]) == ("en_curso", admin)
    assert conn.execute("select count(*) from ticket_events where ticket_id=? and event_type='assignment'", (tid,)).fetchone()[0] == 1
    conn.close()

def test_nota_interna_no_cambia_estado(admin_client, admin, make_ticket, settings):
    tid = make_ticket(state="nueva")
    html = admin_client.get(f"/admin/incidencias/{tid}").text
    admin_client.post(f"/admin/incidencias/{tid}/responder",
        data={"body": "Nota para mí", "is_internal": "1", "csrf_token": csrf_from(html)})
    conn = connect(settings.db_path)
    assert conn.execute("select state from tickets where id=?", (tid,)).fetchone()[0] == "nueva"
    assert conn.execute("select is_internal from messages where ticket_id=? order by id desc", (tid,)).fetchone()[0] == 1
    conn.close()

def test_resolver_crea_evento_y_mensaje_de_sistema(admin_client, make_ticket, settings):
    tid = make_ticket(state="en_curso")
    html = admin_client.get(f"/admin/incidencias/{tid}").text
    admin_client.post(f"/admin/incidencias/{tid}/estado",
        data={"state": "resuelta", "csrf_token": csrf_from(html)})
    conn = connect(settings.db_path)
    t = conn.execute("select * from tickets where id=?", (tid,)).fetchone()
    assert t["state"] == "resuelta" and t["resolved_at"] is not None
    assert conn.execute("select count(*) from ticket_events where ticket_id=? and event_type='resolve'", (tid,)).fetchone()[0] == 1
    assert conn.execute("select count(*) from messages where ticket_id=? and author_type='system'", (tid,)).fetchone()[0] == 1
    conn.close()

def test_cambiar_campos_deja_eventos(admin_client, make_ticket, settings):
    tid = make_ticket(priority="baja")
    conn = connect(settings.db_path)
    d = conn.execute("select id from departments where name='Comercial'").fetchone()[0]
    c = conn.execute("select id from categories where name='Hardware'").fetchone()[0]
    conn.close()
    html = admin_client.get(f"/admin/incidencias/{tid}").text
    admin_client.post(f"/admin/incidencias/{tid}/campos", data={
        "priority": "urgente", "department_id": str(d), "category_id": str(c),
        "csrf_token": csrf_from(html)})
    conn = connect(settings.db_path)
    t = conn.execute("select * from tickets where id=?", (tid,)).fetchone()
    assert (t["priority"], t["department_id"], t["category_id"]) == ("urgente", d, c)
    tipos = {x[0] for x in conn.execute("select event_type from ticket_events where ticket_id=?", (tid,))}
    assert {"priority", "department", "category"} <= tipos
    conn.close()

def test_no_se_puede_volver_a_nueva(admin_client, make_ticket):
    tid = make_ticket(state="en_curso")
    html = admin_client.get(f"/admin/incidencias/{tid}").text
    r = admin_client.post(f"/admin/incidencias/{tid}/estado",
        data={"state": "nueva", "csrf_token": csrf_from(html)})
    assert r.status_code == 400

def test_post_sin_csrf_es_rechazado(admin_client, make_ticket):
    tid = make_ticket()
    r = admin_client.post(f"/admin/incidencias/{tid}/estado", data={"state": "resuelta"})
    assert r.status_code == 400

def test_sesion_caducada_en_post_redirige(admin_client, admin, make_ticket, settings):
    tid = make_ticket()
    conn = connect(settings.db_path); conn.execute("delete from admin_sessions"); conn.commit(); conn.close()
    r = admin_client.post(f"/admin/incidencias/{tid}/estado", data={"state": "resuelta", "csrf_token": "x"})
    assert r.status_code == 303 and r.headers["location"].startswith("/admin/login")
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_admin_ticket.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar**

`post_admin_message`: valida cuerpo; inserta mensaje con `is_internal`; inserta una fila en `attachments` por cada `SavedFile` de `attachments`; si es público y la incidencia no tiene asignado, la asigna a `admin_id` (evento `assignment`); si es pública y está `nueva`, pasa a `en_curso` (evento `state`); actualiza `updated_at`. La nota interna no asigna ni cambia estado.

`assign`: valida que el admin exista y esté activo; `assignee_id=None` libera; inserta evento `assignment` con `old_value`/`new_value`; actualiza `updated_at`.

`change_state`: valida contra `STATES` y rechaza `nueva`; si el estado no cambia, no hace nada. Pasa de cualquier estado a `en_curso`/`en_espera`/`resuelta`. Al resolver: `resolved_at=now`, evento `resolve`, mensaje de sistema “Incidencia marcada como resuelta por {display_name}.”; al pasar a `en_espera`: evento `state`, mensaje “En espera de respuesta del usuario.”; al reabrir desde resuelta: `resolved_at=NULL`, evento `state`, mensaje “Incidencia reabierta por {display_name}.”.

`change_priority/department/category`: validan valor o id existente; si cambia, actualizan y registran evento con valores antiguo/nuevo.

`GET /admin/incidencias/{id}`: 404 si no existe; en esta tarea no marca lectura (Task 11 añade `mark_read_admin`); carga mensajes (incluidas notas internas), adjuntos y datos de equipo; render `admin/ticket.html`, que incluye `partials/ticket_detail.html`. Modificar `GET /admin` para aceptar `id`: si viene, carga la misma información y pasa `selected_ticket` a `inbox.html`, que incluye ese partial en el panel derecho; sin `id`, el panel muestra “Selecciona una incidencia”.

`POST .../responder`: lee `body`, `is_internal` y hasta 3 archivos; guarda cada uno con `save_upload` (5 MB); llama a `post_admin_message` con la lista; si la base falla, borra los archivos; redirige a `/admin?id={id}` para conservar el panel (o al detalle completo si se abrió desde él). `POST .../estado` y `.../campos` validan y llaman a sus funciones; los errores de regla se muestran con 400.

`partials/ticket_detail.html`: layout `.split` de dos columnas (hilo + panel de datos) que colapsa a una en pantallas estrechas; cabecera con código, asunto, estado/urgencia/tipo/departamento, botones “Asignármela/Liberar” (Task 11), “Marcar resuelta” con `data-confirm="¿Marcar la incidencia como resuelta?"`, “Copiar datos del equipo”; panel `.pcinfo` con usuario, departamento, equipo, IP, MAC (o “No disponible (otra subred)”), navegador/SO y fecha; hilo con notas internas resaltadas; formulario de respuesta con checkbox “Nota interna (no visible para el usuario)”, hasta 3 adjuntos y CSRF; formularios independientes para estado y campos. `admin/ticket.html` y `inbox.html` incluyen este partial; el segundo en el panel derecho.

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `python -m pytest tests/test_admin_ticket.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ticket_actions.py app/tickets.py app/routes/admin.py app/templates/admin/ticket.html app/templates/partials tests/test_admin_ticket.py
git commit -m "feat: detalle de incidencia, respuestas, estados y auditoria"
```

---

### Task 11: Asignación visible y avisos del admin

**Files:**
- Create: `app/routes/api.py`, `tests/test_admin_alerts.py`
- Modify: `app/tickets.py`, `app/routes/admin.py`, `app/templates/admin/inbox.html`, `app/templates/admin/ticket.html`, `app/static/app.js`, `app/main.py`

**Interfaces:**
- Produces: `admin_unread(conn, admin_id) -> dict[str, int]` con `sin_asignar` y `mis_no_leidas`; `mark_read_admin(conn, ticket_id, admin_id, *, now=None)`.
- Rutas: `POST /admin/incidencias/{id}/asignar` (`assignee` = `me`, `none` o id), `GET /api/admin/avisos`.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_admin_alerts.py
from app.db import connect
from app.timeutil import utcnow, to_iso
from tests.conftest import csrf_from

def test_asignar_liberar_y_reasignar(admin_client, admin, make_ticket, settings):
    tid = make_ticket()
    html = admin_client.get(f"/admin/incidencias/{tid}").text
    admin_client.post(f"/admin/incidencias/{tid}/asignar", data={"assignee": "me", "csrf_token": csrf_from(html)})
    conn = connect(settings.db_path)
    assert conn.execute("select assigned_admin_id from tickets where id=?", (tid,)).fetchone()[0] == admin
    conn.close()
    admin_client.post(f"/admin/incidencias/{tid}/asignar", data={"assignee": "none", "csrf_token": csrf_from(html)})
    conn = connect(settings.db_path)
    assert conn.execute("select assigned_admin_id from tickets where id=?", (tid,)).fetchone()[0] is None
    conn.close()

def test_avisos_sin_asignar_y_mis_no_leidas(admin_client, admin, make_ticket, settings):
    libre = make_ticket(state="nueva")
    mia = make_ticket(state="en_curso", assigned_admin_id=admin)
    conn = connect(settings.db_path)
    conn.execute("delete from messages where ticket_id=?", (mia,))
    conn.execute("insert into messages(ticket_id,author_type,body,is_internal,created_at)"
                 " values(?,'requester','Nueva respuesta',0,?)", (mia, to_iso(utcnow())))
    conn.commit(); conn.close()
    body = admin_client.get("/api/admin/avisos").json()
    assert body == {"sin_asignar": 1, "mis_no_leidas": 1}
    admin_client.get(f"/admin/incidencias/{mia}")
    assert admin_client.get("/api/admin/avisos").json()["mis_no_leidas"] == 0

def test_api_avisos_sin_sesion(client):
    assert client.get("/api/admin/avisos").status_code == 401
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_admin_alerts.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar**

`admin_unread`: `sin_asignar` cuenta incidencias abiertas sin asignar; `mis_no_leidas` cuenta mensajes públicos de tipo `requester` posteriores a `ticket_reads.last_read_at` (o todos si no hay fila) en incidencias asignadas a ese admin.

`GET /admin/incidencias/{id}`: al abrir, `mark_read_admin`. `POST .../asignar`: interpreta `me` → admin actual, `none` → `NULL`, otro → id validado; llama a `assign`; redirige al detalle.

`/api/admin/avisos`: `Depends(require_admin)`, devuelve el dict.

`app/static/app.js`: si `document.body.dataset.poll == "/api/admin/avisos"`, actualiza `[data-badge="sin-asignar"]` y `[data-badge="mis-no-leidas"]` y el título con la suma.

`inbox.html`/`ticket.html`: muestran el asignado (“Sin asignar” o nombre), botones “Asignármela”, “Liberar” y un selector con todos los admins activos.

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `python -m pytest tests/test_admin_alerts.py tests/test_admin_ticket.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/routes app/tickets.py app/templates/admin app/static/app.js tests/test_admin_alerts.py
git commit -m "feat: asignacion de incidencias y avisos de admin"
```

---

### Task 12: Usuarios que han abierto incidencias

**Files:**
- Create: `app/templates/admin/users.html`, `app/templates/admin/user.html`, `tests/test_admin_users.py`
- Modify: `app/requesters.py`, `app/routes/admin.py`, `app/templates/base.html`

**Interfaces:**
- Produces: `list_requesters(conn, *, q="", only_open=False, active_since=None) -> list[Row]`, `requester_history(conn, requester_id) -> list[Row]`, `update_requester(conn, requester_id, *, name, department_id, device_name, apply_history=False, actor_id=None, now=None)`.
- Rutas: `GET /admin/usuarios`, `GET /admin/usuarios/{id}`, `POST /admin/usuarios/{id}`.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_admin_users.py
from app.db import connect
from tests.conftest import csrf_from

def test_listado_y_busqueda(admin_client, make_ticket):
    make_ticket(requester_name="María López")
    make_ticket(requester_name="Carlos Ruiz")
    r = admin_client.get("/admin/usuarios?q=María")
    assert "María López" in r.text and "Carlos Ruiz" not in r.text
    assert "Ver historial" in r.text

def test_correccion_sin_reescribir_historial(admin_client, make_ticket, settings):
    tid = make_ticket(requester_name="Maria")
    conn = connect(settings.db_path)
    rid = conn.execute("select requester_id from tickets where id=?", (tid,)).fetchone()[0]
    d2 = conn.execute("select id from departments where name='Comercial'").fetchone()[0]
    conn.close()
    html = admin_client.get(f"/admin/usuarios/{rid}").text
    admin_client.post(f"/admin/usuarios/{rid}", data={
        "name": "María López", "department_id": str(d2), "device_name": "PC-01",
        "apply_history": "0", "csrf_token": csrf_from(html)})
    conn = connect(settings.db_path)
    assert conn.execute("select requester_name from tickets where id=?", (tid,)).fetchone()[0] == "Maria"
    assert conn.execute("select name from requesters where id=?", (rid,)).fetchone()[0] == "María López"
    conn.close()
    html = admin_client.get(f"/admin/usuarios/{rid}").text
    admin_client.post(f"/admin/usuarios/{rid}", data={
        "name": "María López", "department_id": str(d2), "device_name": "PC-01",
        "apply_history": "1", "csrf_token": csrf_from(html)})
    conn = connect(settings.db_path)
    t = conn.execute("select requester_name, department_id from tickets where id=?", (tid,)).fetchone()
    assert (t["requester_name"], t["department_id"]) == ("María López", d2)
    conn.close()

def test_no_admin_no_entra(admin_client):
    assert admin_client.get("/admin/usuarios").status_code == 200
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_admin_users.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar**

`list_requesters`: join con `departments`, conteos de incidencias y abiertas, última actividad; `q` filtra por nombre, equipo o IP; `only_open` exige alguna incidencia no resuelta; `active_since` filtra `last_seen_at >=`.

`requester_history`: todas las incidencias del requester, incluidas resueltas, ordenadas por fecha.

`update_requester`: valida nombre (2–80) y departamento activo; actualiza el perfil; si `apply_history`, actualiza `tickets.requester_name` y `tickets.department_id` de sus incidencias e inserta en `ticket_events` un evento `requester_name`/`department` por cada una, con `admin_id=actor_id`.

`GET /admin/usuarios`: listado con filtros y enlaces de historial. `GET /admin/usuarios/{id}`: perfil + historial + formulario de corrección. `POST`: aplica y redirige con `?ok=guardado`.

`base.html`: activar el enlace “Usuarios”.

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `python -m pytest tests/test_admin_users.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/requesters.py app/routes/admin.py app/templates/admin/users.html app/templates/admin/user.html app/templates/base.html tests/test_admin_users.py
git commit -m "feat: listado de usuarios e historial con correccion auditada"
```

---

### Task 13: Catálogos: crear, renombrar, archivar y ordenar

**Files:**
- Create: `app/templates/admin/catalogs.html`, `tests/test_admin_catalogs.py`
- Modify: `app/catalogs.py`, `app/routes/admin.py`, `app/templates/base.html`

**Interfaces:**
- Produces: `list_catalogs(conn, kind, active_only=False)`, `create_catalog(conn, kind, name, *, now=None) -> int`, `rename_catalog(conn, kind, catalog_id, name)`, `set_catalog_active(conn, kind, catalog_id, active)`, `move_catalog(conn, kind, catalog_id, direction)`, `CatalogError(ValueError)`.
- Rutas: `GET /admin/catalogos`, `POST /admin/catalogos/{kind}/crear`, `.../{id}/renombrar`, `.../{id}/archivar`, `.../{id}/reactivar`, `.../{id}/mover` (`direction=up|down`).

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_admin_catalogs.py
from app.catalogs import CatalogError, create_catalog, set_catalog_active
from app.db import connect
from tests.conftest import csrf_from

def test_duplicado_ignorando_acentos_y_mayusculas(settings):
    conn = connect(settings.db_path)
    try:
        create_catalog(conn, "departments", "administracion")
    except CatalogError:
        pass
    else:
        raise AssertionError("debe rechazar duplicado sin acentos")
    conn.close()

def test_no_se_puede_archivar_el_ultimo_activo(admin, settings):
    conn = connect(settings.db_path)
    for row in conn.execute("select id from departments order by id").fetchall()[:-1]:
        set_catalog_active(conn, "departments", row["id"], False)
    ultimo = conn.execute("select id from departments where active=1").fetchone()[0]
    try:
        set_catalog_active(conn, "departments", ultimo, False)
    except CatalogError:
        pass
    else:
        raise AssertionError("no debe archivar el último")
    conn.close()

def test_archivado_no_aparece_en_formulario_pero_si_en_historial(admin_client, make_ticket, settings):
    conn = connect(settings.db_path)
    d = conn.execute("select id from departments where name='Comercial'").fetchone()[0]
    conn.close()
    tid = make_ticket(department_id=d)
    html = admin_client.get("/admin/catalogos").text
    admin_client.post(f"/admin/catalogos/departments/{d}/archivar", data={"csrf_token": csrf_from(html)})
    assert "Comercial" not in admin_client.get("/").text
    assert "Comercial" in admin_client.get(f"/admin/incidencias/{tid}").text

def test_crear_renombrar_y_mover(admin_client, settings):
    html = admin_client.get("/admin/catalogos").text
    admin_client.post("/admin/catalogos/categories/crear", data={"name": "Móviles", "csrf_token": csrf_from(html)})
    conn = connect(settings.db_path)
    cid = conn.execute("select id from categories where name='Móviles'").fetchone()[0]
    conn.close()
    html = admin_client.get("/admin/catalogos").text
    admin_client.post(f"/admin/catalogos/categories/{cid}/renombrar", data={"name": "Telefonía", "csrf_token": csrf_from(html)})
    html = admin_client.get("/admin/catalogos").text
    admin_client.post(f"/admin/catalogos/categories/{cid}/mover", data={"direction": "up", "csrf_token": csrf_from(html)})
    conn = connect(settings.db_path)
    assert conn.execute("select name from categories where id=?", (cid,)).fetchone()[0] == "Telefonía"
    conn.close()
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_admin_catalogs.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Validar `kind` contra `{"departments","categories"}` en todas las funciones (nunca interpolar el nombre recibido sin comprobarlo). Normalización para duplicados: `unicodedata.normalize("NFKD", name).encode("ascii","ignore").decode().casefold().strip()`. Nombre visible 2–60, sin vacío.

`create_catalog`: `sort_order = max(sort_order)+10`; `rename_catalog`: solo cambia el nombre; `set_catalog_active`: al archivar, si quedaría cero activos lanza `CatalogError`; `move_catalog`: intercambia `sort_order` con el vecino en la dirección pedida, sin salirse de la lista.

`GET /admin/catalogos` muestra dos paneles (departamentos y tipos) con activos y archivados, contadores de uso, formularios de alta, renombrar, archivar/reactivar y flechas. `POST` redirige con `?ok=` o `?error=`.

`base.html`: activar “Departamentos y tipos”.

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `python -m pytest tests/test_admin_catalogs.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/catalogs.py app/routes/admin.py app/templates/admin/catalogs.html app/templates/base.html tests/test_admin_catalogs.py
git commit -m "feat: gestion de departamentos y tipos con archivado"
```

---

### Task 14: Cuentas de admin (solo superadmin) y contraseña propia

**Files:**
- Create: `app/templates/admin/accounts.html`, `app/templates/admin/password.html`, `tests/test_admin_accounts.py`
- Modify: `app/routes/admin.py`, `app/admins.py`, `app/templates/base.html`

**Interfaces:**
- Rutas: `GET /admin/cuentas`, `POST /admin/cuentas/crear`, `POST /admin/cuentas/{id}/clave`, `POST /admin/cuentas/{id}/estado`, `POST /admin/cuentas/{id}/rol`; `GET/POST /admin/mi-clave`.
- `Admins` ya expone las funciones en Task 4; esta tarea añade `iterations` a `reset_password`/`change_own_password` y usa las del `Settings`.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_admin_accounts.py
from app.admins import create_admin
from app.db import connect
from tests.conftest import csrf_from
from fastapi.testclient import TestClient

def _login(app, username, password):
    c = TestClient(app, follow_redirects=False)
    c.get("/admin/login")
    tok = c.cookies["login_csrf"]
    r = c.post("/admin/login", data={"username": username, "password": password, "csrf_token": tok})
    assert r.status_code == 303
    return c

def test_admin_normal_no_entra_en_cuentas(admin_client, app, settings):
    conn = connect(settings.db_path)
    create_admin(conn, username="normal", display_name="Normal", password="clave-segura-2", role="admin", iterations=1000)
    conn.commit(); conn.close()
    c = _login(app, "normal", "clave-segura-2")
    assert c.get("/admin/cuentas").status_code == 403

def test_crear_cuenta_y_resetear_invalida_sesiones(admin_client, app, settings):
    html = admin_client.get("/admin/cuentas").text
    r = admin_client.post("/admin/cuentas/crear", data={
        "username": "soporte2", "display_name": "Soporte Dos", "role": "admin",
        "password": "clave-segura-2", "csrf_token": csrf_from(html)})
    assert r.status_code == 303
    c = _login(app, "soporte2", "clave-segura-2")
    assert c.get("/admin").status_code == 200
    conn = connect(settings.db_path)
    uid = conn.execute("select id from admins where username='soporte2'").fetchone()[0]
    conn.close()
    html = admin_client.get("/admin/cuentas").text
    admin_client.post(f"/admin/cuentas/{uid}/clave", data={
        "password": "clave-nueva-3", "csrf_token": csrf_from(html)})
    assert c.get("/admin").status_code == 303

def test_no_puede_desactivar_al_ultimo_superadmin(admin_client, admin):
    html = admin_client.get("/admin/cuentas").text
    r = admin_client.post(f"/admin/cuentas/{admin}/estado", data={"active": "0", "csrf_token": csrf_from(html)})
    assert r.status_code == 400

def test_cambiar_clave_propia_mantiene_sesion_actual(admin_client, admin, app, settings):
    otra = _login(app, "javier", "clave-segura-1")
    html = admin_client.get("/admin/mi-clave").text
    r = admin_client.post("/admin/mi-clave", data={
        "current": "clave-segura-1", "new": "clave-segura-9", "csrf_token": csrf_from(html)})
    assert r.status_code == 303
    assert admin_client.get("/admin").status_code == 200
    assert otra.get("/admin").status_code == 303
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_admin_accounts.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar**

`GET /admin/cuentas` y todas las acciones usan `Depends(require_superadmin)`. Crear cuenta valida usuario único, rol en `{admin, superadmin}` y contraseña ≥10 (usa `iterations=settings.pbkdf2_iterations`); `reset_password` borra todas las sesiones del objetivo; `set_active(False)` también; `set_role` también. Un superadmin no puede desactivarse, degradarse ni quitarse a sí mismo; el servicio lanza `AdminRuleError` y la ruta responde 400 con el mensaje. Cada acción llama a `audit`.

`GET/POST /admin/mi-clave` (con `Depends(require_admin)`, no superadmin): pide contraseña actual, valida nueva (≥10 y distinta), actualiza hash con `settings.pbkdf2_iterations` y `keep_session_id=admin.session_id`, borra todas las sesiones del admin menos la actual y audita.

`accounts.html`: tabla de cuentas con rol, estado, último acceso y acciones; formulario de alta. `password.html`: cambio de contraseña propia. `base.html`: “Cuentas” solo si `admin.role == "superadmin"`.

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `python -m pytest tests/test_admin_accounts.py tests/test_auth.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/admins.py app/routes/admin.py app/templates/admin/accounts.html app/templates/admin/password.html app/templates/base.html tests/test_admin_accounts.py
git commit -m "feat: cuentas de administracion y cambio de contrasena"
```

---

### Task 15: Exportación CSV, vista imprimible y copiar datos

**Files:**
- Create: `tests/test_export.py`
- Modify: `app/routes/admin.py`, `app/tickets.py`, `app/templates/admin/ticket.html`, `app/static/app.js`, `app/static/app.css`

**Interfaces:**
- Ruta: `GET /admin/export.csv` con los mismos filtros que la bandeja.
- `export_rows(conn, filters, admin_id) -> list[Row]`.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_export.py
import pytest
from app.db import connect
from app.tickets import create_ticket
from app.pcinfo import ClientInfo

def test_csv_con_bom_y_filtros(admin_client, make_ticket):
    make_ticket(subject="Correo roto")
    make_ticket(subject="Impresora")
    r = admin_client.get("/admin/export.csv?q=Correo")
    assert r.status_code == 200
    assert r.content.startswith(b"\xef\xbb\xbf")
    texto = r.content.decode("utf-8-sig")
    assert "Correo roto" in texto and "Impresora" not in texto
    assert "INC-2026-" in texto

def test_csv_neutraliza_formulas(admin_client, make_ticket):
    make_ticket(subject="=HYPERLINK(\"http://mal\")")
    texto = admin_client.get("/admin/export.csv").content.decode("utf-8-sig")
    assert "'=HYPERLINK" in texto

def test_csv_exige_sesion(client):
    assert client.get("/admin/export.csv").status_code == 303

RUTAS_GET = ["/admin", "/admin/usuarios", "/admin/catalogos", "/admin/cuentas",
             "/admin/mi-clave", "/admin/export.csv", "/admin/incidencias/1"]
RUTAS_POST = ["/admin/incidencias/1/responder", "/admin/incidencias/1/estado",
              "/admin/incidencias/1/campos", "/admin/incidencias/1/asignar",
              "/admin/usuarios/1", "/admin/catalogos/departments/crear",
              "/admin/cuentas/crear", "/admin/mi-clave"]

@pytest.mark.parametrize("ruta", RUTAS_GET)
def test_rutas_admin_get_sin_sesion(client, ruta):
    assert client.get(ruta).status_code in (303, 401)

@pytest.mark.parametrize("ruta", RUTAS_POST)
def test_rutas_admin_post_sin_sesion(client, ruta):
    assert client.post(ruta, data={}).status_code in (303, 401)
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_export.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar**

`export_rows` reutiliza los filtros de `list_admin` sin paginación. La ruta devuelve `Response` con `media_type="text/csv; charset=utf-8"`, BOM `\ufeff` y `Content-Disposition: attachment; filename="incidencias-YYYYMMDD.csv"`. Columnas: código, fecha, solicitante, departamento, tipo, prioridad, estado, asignado, asunto, últimos datos del equipo (IP, MAC, hostname), reaperturas. Si una celda empieza por `=`, `+`, `-` o `@`, se prefija con `'`.

`admin/ticket.html`: botón “Copiar datos del equipo” con `data-copy` que copia un bloque de texto ya renderizado (usuario, equipo, IP, MAC, navegador); botón “Imprimir”. `app.css`: `@media print` oculta topbar, filtros, botones y formularios, y deja el detalle limpio. `app.js`: manejador de `[data-copy]` con `navigator.clipboard.writeText` y fallback a `document.execCommand("copy")`.

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `python -m pytest tests/test_export.py -q`
Expected: PASS (3 tests funcionales y las rutas de admin parametrizadas).

- [ ] **Step 5: Commit**

```bash
git add app/routes/admin.py app/tickets.py app/templates/admin/ticket.html app/static tests/test_export.py
git commit -m "feat: exportacion csv segura, impresion y copia de datos"
```

---

### Task 16: Despliegue, copia de seguridad, README y verificación final

**Files:**
- Create: `run.sh`, `run.bat`, `deploy/incidencias.service`, `tests/test_backup.py`
- Modify: `app/manage.py`, `README.md`, `.env.example`, `app/main.py` (crear `upload_dir` al arrancar)

**Interfaces:**
- Produces: `backup(settings, out_dir, *, now=None) -> Path` en `app/manage.py`.
- Scripts de arranque y unidad systemd.

- [ ] **Step 1: Escribir el test de copia de seguridad**

```python
# tests/test_backup.py
import sqlite3
from app.db import connect, init_db
from app.manage import backup

def test_backup_copia_base_y_adjuntos(settings, tmp_path):
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    conn.execute("insert into ticket_counters(year,value) values(2026,7)")
    conn.commit(); conn.close()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    dest = backup(settings, tmp_path / "copias")
    assert (dest / "incidencias.db").exists()
    assert (dest / "uploads" / "a.png").exists()
    c = sqlite3.connect(dest / "incidencias.db")
    assert c.execute("select value from ticket_counters where year=2026").fetchone()[0] == 7
    c.close()
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `python -m pytest tests/test_backup.py -q`
Expected: FAIL, `backup` no existe.

- [ ] **Step 3: Implementar despliegue y documentación**

`backup`: crea `out_dir/backup-YYYYMMDD-HHMMSS/`, copia la base con `sqlite3.Connection.backup` a `incidencias.db` y `shutil.copytree(upload_dir, dest/"uploads", dirs_exist_ok=True)`; devuelve el directorio.

`manage.py`: subcomando `backup --out DIR` que usa `load_settings()`.

`run.sh` (con `chmod +x`):

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
set -a
[ -f .env ] && . ./.env
set +a
ARGS=(--host "${APP_HOST:-0.0.0.0}" --port "${APP_PORT:-8000}" --workers 1)
if [[ -n "${TLS_CERT:-}" && -n "${TLS_KEY:-}" ]]; then
  ARGS+=(--ssl-certfile "$TLS_CERT" --ssl-keyfile "$TLS_KEY")
fi
exec .venv/bin/python -m uvicorn app.main:app "${ARGS[@]}"
```

`run.bat`:

```bat
@echo off
cd /d %~dp0
if "%APP_HOST%"=="" set APP_HOST=0.0.0.0
if "%APP_PORT%"=="" set APP_PORT=8000
.venv\Scripts\python.exe -m uvicorn app.main:app --host %APP_HOST% --port %APP_PORT% --workers 1
```

`deploy/incidencias.service`: unidad systemd con `WorkingDirectory=/opt/incidencias`, `EnvironmentFile=/opt/incidencias/.env`, `ExecStart=/opt/incidencias/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`, `Restart=always`, `User=incidencias`.

`README.md`: requisitos, instalación en Linux y Windows, creación del superadmin (`python -m app.manage create-superadmin`), arranque manual, systemd, NSSM en Windows Server, abrir el puerto 8000 en el firewall, TLS opcional con certificado o proxy inverso, copia de seguridad y restauración, actualización, límites conocidos (MAC no disponible en otra subred, sin notificaciones del navegador, sin recuperación de contraseña por correo) y resolución de problemas.

`create_app`: crear `settings.upload_dir` con `mkdir(parents=True, exist_ok=True)` antes de montar la app y registrar un `@app.exception_handler(Exception)` que registre la traza en el log del servidor y devuelva una página 500 genérica (“Ha ocurrido un error”) sin detalles internos.

- [ ] **Step 4: Ejecutar toda la batería**

Run: `python -m pytest -q`
Expected: PASS, 0 fallos.

- [ ] **Step 5: Verificación manual de arranque**

```bash
python -m app.manage create-superadmin --username admin
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

En otra terminal: `curl http://127.0.0.1:8765/salud` → `{"status":"ok"}`. Abrir `http://127.0.0.1:8765/`, crear una incidencia, entrar en `/admin`, responder, resolver, comprobar la reapertura desde el usuario y descargar el CSV. Parar el servidor.

- [ ] **Step 6: Commit**

```bash
git add run.sh run.bat deploy README.md .env.example app/manage.py app/main.py tests/test_backup.py
git commit -m "chore: despliegue, copias de seguridad y documentacion"
```

---

## Verificación final del proyecto

- [ ] `python -m pytest -q` en verde.
- [ ] `python -m app.manage create-superadmin --username admin` crea la cuenta y `/admin/login` funciona.
- [ ] Un usuario sin sesión no puede abrir ninguna ruta `/admin` ni `/api/admin`.
- [ ] Una incidencia creada desde otro PC muestra IP y, si está en la misma red, MAC; si está enrutada, “No disponible”.
- [ ] Responder a una resuelta la reabre y avisa.
- [ ] Archivar un departamento en uso no rompe el historial.
- [ ] El CSV se abre en Excel con acentos correctos.
- [ ] Reiniciar el servicio conserva datos y adjuntos.

