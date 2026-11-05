from __future__ import annotations

import unicodedata

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


def _check_kind(kind: str) -> None:
    if kind not in CATALOG_KINDS:
        raise CatalogError(f"Catálogo desconocido: {kind}")


def _normalize(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name or "")
    return "".join(c for c in folded if not unicodedata.combining(c)).casefold().strip()


def list_catalogs(
    conn: sqlite3.Connection, kind: str, active_only: bool = True
) -> list[sqlite3.Row]:
    _check_kind(kind)
    sql = f"select * from {kind}"
    if active_only:
        sql += " where active = 1"
    sql += " order by sort_order, lower(name)"
    return list(conn.execute(sql))


def create_catalog(conn, kind, name, *, now=None) -> int:
    _check_kind(kind)
    name = (name or "").strip()
    if not name:
        raise CatalogError("El nombre no puede estar vacío")
    normalized = _normalize(name)
    for row in conn.execute(f"select name from {kind}"):
        if _normalize(row["name"]) == normalized:
            raise CatalogError("Ya existe un elemento con ese nombre")
    sort_order = conn.execute(
        f"select coalesce(max(sort_order), 0) + 10 from {kind}"
    ).fetchone()[0]
    conn.execute(
        f"insert into {kind}(name,active,sort_order,created_at) values(?,1,?,?)",
        (name, sort_order, to_iso(now or utcnow())),
    )
    conn.commit()
    return conn.execute("select last_insert_rowid()").fetchone()[0]


def rename_catalog(conn, kind, catalog_id, name) -> None:
    _check_kind(kind)
    name = (name or "").strip()
    if not name:
        raise CatalogError("El nombre no puede estar vacío")
    normalized = _normalize(name)
    for row in conn.execute(
        f"select id, name from {kind} where id != ?", (catalog_id,)
    ):
        if _normalize(row["name"]) == normalized:
            raise CatalogError("Ya existe un elemento con ese nombre")
    conn.execute(f"update {kind} set name = ? where id = ?", (name, catalog_id))
    conn.commit()


def set_catalog_active(conn, kind, catalog_id, active) -> None:
    _check_kind(kind)
    if not active:
        remaining = conn.execute(
            f"select count(*) from {kind} where active = 1 and id != ?",
            (catalog_id,),
        ).fetchone()[0]
        if remaining == 0:
            raise CatalogError("No se puede archivar el último elemento activo")
    conn.execute(
        f"update {kind} set active = ? where id = ?",
        (1 if active else 0, catalog_id),
    )
    conn.commit()


def move_catalog(conn, kind, catalog_id, direction) -> None:
    _check_kind(kind)
    if direction not in {"up", "down"}:
        raise CatalogError("Dirección inválida")
    row = conn.execute(
        f"select id, sort_order from {kind} where id = ?", (catalog_id,)
    ).fetchone()
    if row is None:
        raise CatalogError("No existe el elemento")
    if direction == "up":
        neighbour = conn.execute(
            f"select id, sort_order from {kind} where sort_order < ? order by sort_order desc limit 1",
            (row["sort_order"],),
        ).fetchone()
    else:
        neighbour = conn.execute(
            f"select id, sort_order from {kind} where sort_order > ? order by sort_order asc limit 1",
            (row["sort_order"],),
        ).fetchone()
    if neighbour is None:
        return
    conn.execute(
        f"update {kind} set sort_order = ? where id = ?",
        (neighbour["sort_order"], row["id"]),
    )
    conn.execute(
        f"update {kind} set sort_order = ? where id = ?",
        (row["sort_order"], neighbour["id"]),
    )
    conn.commit()
