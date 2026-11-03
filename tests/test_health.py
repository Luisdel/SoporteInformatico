from app.config import load_settings

def test_salud(client):
    r = client.get("/salud")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

def test_settings_defaults(tmp_path):
    s = load_settings({"DB_PATH": str(tmp_path / "i.db"), "UPLOAD_DIR": str(tmp_path / "up")})
    assert (s.host, s.port, s.timezone, s.session_hours, s.max_upload_mb) == (
        "0.0.0.0", 8000, "Europe/Madrid", 12, 5)
    assert s.trusted_proxies == ()
    assert s.pbkdf2_iterations == 600_000
