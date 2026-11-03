from __future__ import annotations

import hmac
from typing import Optional

from fastapi import Depends, HTTPException, Request

from app.db import get_db
from app.security import find_admin_session, touch_admin_session
from app.timeutil import to_iso


class AdminContext:
    def __init__(self, id: int, username: str, display_name: str, role: str,
                 csrf_token: str, session_id: str) -> None:
        self.id = id
        self.username = username
        self.display_name = display_name
        self.role = role
        self.csrf_token = csrf_token
        self.session_id = session_id


def require_admin(request: Request, conn=Depends(get_db)) -> AdminContext:
    token = request.cookies.get("admin_session")
    if token is None:
        if request.url.path.startswith("/api/"):
            raise HTTPException(status_code=401, detail="No autenticado")
        raise HTTPException(
            status_code=303,
            headers={"Location": f"/admin/login?next={request.url.path}"},
        )
    row = find_admin_session(
        conn, token, idle_hours=request.app.state.settings.session_hours
    )
    if row is None:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    touch_admin_session(conn, row["session_id"])
    return AdminContext(
        id=row["admin_id"],
        username=row["username"],
        display_name=row["display_name"],
        role=row["role"],
        csrf_token=row["csrf_token"],
        session_id=row["session_id"],
    )


def require_superadmin(admin: AdminContext = Depends(require_admin)) -> AdminContext:
    if admin.role != "superadmin":
        raise HTTPException(status_code=403, detail="Solo para superadmins")
    return admin


def verify_csrf(admin: AdminContext, token: str) -> None:
    if not hmac.compare_digest(admin.csrf_token, token or ""):
        raise HTTPException(status_code=400, detail="Token CSRF inválido")