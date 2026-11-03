from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from app.db import get_db
from app.ticket_actions import admin_unread

router = APIRouter()

@router.get("/api/admin/avisos")
def avisos_admin(conn=Depends(get_db)):
    return JSONResponse(admin_unread(conn, 1))
