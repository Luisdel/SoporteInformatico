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
