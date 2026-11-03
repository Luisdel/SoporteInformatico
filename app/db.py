from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

from fastapi import Request

from app.catalogs import seed_defaults

SCHEMA_V1 = """
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
"""

MIGRATIONS: tuple[str, ...] = (SCHEMA_V1,)


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for script in MIGRATIONS[version:]:
            conn.executescript(script)
        if version < len(MIGRATIONS):
            conn.execute(f"PRAGMA user_version={len(MIGRATIONS)}")
        seed_defaults(conn)
        conn.commit()
    finally:
        conn.close()


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
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
