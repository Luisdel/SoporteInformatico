# App de Incidencias

Aplicación web interna de incidencias: los usuarios abren y siguen sus
incidencias sin contraseña desde el navegador, y los administradores las
gestionan con login, asignación, catálogos y datos del equipo.

- Backend: FastAPI + SQLite en un único proceso Uvicorn.
- Frontend: plantillas Jinja2, CSS y JS propios (sin CDN ni build).
- Usuarios: cookie de dispositivo (hash SHA-256 en base de datos).
- Administradores: sesión en servidor, contraseña PBKDF2 y CSRF.
- Adjuntos: PNG, JPEG, WebP o PDF validados por firma, máximo 5 MB y 3 por mensaje.
- Actualización automática: las páginas se recargan cada 5 minutos, salvo que haya
  un borrador en curso; se conserva la posición de scroll.

## Requisitos

- Python 3.13
- Dependencias de `requirements.txt`

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Configuración

Copia `.env.example` a `.env` y ajusta los valores si hace falta. Los más
importantes:

| Variable | Por defecto | Descripción |
| --- | --- | --- |
| `APP_HOST` | `0.0.0.0` | Interfaz de escucha |
| `APP_PORT` | `8000` | Puerto |
| `DB_PATH` | `data/incidencias.db` | Base de datos SQLite |
| `UPLOAD_DIR` | `data/uploads` | Carpeta de adjuntos |
| `SESSION_HOURS` | `12` | Horas de inactividad de la sesión admin |
| `MAX_UPLOAD_MB` | `5` | Tamaño máximo por adjunto |
| `SECURE_COOKIES` | `0` | Ponlo a `1` si sirves por HTTPS |

## Crear el primer administrador

La base de datos se crea sola al arrancar, pero el primer administrador debe
crearse con la CLI:

```powershell
python -m app.manage create-admin admin --display-name "Administrador" --role superadmin
```

Te pedirá la contraseña (mínimo 10 caracteres). Otros comandos útiles:

```powershell
python -m app.manage list-admins
python -m app.manage reset-password admin
```

Ya dentro de la aplicación, el superadministrador puede crear más cuentas desde
**Administradores** (crear, activar/desactivar, cambiar rol y resetear
contraseña). Esa misma página incluye la **zona de peligro** para vaciar la base
de datos completa: incidencias, mensajes, adjuntos, solicitantes y el resto de
administradores. La cuenta y la sesión del superadministrador actual se
conservan.

## Formato de fecha

Todas las fechas y horas se muestran en **GFH/DTG Zulú** (`DDHHMMZMMMYY`), por
ejemplo `051430ZNOV26`. La base de datos guarda ISO 8601 en UTC; el formato se
aplica en la interfaz y en la exportación CSV.

## Arrancar

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- Formulario público: <http://127.0.0.1:8000/>
- Mis incidencias: <http://127.0.0.1:8000/mis-incidencias>
- Administración: <http://127.0.0.1:8000/admin>
- Salud: <http://127.0.0.1:8000/salud> (también `/health`)

Para producción usa un proxy inverso con TLS y activa `SECURE_COOKIES=1`.

## Pruebas

```powershell
python -m pytest tests/ -q
```

La suite cubre creación pública, cookie de dispositivo, login y sesiones,
bandeja y detalle de admin, asignación y avisos, usuarios, catálogos,
contraseñas, exportación CSV, adjuntos, gestión de administradores, limpieza
total de la base de datos, formato GFH y validaciones de seguridad.

## Estructura

```
app/
  main.py             creación de la app y routers
  db.py               esquema SQLite, migraciones y conexión
  security.py         hashes, sesiones y rate limiting
  auth.py             dependencias de sesión admin y CSRF
  admins.py           alta/edición de cuentas y autenticación
  requesters.py       usuarios por cookie de dispositivo
  tickets.py          creación de incidencias y numeración
  ticket_actions.py   mensajes, estados, asignación y avisos
  catalogs.py         departamentos y categorías
  uploads.py          guardado y validación de adjuntos
  pcinfo.py           IP, MAC, hostname y user-agent
  manage.py           CLI de administración
  routes/             rutas públicas, admin, auth, adjuntos
  templates/          plantillas Jinja2
  static/             CSS y JS
tests/                suite pytest
docs/                 plan y diseño
```
