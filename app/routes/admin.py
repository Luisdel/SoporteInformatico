from __future__ import annotations
from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.db import get_db
from app.requesters import ensure_requester
from app.ticket_actions import (
    get_ticket_for_requester, list_messages, post_requester_message,
    mark_read_requester, requester_unread)
from app.tickets import get_ticket
from app.timeutil import utcnow, to_iso
from app.pcinfo import ClientInfo

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/admin")
def inbox(request: Request, conn=Depends(get_db)):
    rows = conn.execute("select * from tickets order by created_at desc").fetchall()
    return templates.TemplateResponse(request, "admin/inbox.html", {"request": request, "tickets": rows})


@router.get("/admin/tickets/{ticket_id}")
def ticket_detail(request: Request, ticket_id: int, conn=Depends(get_db)):
    t = get_ticket(conn, ticket_id)
    if t is None:
        raise HTTPException(status_code=404, detail="No encontrado")
    messages = list_messages(conn, ticket_id)
    return templates.TemplateResponse(request, "admin/detail.html", {"request": request, "ticket": t, "messages": messages})


@router.get("/mis-incidencias")
def list_own(request: Request, conn=Depends(get_db)):
    requester, _ = ensure_requester(request, conn, ip=request.client.host if request.client else "0.0.0.0", user_agent=request.headers.get("user-agent", ""))
    rows = conn.execute("select * from tickets where requester_id=? order by updated_at desc", (requester["id"],)).fetchall()
    return templates.TemplateResponse(request, "public/list.html", {"request": request, "tickets": rows})


@router.get("/admin/incidencias/{ticket_id}")
def admin_detail(request: Request, ticket_id: int, conn=Depends(get_db)):
    t = get_ticket(conn, ticket_id)
    if t is None:
        raise HTTPException(status_code=404, detail="No encontrado")
    messages = list_messages(conn, ticket_id, include_internal=True)
    return templates.TemplateResponse(request, "admin/ticket.html", {"request": request, "ticket": t, "messages": messages})


@router.post("/admin/incidencias/{ticket_id}/responder")
def admin_responder(request: Request, ticket_id: int, conn=Depends(get_db), body: str = Form(""), is_internal: str = Form("0")):
    admin_id = 1
    post_requester_message(conn, ticket_id, admin_id, body)
    if is_internal == "1":
        conn.execute("update messages set is_internal=1 where ticket_id=? and body=?", (ticket_id, body))
    else:
        if get_ticket(conn, ticket_id)["state"] == "nueva":
            conn.execute("update tickets set state='en_curso', assigned_admin_id=?, updated_at=? where id=?",
                (admin_id, to_iso(utcnow()), ticket_id))
            conn.execute("insert into ticket_events(ticket_id,event_type,author_admin_id,created_at) values(?,?,?,?)",
                (ticket_id, "assignment", admin_id, to_iso(utcnow())))
    conn.commit()
    resp = RedirectResponse(url=f"/admin/incidencias/{ticket_id}", status_code=303)
    return resp


@router.post("/admin/incidencias/{ticket_id}/estado")
def admin_estado(request: Request, ticket_id: int, conn=Depends(get_db), state: str = Form("")):
    admin_id = 1
    conn.execute("update tickets set state=?, resolved_at=? where id=?",
        (state, to_iso(utcnow()) if state=="resuelta" else None, ticket_id))
    conn.execute("insert into ticket_events(ticket_id,event_type,author_admin_id,created_at) values(?,?,?,?)",
        (ticket_id, "resolve" if state=="resuelta" else "state_change", admin_id, to_iso(utcnow())))
    conn.execute("insert into messages(ticket_id,author_type,author_admin_id,body,is_internal,created_at) values(?,'system',NULL,?,0,?)",
        (ticket_id, "Estado cambiado a "+state, to_iso(utcnow())))
    conn.commit()
    resp = RedirectResponse(url=f"/admin/incidencias/{ticket_id}", status_code=303)
    return resp


@router.get("/mis-incidencias/{ticket_id}")
def detail_own(request: Request, ticket_id: int, conn=Depends(get_db)):
    requester, _ = ensure_requester(request, conn, ip=request.client.host if request.client else "0.0.0.0", user_agent=request.headers.get("user-agent", ""))
    t = get_ticket_for_requester(conn, ticket_id, requester["id"])
    if t is None:
        raise HTTPException(status_code=404, detail="No encontrado")
    messages = list_messages(conn, ticket_id)
    mark_read_requester(conn, ticket_id, now=utcnow())
    return templates.TemplateResponse(request, "public/detail.html", {"request": request, "ticket": t, "messages": messages})


@router.post("/mis-incidencias/{ticket_id}/responder")
def responder_own(request: Request, ticket_id: int, conn=Depends(get_db), body: str = Form("")):
    requester, token = ensure_requester(request, conn, ip=request.client.host if request.client else "0.0.0.0", user_agent=request.headers.get("user-agent", ""))
    t = get_ticket_for_requester(conn, ticket_id, requester["id"])
    if t is None:
        raise HTTPException(status_code=404, detail="No encontrado")
    post_requester_message(conn, ticket_id, requester["id"], body)
    # Reopen if resolved
    if t["state"] == "resuelta":
        conn.execute("update tickets set state='en_curso', reopened_count=reopened_count+1, resolved_at=NULL, updated_at=? where id=?", (to_iso(utcnow()), ticket_id))
        conn.execute("insert into ticket_events(ticket_id,event_type,author_admin_id,created_at) values(?,?,?,?)", (ticket_id, "reopen", None, to_iso(utcnow())))
        conn.execute("insert into messages(ticket_id,author_type,author_admin_id,body,is_internal,created_at) values(?,'system',NULL,?,0,?)", (ticket_id, "Reabierto por respuesta", to_iso(utcnow())))
        conn.commit()
    resp = RedirectResponse(url=f"/mis-incidencias/{ticket_id}", status_code=303)
    if token and not request.cookies.get("device"):
        resp.set_cookie("device", token, httponly=True, samesite="lax", max_age=31_536_000, secure=request.app.state.settings.secure_cookies)
    return resp


@router.get("/api/avisos")
def avisos(request: Request, conn=Depends(get_db)):
    requester, _ = ensure_requester(request, conn, ip=request.client.host if request.client else "0.0.0.0", user_agent=request.headers.get("user-agent", ""))
    unread = requester_unread(conn, requester["id"])
    return JSONResponse({"unread": unread})
