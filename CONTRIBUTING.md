# Contribuir

Gracias por ayudar a mejorar la aplicación de incidencias.

## Antes de empezar

- Usa Python 3.11 o superior; 3.13 es la versión comprobada en CI.
- Trabaja en una rama creada desde la rama por defecto.
- Mantén los cambios pequeños y relacionados con una sola mejora o corrección.
- Conserva la compatibilidad con SQLite y el despliegue mediante Uvicorn/systemd.

## Configuración local

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Ejecuta la aplicación con:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

No uses cuentas, contraseñas, rutas o datos reales en tests o documentación.

## Validación

Antes de abrir un pull request, ejecuta:

```bash
python -m compileall -q app tests
python -m pytest tests/ -q
```

Incluye tests para cambios de comportamiento y evita sustituir tests existentes
sin una razón clara.

## Pull requests

- Describe el problema y la solución.
- Indica cómo probar el cambio.
- Relaciona el issue correspondiente cuando exista.
- No incluyas archivos `.env`, bases de datos, adjuntos, secretos o caches.
- Los cambios funcionales deben conservar las rutas, cookies, permisos y formato
  de respuesta públicos salvo que el objetivo exija lo contrario.
