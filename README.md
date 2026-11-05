# App de Incidencias

Aplicación web de soporte informático para uso interno. Los usuarios abren y
siguen sus incidencias sin contraseña desde el navegador; los administradores
las gestionan con login, roles, asignación, catálogos y adjuntos.

- Backend: **FastAPI + SQLite** en un único proceso Uvicorn.
- Frontend: plantillas **Jinja2**, CSS y JavaScript propios (sin CDN ni build).
- Usuarios: cookie de dispositivo con hash SHA-256 en base de datos.
- Administradores: sesión en servidor, contraseña PBKDF2, CSRF y roles.
- Adjuntos: PNG, JPEG, WebP o PDF validados por firma (máx. 5 MB, 3 por mensaje).
- Fechas en **GFH/DTG Zulú** (`DDHHMMZMMMYY`, por ejemplo `051430ZNOV26`).
- Recarga automática cada 5 minutos, respetando borradores y scroll.

## Funcionalidad

### Usuario normal
- Abre una incidencia sin registrarse.
- Sigue sus incidencias desde “Mis incidencias”.
- Responde, adjunta archivos y recibe avisos de nuevas respuestas.
- Si responde a una incidencia resuelta, se reabre automáticamente.

### Administración
- Bandeja con filtros por estado, búsqueda y “solo asignadas a mí”.
- Detalle con conversación, notas internas, adjuntos e historial.
- Cambio de estado, prioridad, departamento, categoría y asignación.
- Usuarios: búsqueda, datos e historial de incidencias.
- Catálogos de departamentos y categorías.
- Exportación CSV compatible con Excel.
- Roles `admin` y `superadmin`.
- El superadmin crea administradores, cambia roles, activa/desactiva cuentas,
  resetea contraseñas y puede vaciar la base de datos desde la zona de peligro
  (conservando su propia cuenta y sesión).

## Requisitos

| Componente | Mínimo |
| --- | --- |
| Python | 3.11 o superior (probado en 3.13) |
| Sistema | Linux (Rocky Linux 9/10, RHEL, Ubuntu, Debian) o Windows |
| Base de datos | SQLite (incluida en Python) |
| Proxy recomendado | Nginx (producción) |

> **Rocky Linux 9** incluye Python 3.9 por defecto, que **no** sirve. Instala
> `python3.12` (AppStream) como se explica abajo. Rocky Linux 10 ya trae 3.12.

## Inicio rápido en local

### Linux / macOS

```bash
git clone https://github.com/TU-USUARIO/app-incidencias.git
cd app-incidencias
python3 -m venv .venv          # usa tu Python 3.11+ (en Rocky, python3.12)
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.manage create-admin admin --display-name "Administrador" --role superadmin
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Windows (PowerShell)

```powershell
git clone https://github.com/TU-USUARIO/app-incidencias.git
cd app-incidencias
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m app.manage create-admin admin --display-name "Administrador" --role superadmin
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abre:

- Formulario público: <http://127.0.0.1:8000/>
- Mis incidencias: <http://127.0.0.1:8000/mis-incidencias>
- Administración: <http://127.0.0.1:8000/admin>
- Salud: <http://127.0.0.1:8000/health> (también `/salud`)

## Instalación en producción sobre Rocky Linux

Probado para Rocky Linux 9 y 10 con Nginx, systemd y SELinux.

### 1. Paquetes del sistema

```bash
sudo dnf install -y epel-release
sudo dnf install -y git nginx firewalld rsync sqlite
sudo dnf install -y python3.12 python3.12-pip
python3.12 --version   # debe ser 3.12 (o superior)
```

Si tu versión de Rocky no ofrece `python3.12`, usa `python3.11` o instala
Python 3.12 desde fuentes. La aplicación requiere **3.11+**.

### 2. Usuario y directorio de la aplicación

```bash
sudo useradd --system --home-dir /opt/incidencias --shell /sbin/nologin incidencias
sudo git clone https://github.com/TU-USUARIO/app-incidencias.git /opt/incidencias
sudo chown -R incidencias:incidencias /opt/incidencias
```

### 3. Entorno virtual y dependencias

```bash
sudo -u incidencias python3.12 -m venv /opt/incidencias/.venv
sudo -u incidencias /opt/incidencias/.venv/bin/pip install --upgrade pip
sudo -u incidencias /opt/incidencias/.venv/bin/pip install -r /opt/incidencias/requirements.txt
```

### 4. Configuración

