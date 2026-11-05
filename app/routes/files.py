from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.db import get_db
from app.security import find_admin_session, hash_token

router = APIRouter()


@router.get("/adjuntos/{attachment_id}")
def download(attachment_id: int, request: Request, conn=Depends(get_db)):
    row = conn.execute(
        """
        select a.*, t.requester_id
          from attachments a
          join tickets t on t.id = a.ticket_id
         where a.id = ?
        """,
        (attachment_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")

    allowed = False
    device = request.cookies.get("device")
    if device:
        requester = conn.execute(
            "select id from requesters where device_token_hash=?",
            (hash_token(device),),
        ).fetchone()
        allowed = requester is not None and requester["id"] == row["requester_id"]
    if not allowed:
        admin_token = request.cookies.get("admin_session")
        if admin_token:
            allowed = (
                find_admin_session(
                    conn,
                    admin_token,
                    idle_hours=request.app.state.settings.session_hours,
                )
                is not None
            )
    if not allowed:
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")

    path = Path(request.app.state.settings.upload_dir) / row["stored_name"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    return FileResponse(
        path, filename=row["original_name"], media_type=row["mime"]
    )
