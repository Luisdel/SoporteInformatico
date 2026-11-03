from app.uploads import save_upload, UploadError
from pathlib import Path

def test_save_valid_png():
    import io
    data = b"\x89PNG\r\n\x1a\nfake"
    class F:
        filename = "test.png"
        file = io.BytesIO(data)
    f = F()
    s = save_upload(f, Path("data/uploads"), max_bytes=5_000_000)
    assert s.mime == "image/png"

def test_size_exceeded():
    import io
    data = b"X" * (6_000_000)
    class F:
        filename = "big.png"
        file = io.BytesIO(data)
    f = F()
    try:
        save_upload(f, Path("data/uploads"), max_bytes=5_000_000)
        assert False, "debe rechazar"
    except UploadError as e:
        assert "tamaño" in str(e)
