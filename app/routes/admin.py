from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.auth import AdminContext, require_admin, require_superadmin, verify_csrf
from app.catalogs import (
    CATALOG_KINDS,
    CatalogError,
    create_catalog,
    list_catalogs,
    move_catalog,
    rename_catalog,
    set_catalog_active,
)
from app.db import get_db
from app.requesters import list_requesters, requester_history, update_requester
from app.security import hash_password
from app.ticket_actions import (
    admin_unread,
    assign,
    change_category,
    change_department,
    change_priority,
    change_state,
    list_attachments,
    list_messages,
    mark_read_admin,
    post_admin_message,
)
from app.tickets import PRIORITIES, STATES, get_ticket
from app.timeutil import to_iso, utcnow
from app.uploads import UploadError, save_many

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

STATE_LABELS = {
    "nueva": "Nueva",
    "en_curso": "En curso",
    "en_espera": "En espera",
    "resuelta": "Resuelta",
}
PRIORITY_LABELS = {
    "baja": "Baja",
    "normal": "Normal",
    "alta": "Alta",
    "urgente": "Urgente",
}


def _admin_ctx(admin: AdminContext) -> dict:
    return {"admin": admin, "csrf_token": admin.csrf_token}


def _save_files(files, request: Request):
    settings = request.app.state.settings
    try:
        return save_many(
            files,
            settings.upload_dir,
            max_bytes=settings.max_upload_mb * 1024 * 1024,
        )
    except UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/admin", response_class=HTMLResponse)
def inbox(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
    state: str = "",
    q: str = "",
    mine: str = "",
):
    clauses = []
    params: list = []
    if state in STATES:
        clauses.append("t.state = ?")
        params.append(state)
    if mine == "1":
        clauses.append("t.assigned_admin_id = ?")
        params.append(admin.id)
    if q:
        clauses.append("(lower(t.code) like lower(?) or lower(t.subject) like lower(?))")
        params.extend([f"%{q}%", f"%{q}%"])
    sql = """
        select t.*, d.name as department_name, c.name as category_name,
               a.display_name as assignee_name
          from tickets t
          left join departments d on d.id = t.department_id
          left join categories c on c.id = t.category_id
          left join admins a on a.id = t.assigned_admin_id
    """
    if clauses:
        sql += " where " + " and ".join(clauses)
    sql += " order by t.updated_at desc, t.id desc"
    tickets = conn.execute(sql, params).fetchall()
    unread = admin_unread(conn, admin.id)
    return templates.TemplateResponse(
        request,
        "admin/inbox.html",
        {
            "request": request,
            "tickets": tickets,
            "unread": unread,
            "filters": {"state": state, "q": q, "mine": mine},
            "state_labels": STATE_LABELS,
            "priority_labels": PRIORITY_LABELS,
            "states": STATES,
            **_admin_ctx(admin),
        },
    )


