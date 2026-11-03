from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.db import get_db
from app.security import hash_password, verify_password
from app.timeutil import utcnow, to_iso


class AdminRuleError(Exception):
    """Operación prohibida sobre cuentas (último superadmin, auto-degradación...)."""


def _validate_username(username: str) -> None:
    if not (3 <= len(username) <= 40):
        raise ValueError("usuario debe tener entre 3 y 40 caracteres")
    if not all(c.islower() and (c.isalnum() or c in "._-") for c in username):
        raise ValueError("usuario solo letras minúsculas, dígitos, punto, guion o guion bajo")


def _validate_display_name(display_name: str) -> None:
    if not display_name or not display_name.strip():
        raise ValueError("el nombre visible no puede estar vacío")


def create_admin(
    conn,
    username: str,
    display_name: str,
    password: str,
    role: str = "admin",
    active: int = 1,
    iterations: int = 600_000,
    created_at: Optional[datetime] = None,
    password_changed_at: Optional[datetime] = None,
) -> int:
    password = password.strip()
    if len(password) < 10:
        raise ValueError("la contraseña debe tener al menos 10 caracteres")
    _validate_username(username)
    _validate_display_name(display_name)
    now = created_at or utcnow()
    conn.execute(
        """
        insert into admins(
            username, display_name, password_hash, role, active,
            created_at, password_changed_at
        ) values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            username,
            display_name.strip(),
            hash_password(password, iterations=iterations),
            role,
            int(active),
            to_iso(now),
            to_iso(password_changed_at or now),
        ),
    )
    conn.commit()
    return conn.execute(
        "select id from admins where username = ?", (username,)
    ).fetchone()[0]


def authenticate(conn, username: str, password: str) -> bool:
    row = conn.execute(
        """
        select password_hash from admins
        where lower(username) = lower(?) and active = 1
        """,
        (username,),
    ).fetchone()
    if row is None:
        return False
    if not verify_password(password, row[0]):
        return False
    conn.execute(
        "update admins set last_login_at = ? where lower(username) = lower(?)",
        (to_iso(utcnow()), username),
    )
    conn.commit()
    return True


def list_admins(conn) -> list:
    return conn.execute(
        "select id, username, display_name, role, active "
        "from admins order by role, username"
    ).fetchall()


def _count_active_superadmins(conn) -> int:
    return conn.execute(
        "select count(*) from admins where role = 'superadmin' and active = 1"
    ).fetchone()[0]


def set_active(conn, admin_id: int, active: int, actor_id: int) -> None:
    row = conn.execute(
        "select role, active from admins where id = ?", (admin_id,)
    ).fetchone()
    if row is None:
        raise AdminRuleError("admin no existe")
    if actor_id == admin_id:
        raise AdminRuleError("no puedes desactivarte a ti mismo")
    if active == 0 and row[0] == "superadmin" and _count_active_superadmins(conn) <= 1:
        raise AdminRuleError("no puede quedar cero superadmins activos")
    conn.execute(
        "update admins set active = ? where id = ?", (int(active), admin_id)
    )
    conn.commit()


def set_role(conn, admin_id: int, role: str, actor_id: int) -> None:
    row = conn.execute("select role from admins where id = ?", (admin_id,)).fetchone()
    if row is None:
        raise AdminRuleError("admin no existe")
    if actor_id == admin_id:
        raise AdminRuleError("no puedes cambiar tu propio rol")
    if role == "superadmin" and _count_active_superadmins(conn) <= 1:
        raise AdminRuleError("no puede quedar cero superadmins activos")
    conn.execute("update admins set role = ? where id = ?", (role, admin_id))
    conn.commit()


def reset_password(conn, admin_id: int, password: str, iterations: int = 600_000) -> None:
    if len(password.strip()) < 10:
        raise ValueError("la contraseña debe tener al menos 10 caracteres")
    conn.execute(
        "update admins set password_hash = ? where id = ?",
        (hash_password(password.strip(), iterations=iterations), admin_id),
    )
    conn.commit()


def change_own_password(conn, admin_id: int, old_password: str, new_password: str, iterations: int = 600_000) -> None:
    row = conn.execute(
        "select password_hash from admins where id = ?", (admin_id,)
    ).fetchone()
    if row is None or not verify_password(old_password, row[0]):
        raise ValueError("contraseña actual incorrecta")
    if len(new_password.strip()) < 10:
        raise ValueError("la nueva contraseña debe tener al menos 10 caracteres")
    conn.execute(
        "update admins set password_hash = ? where id = ?",
        (hash_password(new_password.strip(), iterations=iterations), admin_id),
    )
    conn.commit()


def audit(conn, admin_id: int, action: str) -> None:
    conn.execute(
        "insert into admin_audit(admin_id, action, performed_at) values (?, ?, ?)",
        (admin_id, action, to_iso(utcnow())),
    )
    conn.commit()