```bash
sudo -u incidencias cp /opt/incidencias/.env.example /opt/incidencias/.env
sudo -u incidencias nano /opt/incidencias/.env
```

Valores recomendados detrás de Nginx:

```ini
APP_HOST=127.0.0.1
APP_PORT=8000
DB_PATH=data/incidencias.db
UPLOAD_DIR=data/uploads
TIMEZONE=Europe/Madrid
TRUSTED_PROXIES=127.0.0.1/32
SESSION_HOURS=12
MAX_UPLOAD_MB=5
SECURE_COOKIES=0
RESOLVE_HOSTNAMES=1
```

Activa `SECURE_COOKIES=1` cuando sirvas por HTTPS (ver paso 8).

### 5. Primer administrador

```bash
cd /opt/incidencias
sudo -u incidencias .venv/bin/python -m app.manage create-admin admin \
  --display-name "Administrador" --role superadmin
```

Te pedirá la contraseña (mínimo 10 caracteres). Comandos útiles:

```bash
cd /opt/incidencias
sudo -u incidencias .venv/bin/python -m app.manage list-admins
sudo -u incidencias .venv/bin/python -m app.manage reset-password admin
```

### 6. Servicio systemd

Copia la unidad incluida:

```bash
sudo cp /opt/incidencias/deploy/incidencias.service /etc/systemd/system/incidencias.service
sudo systemctl daemon-reload
sudo systemctl enable --now incidencias
sudo systemctl status incidencias
```

Si instalaste en otra ruta, edita `WorkingDirectory`, `ExecStart`,
`EnvironmentFile` y `ReadWritePaths` dentro del archivo.

### 7. Nginx y SELinux

```bash
sudo cp /opt/incidencias/deploy/nginx-incidencias.conf /etc/nginx/conf.d/incidencias.conf
sudo nano /etc/nginx/conf.d/incidencias.conf   # pon tu dominio en server_name
sudo nginx -t
sudo systemctl enable --now nginx

# Permitir que Nginx se conecte a Uvicorn en 127.0.0.1:8000
sudo setsebool -P httpd_can_network_connect 1

# Abrir HTTP/HTTPS en firewalld
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### 8. HTTPS con Let's Encrypt (recomendado)

```bash
sudo dnf install -y certbot python3-certbot-nginx
sudo certbot --nginx -d incidencias.tu-dominio.com
```

Después:

```bash
sudo -u incidencias sed -i 's/^SECURE_COOKIES=.*/SECURE_COOKIES=1/' /opt/incidencias/.env
sudo systemctl restart incidencias
```

Certbot renueva el certificado automáticamente mediante su temporizador de
systemd.

### 9. Instalación automatizada (opcional)

El repositorio incluye un script para Rocky Linux que instala paquetes, crea el
usuario, el entorno virtual, el servicio y Nginx:

```bash
sudo DOMAIN=incidencias.tu-dominio.com bash deploy/install-rocky.sh
```

- Debe ejecutarse desde el repositorio clonado.
- No sobrescribe `.env` ni `data/` si ya existen.
- Al terminar, crea el administrador con el comando que imprime por pantalla.
- Revisa siempre el script antes de ejecutarlo como root.

## Configuración

Todas las variables se leen de `.env` (o del entorno del proceso):

| Variable | Por defecto | Descripción |
| --- | --- | --- |
| `APP_HOST` | `0.0.0.0` | Interfaz por defecto para ejecuciones propias |
| `APP_PORT` | `8000` | Puerto por defecto |
| `DB_PATH` | `data/incidencias.db` | Ruta de SQLite (relativa al directorio de trabajo) |
| `UPLOAD_DIR` | `data/uploads` | Carpeta de adjuntos |
| `TIMEZONE` | `Europe/Madrid` | Zona para utilidades locales (la UI usa GFH Zulú) |
| `TRUSTED_PROXIES` | vacío | CIDR de proxies de confianza para `X-Forwarded-For` |
| `TLS_CERT` / `TLS_KEY` | vacío | TLS directo opcional en Uvicorn |
| `SESSION_HOURS` | `12` | Horas de inactividad de la sesión admin |
| `MAX_UPLOAD_MB` | `5` | Tamaño máximo por adjunto |
| `SECURE_COOKIES` | `0` | `1` obliga a cookies solo por HTTPS |
| `PBKDF2_ITERATIONS` | `600000` | Iteraciones del hash de contraseñas |
| `RESOLVE_HOSTNAMES` | `1` | Resolución inversa de IP a hostname |

## Operación

### Logs

```bash
sudo journalctl -u incidencias -f
sudo tail -f /var/log/nginx/error.log
```

### Copias de seguridad

Copia en caliente de SQLite (recomendado):

```bash
sudo -u incidencias sqlite3 /opt/incidencias/data/incidencias.db \
  ".backup '/var/backups/incidencias-$(date +%F).db'"