def _detail_context(conn, ticket_id, admin: AdminContext) -> dict:
    ticket = get_ticket(conn, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")
    messages = list_messages(conn, ticket_id, include_internal=True)
    departments = list_catalogs(conn, "departments", active_only=False)
    categories = list_catalogs(conn, "categories", active_only=False)
    admins = conn.execute(
        "select id, username, display_name from admins where active=1 order by display_name"
    ).fetchall()
    return {
        "ticket": ticket,
        "messages": messages,
        "attachments": list_attachments(conn, ticket_id),
        "departments": departments,
        "categories": categories,
        "admins": admins,
        "state_labels": STATE_LABELS,
        "priority_labels": PRIORITY_LABELS,
        "states": STATES,
        "priorities": PRIORITIES,
        **_admin_ctx(admin),
    }


@router.get("/admin/incidencias/{ticket_id}", response_class=HTMLResponse)
def admin_detail(
    request: Request,
    ticket_id: int,
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
):
    context = _detail_context(conn, ticket_id, admin)
    mark_read_admin(conn, ticket_id, admin.id, now=utcnow())
    return templates.TemplateResponse(request, "admin/ticket.html", context)


@router.get("/admin/tickets/{ticket_id}", response_class=HTMLResponse)
def admin_detail_legacy(
    request: Request,
    ticket_id: int,
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
):
    context = _detail_context(conn, ticket_id, admin)
    mark_read_admin(conn, ticket_id, admin.id, now=utcnow())
    return templates.TemplateResponse(request, "admin/detail.html", context)


@router.post("/admin/incidencias/{ticket_id}/responder")
def admin_responder(
    request: Request,
    ticket_id: int,
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
    body: str = Form(""),
    is_internal: str = Form("0"),
    csrf_token: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    verify_csrf(admin, csrf_token)
    if get_ticket(conn, ticket_id) is None:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")
    attachments = _save_files(files, request)
    try:
        post_admin_message(
            conn,
            ticket_id,
            admin.id,
            body,
            is_internal=is_internal == "1",
            attachments=attachments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/admin/incidencias/{ticket_id}", status_code=303)


@router.post("/admin/incidencias/{ticket_id}/estado")
def admin_estado(
    request: Request,
    ticket_id: int,
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
    state: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(admin, csrf_token)
    try:
        change_state(conn, ticket_id, admin.id, state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/admin/incidencias/{ticket_id}", status_code=303)


@router.post("/admin/incidencias/{ticket_id}/asignar")
def admin_asignar(
    request: Request,
    ticket_id: int,
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
    assignee: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(admin, csrf_token)
    if assignee == "me":
        assignee_id = admin.id
    elif assignee in {"", "none"}:
        assignee_id = None
    else:
        try:
            assignee_id = int(assignee)
        except ValueError:
            raise HTTPException(status_code=400, detail="Asignación inválida")
    try:
        assign(conn, ticket_id, admin.id, assignee_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/admin/incidencias/{ticket_id}", status_code=303)


@router.post("/admin/incidencias/{ticket_id}/campos")
def admin_campos(
    request: Request,
    ticket_id: int,
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
    priority: str = Form(""),
    department_id: str = Form(""),
    category_id: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(admin, csrf_token)
    try:
        if priority:
            change_priority(conn, ticket_id, admin.id, priority)
        if department_id:
            change_department(conn, ticket_id, admin.id, int(department_id))
        if category_id:
            change_category(conn, ticket_id, admin.id, int(category_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/admin/incidencias/{ticket_id}", status_code=303)


@router.get("/admin/usuarios", response_class=HTMLResponse)
def admin_usuarios(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
    q: str = "",
):
    users = list_requesters(conn, q=q)
    return templates.TemplateResponse(
        request, "admin/users.html", {"request": request, "users": users, "q": q, **_admin_ctx(admin)}
    )


@router.get("/admin/usuarios/{requester_id}", response_class=HTMLResponse)
def admin_usuario(
    request: Request,
    requester_id: int,
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
):
    user = conn.execute(
        "select * from requesters where id=?", (requester_id,)
    ).fetchone()
    if user is None:
        raise HTTPException(status_code=404, detail="Solicitante no encontrado")
    history = requester_history(conn, requester_id)
    departments = list_catalogs(conn, "departments", active_only=False)
    return templates.TemplateResponse(
        request,
        "admin/user.html",
        {
            "request": request,
            "user": user,
            "history": history,
            "departments": departments,
            **_admin_ctx(admin),
        },
    )


@router.post("/admin/usuarios/{requester_id}")
def admin_usuario_update(
    request: Request,
    requester_id: int,
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
    name: str = Form(""),
    department_id: str = Form(""),
    device_name: str = Form(""),
    apply_history: str = Form("0"),
    csrf_token: str = Form(""),
):
    verify_csrf(admin, csrf_token)
    try:
        update_requester(
            conn,
            requester_id,
            name=name,
            department_id=int(department_id) if department_id else None,
            device_name=device_name,
            apply_history=apply_history == "1",
            actor_id=admin.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/admin/usuarios/{requester_id}", status_code=303)


@router.get("/admin/catalogos", response_class=HTMLResponse)
def admin_catalogos(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
):
    return templates.TemplateResponse(
        request,
        "admin/catalogs.html",
        {
            "request": request,
            "departments": list_catalogs(conn, "departments", active_only=False),
            "categories": list_catalogs(conn, "categories", active_only=False),
            **_admin_ctx(admin),
        },
    )


@router.post("/admin/catalogos/{kind}")
def admin_catalogo_create(
    request: Request,
    kind: str,
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
    name: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(admin, csrf_token)
    try:
        create_catalog(conn, kind, name)
    except CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/admin/catalogos", status_code=303)


@router.post("/admin/catalogos/{kind}/{catalog_id}/{action}")
def admin_catalogo_action(
    request: Request,
    kind: str,
    catalog_id: int,
    action: str,
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
    name: str = Form(""),
    active: str = Form("1"),
    csrf_token: str = Form(""),
):
    verify_csrf(admin, csrf_token)
    if kind not in CATALOG_KINDS:
        raise HTTPException(status_code=404, detail="Catálogo no encontrado")
    try:
        if action == "rename":
            rename_catalog(conn, kind, catalog_id, name)
        elif action == "activar":
            set_catalog_active(conn, kind, catalog_id, True)
        elif action == "archivar":
            set_catalog_active(conn, kind, catalog_id, False)
        elif action == "subir":
            move_catalog(conn, kind, catalog_id, "up")
        elif action == "bajar":
            move_catalog(conn, kind, catalog_id, "down")
        else:
            raise HTTPException(status_code=404, detail="Acción no encontrada")
    except CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/admin/catalogos", status_code=303)


@router.get("/admin/export.csv")
def admin_export(
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
    state: str = "",
):
    sql = """
        select t.code, t.state, t.priority, t.subject, t.requester_name,
               d.name as department, c.name as category, t.created_at, t.updated_at
          from tickets t
          left join departments d on d.id = t.department_id
          left join categories c on c.id = t.category_id
    """
    params: list = []
    if state in STATES:
        sql += " where t.state = ?"
        params.append(state)
    sql += " order by t.created_at desc"
    rows = conn.execute(sql, params).fetchall()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Código",
            "Estado",
            "Prioridad",
            "Asunto",
            "Solicitante",
            "Departamento",
            "Categoría",
            "Creada",
            "Actualizada",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["code"],
                row["state"],
                row["priority"],
                row["subject"],
                row["requester_name"],
                row["department"] or "",
                row["category"] or "",
                row["created_at"],
                row["updated_at"],
            ]
        )
    buffer.seek(0)
    filename = f"incidencias-{utcnow().date().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/admin/password")
def admin_password(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
    current_password: str = Form(""),
    new_password: str = Form(""),
    repeat_password: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(admin, csrf_token)
    if new_password != repeat_password:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")
    if len(new_password) < 10:
        raise HTTPException(
            status_code=400, detail="La contraseña debe tener al menos 10 caracteres"
        )
    from app.admins import authenticate

    if not authenticate(conn, admin.username, current_password):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")
    conn.execute(
        "update admins set password_hash=?, password_changed_at=? where id=?",
        (hash_password(new_password), to_iso(utcnow()), admin.id),
    )
    conn.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.get("/api/admin/avisos")
def admin_avisos(
    admin: AdminContext = Depends(require_admin),
    conn=Depends(get_db),
):
    return JSONResponse(admin_unread(conn, admin.id))
