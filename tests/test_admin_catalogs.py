from app.catalogs import CatalogError, create_catalog, set_catalog_active
from app.db import connect

def test_duplicado_ignorando_acentos_y_mayusculas(settings):
    conn = connect(settings.db_path)
    try:
        create_catalog(conn, "departments", "administracion")
    except CatalogError:
        pass
    else:
        raise AssertionError("debe rechazar duplicado sin acentos")
    conn.close()
