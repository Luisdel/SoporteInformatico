from __future__ import annotations
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from app.db import get_db
from app.requesters import ensure_requester, update_requester
from app.tickets import create_ticket
from app.config import Settings, load_settings
from app.pcinfo import collect
from app.timeutil import utcnow

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
def public_form(request: Request, conn=Depends(get_db), settings: Settings = Depends(load_settings)):
    requester, token = ensure_requester(request, conn, ip=request.client.host if request.client else "0.0.0.0", user_agent=request.headers.get("user-agent", ""))
    depts = conn.execute("select * from departments where active=1 order by sort_order").fetchall()
    cats = conn.execute("select * from categories where active=1 order by sort_order").fetchall()
    resp = templates.TemplateResponse(request, "public/new.html", {
        "request": request, "requester": requester, "departments": depts, "categories": cats,
        "token": token})
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
    requester, token = ensure_requester(request, conn, ip=request.client.host if request.client else "0.0.0.0", user_agent=request.headers.get("user-agent", ""))
    dept_id = int(department_id or 0)
    cat_id = int(category_id or 0)
    name = (name or "").strip()
    subject = (subject or "").strip()
    description = (description or "").strip()
    if dept_id == 0 or cat_id == 0 or not name or not subject or not description or len(description) < 10:
        raise HTTPException(status_code=400, detail="datos incompletos")
    client = collect(request, settings) if hasattr(request.app.state, "pcinfo_collector") else {}
    try:
        ticket_id = create_ticket(conn, requester_id=requester["id"], requester_name=name,
            department_id=dept_id, category_id=cat_id, priority=priority, subject=subject,
            description=description, client=client, now=utcnow())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if token and not request.cookies.get("device"):
        resp = RedirectResponse(url="/mis-incidencias/" + str(requester["id"]), status_code=303)
        resp.set_cookie("device", token, httponly=True, samesite="lax", max_age=31_536_000, secure=settings.secure_cookies)
        return resp
    return RedirectResponse(url="/mis-incidencias/" + str(requester["id"]), status_code=303)
