from __future__ import annotations

from datetime import timedelta
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import AdminContext, require_admin
from app.config import Settings, load_settings
from app.db import get_db
from app.security import find_admin_session, touch_admin_session, new_token, hash_token, RateLimiter
from app.timeutil import utcnow, to_iso

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/admin/login", response_class=HTMLResponse)
def login_form(request: Request):
    if request.cookies.get("admin_session"):
        return RedirectResponse(url="/admin", status_code=303)
    csrf_token = new_token()
    response = templates.TemplateResponse(
        request, "admin/login.html", {"csrf_token": csrf_token}
    )
    response.set_cookie(
        "login_csrf",
        csrf_token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
        secure=request.app.state.settings.secure_cookies,
    )
    return response


@router.post("/admin/login", status_code=303)
async def login_handler(
    request: Request,
    conn=Depends(get_db),
    settings: Settings = Depends(load_settings),
    csrf_token: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
):
    cookie_token = request.cookies.get("login_csrf", "")
    if not csrf_token or not cookie_token or csrf_token != cookie_token:
        raise HTTPException(status_code=400, detail="Token CSRF inválido")
    username = username.strip()
    password = password.strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="Faltan campos")
    if not (3 <= len(username) <= 40):
        raise HTTPException(status_code=400, detail="Usuario debe tener entre 3 y 40 caracteres")
    if len(password) < 10:
        raise HTTPException(status_code=400, detail="Contraseña debe tener al menos 10 caracteres")
    ip = request.client.host if request.client else "0.0.0.0"
    limiter = request.app.state.login_limiter
    if not limiter.hit(f"{ip}:{username.lower()}", 5, 900):
        raise HTTPException(status_code=429, detail="Demasiados intentos")
    from app.admins import authenticate
    if not authenticate(conn, username, password):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    limiter.reset(f"{ip}:{username.lower()}")
    admin_row = conn.execute("select id from admins where lower(username)=lower(?) and active=1", (username,)).fetchone()
    if admin_row is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    admin_id = admin_row[0]
    token, csrf = new_token(), new_token()
    conn.execute(
        """
        insert into admin_sessions(
            token_hash, csrf_token, admin_id, created_at, last_seen_at,
            expires_at, ip, user_agent
        ) values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hash_token(token),
            csrf,
            admin_id,
            to_iso(utcnow()),
            to_iso(utcnow()),
            to_iso(utcnow() + timedelta(days=settings.session_hours)),
            ip,
            request.headers.get("user-agent"),
        ),
    )
    admin_row = conn.execute("select id from admins where lower(username)=lower(?) and active=1", (username,)).fetchone()
    if admin_row is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    admin_id = admin_row[0]
    conn.execute(
        "update admin_sessions set admin_id = ? where token_hash = ?",
        (admin_id, hash_token(token)),
    )
    conn.commit()
    response = RedirectResponse(url="/admin", status_code=303)
    response.set_cookie(
        "admin_session",
        token,
        httponly=True,
        samesite="lax",
        max_age=settings.session_hours * 3600,
        secure=settings.secure_cookies,
    )
    response.set_cookie(
        "login_csrf",
        csrf,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
        secure=settings.secure_cookies,
    )
    return response


@router.post("/admin/logout", status_code=303)
def logout_handler(request: Request, conn=Depends(get_db)):
    token = request.cookies.get("admin_session")
    if token:
        conn.execute(
            "delete from admin_sessions where token_hash = ?", (hash_token(token),)
        )
        conn.commit()
    response = RedirectResponse(url="/admin", status_code=303)
    response.delete_cookie("admin_session")
    response.delete_cookie("login_csrf")
    return response


@router.get("/admin", response_class=HTMLResponse)
def admin_index(request: Request, admin: AdminContext = Depends(require_admin)):
    return templates.TemplateResponse(
        request, "admin/index.html",
        {
            "admin": admin,
            "csrf_token": admin.csrf_token,
            "content": "Bandeja de incidencias (pendiente de la tarea 9)",
        },
    )
