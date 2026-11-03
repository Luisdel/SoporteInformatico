from __future__ import annotations

import sqlite3

from app.timeutil import to_iso, utcnow

DEFAULT_DEPARTMENTS = (
    "Administración",
    "Comercial",
    "Producción",
    "Almacén",
    "Dirección",
)
DEFAULT_CATEGORIES = (
    "Correo / Outlook",
    "Hardware",
    "Software",
    "Red / Internet",
    "Impresora",
    "Accesos y contraseñas",
    "Otro",
)

CATALOG_KINDS = frozenset({"departments", "categories"})


class CatalogError(ValueError):
    pass


def _seed_table(conn: sqlite3.Connection, table: str, names: tuple[str, ...]) -> None:
    if conn.execute(f"select 1 from {table} limit 1").fetchone():
        return
    now = to_iso(utcnow())
    conn.executemany(
        f"insert into {table}(name,active,sort_order,created_at) values(?,1,?,?)",
        [(name, (index + 1) * 10, now) for index, name in enumerate(names)],
    )


def seed_defaults(conn: sqlite3.Connection) -> None:
    _seed_table(conn, "departments", DEFAULT_DEPARTMENTS)
    _seed_table(conn, "categories", DEFAULT_CATEGORIES)


def list_catalogs(
    conn: sqlite3.Connection, kind: str, active_only: bool = True
) -> list[sqlite3.Row]:
    if kind not in CATALOG_KINDS:
        raise CatalogError(f"Catálogo desconocido: {kind}")
    sql = f"select * from {kind}"
    if active_only:
        sql += " where active = 1"
    sql += " order by sort_order, lower(name)"
    return list(conn.execute(sql))
