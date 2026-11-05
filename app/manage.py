from __future__ import annotations

import argparse
import getpass
import sys

from app.admins import create_admin, list_admins, reset_password
from app.config import load_settings
from app.db import connect, init_db


def _conn():
    settings = load_settings()
    init_db(settings.db_path)
    return connect(settings.db_path)


def cmd_create_admin(args) -> None:
    password = args.password or getpass.getpass("Contraseña: ")
    confirmation = args.password or getpass.getpass("Repite la contraseña: ")
    if password != confirmation:
        print("Las contraseñas no coinciden", file=sys.stderr)
        raise SystemExit(1)
    conn = _conn()
    try:
        admin_id = create_admin(
            conn,
            username=args.username,
            display_name=args.display_name or args.username,
            password=password,
            role=args.role,
        )
    except Exception as exc:  # noqa: BLE001 - mensaje claro en CLI
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    finally:
        conn.close()
    print(f"Administrador creado: id={admin_id}, usuario={args.username}, rol={args.role}")


def cmd_list_admins(_args) -> None:
    conn = _conn()
    try:
        for row in list_admins(conn):
            state = "activo" if row["active"] else "inactivo"
            print(f"{row['id']:>3}  {row['username']:<20} {row['role']:<10} {state}  {row['display_name']}")
    finally:
        conn.close()


def cmd_reset_password(args) -> None:
    password = args.password or getpass.getpass("Nueva contraseña: ")
    conn = _conn()
    try:
        row = conn.execute(
            "select id from admins where lower(username)=lower(?)", (args.username,)
        ).fetchone()
        if row is None:
            print("No existe ese usuario", file=sys.stderr)
            raise SystemExit(1)
        reset_password(conn, row["id"], password)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    finally:
        conn.close()
    print(f"Contraseña actualizada para {args.username}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gestión de la app de incidencias")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-admin", help="Crea un administrador")
    create.add_argument("username")
    create.add_argument("--display-name", default="")
    create.add_argument("--role", choices=["admin", "superadmin"], default="superadmin")
    create.add_argument("--password", default="")
    create.set_defaults(func=cmd_create_admin)

    listing = sub.add_parser("list-admins", help="Lista administradores")
    listing.set_defaults(func=cmd_list_admins)

    reset = sub.add_parser("reset-password", help="Cambia la contraseña de un admin")
    reset.add_argument("username")
    reset.add_argument("--password", default="")
    reset.set_defaults(func=cmd_reset_password)

    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