sudo tar czf /var/backups/uploads-$(date +%F).tar.gz -C /opt/incidencias/data uploads
```

Restauración:

```bash
sudo systemctl stop incidencias
sudo cp /var/backups/incidencias-2026-11-05.db /opt/incidencias/data/incidencias.db
sudo chown incidencias:incidencias /opt/incidencias/data/incidencias.db
sudo systemctl start incidencias
```

### Actualizar

```bash
sudo -u incidencias git -C /opt/incidencias pull
sudo -u incidencias /opt/incidencias/.venv/bin/pip install -r /opt/incidencias/requirements.txt
sudo systemctl restart incidencias
```

Las migraciones de esquema se aplican solas al arrancar.

### Limpiar la base de datos

Entra como superadmin en **Administradores → Zona de peligro** y escribe
`BORRAR`. Se eliminan incidencias, mensajes, adjuntos, solicitantes y el resto
de administradores; se conservan tu cuenta y tu sesión.

## Seguridad

- Usa siempre HTTPS en producción y activa `SECURE_COOKIES=1`.
- Configura `TRUSTED_PROXIES=127.0.0.1/32` solo si Nginx está en la misma máquina.
- Mantén el servicio escuchando en `127.0.0.1` detrás del proxy.
- Restringe permisos: `.env` y `data/` deben pertenecer al usuario del servicio.
- Hay rate limiting en el login y tokens CSRF en todos los formularios admin.
- Las contraseñas usan PBKDF2-SHA256 con 600 000 iteraciones.
- SQLite funciona mejor con **un solo worker** de Uvicorn, como en la unidad
  incluida. No uses `--workers N` salvo que sepas lo que haces.
- Haz copias periódicas de `data/incidencias.db` y `data/uploads/`.

## Desarrollo y pruebas

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

La suite cubre creación pública, cookie de dispositivo, login y sesiones,
bandeja y detalle, asignación y avisos, usuarios, catálogos, contraseñas,
exportación CSV, adjuntos, administradores, limpieza total, formato GFH y
validaciones de seguridad.

## Estructura

```
app/
  main.py             creación de la app y routers
  db.py               esquema SQLite, migraciones y conexión
  config.py           carga de .env y ajustes
  security.py         hashes, sesiones y rate limiting
  auth.py             dependencias de sesión admin y CSRF
  admins.py           cuentas, roles y autenticación
  requesters.py       usuarios por cookie de dispositivo
  tickets.py          creación, estados y prioridades
  ticket_actions.py   mensajes, estados, asignación y avisos
  catalogs.py         departamentos y categorías
  uploads.py          guardado y validación de adjuntos
  pcinfo.py           IP, MAC, hostname y user-agent
  manage.py           CLI de administración
  routes/             rutas públicas, admin, auth y adjuntos
  templates/          plantillas Jinja2
  static/             CSS y JavaScript
deploy/
  incidencias.service unidad systemd
  nginx-incidencias.conf configuración de Nginx
  install-rocky.sh    instalación automatizada
tests/                suite pytest
```

## Solución de problemas

| Síntoma | Causa probable | Solución |
| --- | --- | --- |
| `SyntaxError` al arrancar | Python < 3.11 | Instala `python3.12` y recrea el venv |
| Nginx devuelve 502 | Uvicorn parado o SELinux | `systemctl status incidencias`; `setsebool -P httpd_can_network_connect 1` |
| `Permission denied` en `data/` | Propietario incorrecto | `chown -R incidencias:incidencias /opt/incidencias/data` |
| Error 413 al subir | Límite de Nginx | Ajusta `client_max_body_size` y `MAX_UPLOAD_MB` |
| `database is locked` | Varios workers | Usa un solo worker de Uvicorn |
| No aparecen avisos | Proxy sin cabeceras | Revisa `X-Forwarded-For` y `TRUSTED_PROXIES` |
| Cookies no se guardan con HTTPS | `SECURE_COOKIES=0` con proxy | Ponlo a `1` y reinicia |

## Licencia

Este repositorio no incluye todavía una licencia de distribución. Antes de
publicarlo, añade la que corresponda (por ejemplo MIT o Apache-2.0).
