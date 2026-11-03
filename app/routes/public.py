from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import Settings, load_settings
from app.db import get_db
from app.pcinfo import ClientInfo
from app.requesters import ensure_requester
from app.ticket_actions import (
    get_ticket_for_requester, list_messages, post_requester_message,
    mark_read_requester, requester_unread)
from app.tickets import create_ticket, get_ticket
from app.timeutil import utcnow, to_iso

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _client(request: Request, settings: Settings):
    if hasattr(request.app.state, "pcinfo_collector"):
        try:
            return request.app.state.pcinfo_collector(request, settings)
        except Exception:
            return ClientInfo(ip="", mac=None, hostname=None, browser="Chrome", os="Windows")
    return ClientInfo(ip="", mac=None, hostname=None, browser="Chrome", os="Windows")


def _ip(request: Request) -> str:
    return request.client.host if request.client else "0.0.0.0"


@router.get("/")
def public_form(request: Request, conn=Depends(get_db), settings: Settings = Depends(load_settings)):
    requester, token = ensure_requester(request, conn, ip=_ip(request), user_agent=request.headers.get("user-agent", ""))
    depts = conn.execute("select * from departments where active=1 order by sort_order").fetchall()
    cats = conn.execute("select * from categories where active=1 order by sort_order").fetchall()
    resp = templates.TemplateResponse(request, "public/new.html", {
        "request": request, "requester": requester, "departments": depts, "categories": cats})
    if token and not request.cookies.get("device"):
        resp.set_cookie("device", token, httponly=True, samesite="lax", max_age=31_536_000, secure=settings.secure_cookies)
    return resp


@router.post("/incidencias")
def create_incidencia(
    request: Request, conn=Depends(get_db), settings: Settings = Depends(load_settings),
    name: str = Form(""), department_id: str = Form(""), category_id: str = Form(""),
    priority: str = Form("normal"), subject: str = Form(""), description: str = Form(""),
    device_name: str = Form("")
):
    requester, token = ensure_requester(request, conn, ip=_ip(request), user_agent=request.headers.get("user-agent", ""))
    dept_id = int(department_id or 0)
    cat_id = int(category_id or 0)
    name = (name or "").strip()
    subject = (subject or "").strip()
    description = (description or "").strip()
    if not name or not subject or len(description) < 10 or dept_id == 0 or cat_id == 0:
        raise HTTPException(status_code=400, detail="datos incompletos")
    client = _client(request, settings)
    try:
        ticket_id = create_ticket(conn, requester_id=requester["id"], requester_name=name,
            department_id=dept_id, category_id=cat_id, priority=priority, subject=subject,
            description=description, client=client, now=utcnow())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    resp = RedirectResponse(url=f"/mis-incidencias/{requester['id']}", status_code=303)
    if token and not request.cookies.get("device"):
        resp.set_cookie("device", token, httponly=True, samesite="lax", max_age=31_536_000, secure=settings.secure_cookies)
    return resp


@router.get("/mis-incidencias")
def list_own(request: Request, conn=Depends(get_db)):
    requester, _ = ensure_requester(request, conn, ip=_ip(request), user_agent=request.headers.get("user-agent", ""))
    rows = conn.execute("select * from tickets where requester_id=? order by updated_at desc", (requester["id"],)).fetchall()
    return templates.TemplateResponse(request, "public/list.html", {"request": request, "tickets": rows})


@router.get("/mis-incidencias/{ticket_id}")
def detail_own(request: Request, ticket_id: int, conn=Depends(get_db)):
    requester, _ = ensure_requester(request, conn, ip=_ip(request), user_agent=request.headers.get("user-agent", ""))
    t = get_ticket(conn, ticket_id)
    if t is None or t["requester_id"] != requester["id"]:
        raise HTTPException(status_code=404, detail="No encontrado")
    messages = list_messages(conn, ticket_id)
    mark_read_requester(conn, ticket_id, now=utcnow())
    return templates.TemplateResponse(request, "public/detail.html", {"request": request, "ticket": t, "messages": messages})


@router.post("/mis-incidencias/{ticket_id}/responder")
def responder_own(request: Request, ticket_id: int, conn=Depends(get_db), body: str = Form("")):
    requester, token = ensure_requester(request, conn, ip=_ip(request), user_agent=request.headers.get("user-agent", ""))
    t = get_ticket(conn, ticket_id)
    if t is None or t["requester_id"] != requester["id"]:
        raise HTTPException(status_code=404, detail="No encontrado")
    post_requester_message(conn, ticket_id, requester["id"], body)
    if t["state"] == "resuelta":
        conn.execute("update tickets set state='en_curso', reopened_count=reopened_count+1, resolved_at=NULL, updated_at=? where id=?",
            (to_iso(utcnow()), ticket_id))
        conn.execute("insert into ticket_events(ticket_id,event_type,created_at) values(?,?,?)",
            (ticket_id, "reopen", to_iso(utcnow())))
        conn.execute("insert into messages(ticket_id,author_type,author_admin_id,body,is_internal,created_at) values(?,'system',NULL,?,0,?)",
            (ticket_id, "Reabierto por respuesta", to_iso(utcnow())))
        conn.commit()
    resp = RedirectResponse(url=f"/mis-incidencias/{ticket_id}", status_code=303)
    if token and not request.cookies.get("device"):
        resp.set_cookie("device", token, httponly=True, samesite="lax", max_age=31_536_000, secure=request.app.state.settings.secure_cookies)
    return resp


@router.get("/api/avisos")
def avisos(request: Request, conn=Depends(get_db)):
    requester, _ = ensure_requester(request, conn, ip=_ip(request), user_agent=request.headers.get("user-agent", ""))
    unread = requester_unread(conn, requester["id"])
    return JSONResponse({"unread": unread})
