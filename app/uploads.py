from __future__ import annotations
import hashlib, os, secrets
from pathlib import Path
from dataclasses import dataclass

class UploadError(ValueError): pass

@dataclass
class SavedFile:
    original_name: str
    stored_name: str
    mime: str
    size: int

SIGNATURES = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "image/webp": b"RIFF",
    "application/pdf": b"%PDF-",
}

def save_upload(file, dest: Path, *, max_bytes: int) -> SavedFile:
    dest.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(16)
    ext = {".png":"png",".jpg":"jpg",".jpeg":"jpg",".webp":"webp",".pdf":"pdf"}.get(Path(file.filename).suffix.lower(), "bin")
    part = dest / (token + ".part")
    sig = file.file.read(16) if hasattr(file.file, "read") else b""
    file.file.seek(0)
    # basic validation
    found = False
    if sig.startswith(b"\x89PNG"):
        mime = "image/png"; found = True
    elif sig.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"; found = True
    elif sig[:4] == b"RIFF" and b"WEBP" in sig[:12]:
        mime = "image/webp"; found = True
    elif sig.startswith(b"%PDF-"):
        mime = "application/pdf"; found = True
    else:
        # try by extension if sig unknown
        ext_map = {".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".webp":"image/webp",".pdf":"application/pdf"}
        mime = ext_map.get(Path(file.filename).suffix.lower(), "application/octet-stream")
        if mime == "application/octet-stream":
            raise UploadError("firma no coincide")
        found = True
    total = 0
    with open(part, "wb") as out:
        while True:
            chunk = file.file.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                out.close()
                part.unlink(missing_ok=True)
                raise UploadError("tamaño excedido")
            out.write(chunk)
    stored = token + "." + ext
    part.rename(dest / stored)
    return SavedFile(original_name=file.filename, stored_name=stored, mime=mime, size=total)


def save_many(files, dest: Path, *, max_bytes: int, limit: int = 3) -> list[SavedFile]:
    saved: list[SavedFile] = []
    for file in files or []:
        if file is None or not getattr(file, "filename", ""):
            continue
        if len(saved) >= limit:
            raise UploadError(f"máximo {limit} adjuntos por mensaje")
        saved.append(save_upload(file, dest, max_bytes=max_bytes))
    return saved
