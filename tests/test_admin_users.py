from app.db import connect
from tests.conftest import csrf_from

def test_listado_y_busqueda(admin_client, make_ticket):
    make_ticket(requester_name="María López")
    make_ticket(requester_name="Carlos Ruiz")
    r = admin_client.get("/admin/usuarios?q=María")
    assert "María López" in r.text and "Carlos Ruiz" not in r.text
    assert "Ver historial" in r.text
