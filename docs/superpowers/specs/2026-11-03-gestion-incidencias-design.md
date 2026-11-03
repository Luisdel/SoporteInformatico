# Aplicación de incidencias — Diseño

Fecha: 2026-11-03
Estado: pendiente de aprobación

## 1. Para qué

Hoy las incidencias se cuentan de viva voz al informático. Se pierden, se olvidan y no queda
constancia de qué pasó. Queremos informatizar ese circuito con algo pequeño: el usuario abre una
incidencia desde el navegador, el informático la recibe con los datos del equipo y le responde por
el mismo hilo.

No es un sistema de helpdesk corporativo. Es una herramienta interna, sencilla y útil, para una
plantilla pequeña o mediana en una red de oficina.

## 2. Quién lo usa

| Rol | Cómo entra | Qué puede hacer |
|---|---|---|
| **Usuario** (sin contraseña) | Abre `http://IP:8000` en el navegador | Abrir incidencias, ver todas las suyas (abiertas y resueltas) con el chat completo, responder y adjuntar capturas |
| **Admin** | Login con usuario y contraseña validado contra el servidor | Bandeja completa, responder, cambiar estado/prioridad/departamento/tipo, asignar incidencias, gestionar usuarios y catálogos, exportar CSV |
| **Superadmin** | Login, cuenta creada en la instalación | Todo lo del admin + crear/desactivar admins y resetear sus contraseñas |

El área de admin no muestra ni un dato sin sesión válida. Cualquier petición sin sesión redirige al
login (o devuelve 401 si es una llamada de datos).

## 3. Objetivos

- Que abrir una incidencia cueste menos de un minuto y no requiera instalar nada en el PC.
- Que el admin reciba el mensaje **y** el contexto del equipo: quién, desde qué equipo, IP, MAC si
  se puede, navegador y sistema, fecha.
- Que exista un hilo de conversación por incidencia, visible para el usuario, con aviso de
  respuesta en la propia web.
- Que el admin pueda organizar el trabajo: estados, prioridad, asignación a un admin, búsqueda.
- Que departamentos y tipos de incidencia los defina el admin, no el código.
- Que quede trazabilidad de quién cambió qué.

## 4. Fuera de alcance (no-goals)

- Correo electrónico, SMS, notificaciones push o de escritorio. El aviso es un contador y un punto
  rojo en la web, más un `(1)` en el título de la pestaña. Los navegadores solo permiten
  notificaciones de escritorio en HTTPS y esta aplicación funciona por HTTP en la LAN.
- Integración con Active Directory / LDAP / SSO.
- App de escritorio o móvil nativa. Todo es web responsive.
- Inventario automático de equipos (agente).
- Multi-empresa o multi-sede con separación de datos.
- Antivirus de adjuntos, firma digital, SLA con relojes y escalados automáticos.
- Estadísticas avanzadas. Solo contadores simples y exportación CSV.

## 5. Anti-objetivos

- **No inventar datos del equipo.** Si la MAC o el nombre no se pueden obtener, se dice "No
  disponible". Nunca se muestra la MAC del router como si fuera la del PC.
- **No dejar el área de admin accesible sin login**, ni siquiera "solo para ver".
- **No perder historial al archivar** un departamento o un tipo.
- **No exigir permisos de administrador** en los PCs de los usuarios.
- **No guardar contraseñas en claro** ni permitir enumerar incidencias por número.

## 6. Arquitectura

```
PC del usuario ──HTTP──┐
                       ├──► Servidor Linux o Windows Server
PC del admin  ──HTTP──┘      FastAPI + Uvicorn (1 proceso)
                             SQLite (WAL) + carpeta de adjuntos
                             Plantillas Jinja2 + CSS/JS propios (sin CDN)
```

- Un único servicio HTTP en el puerto configurable (8000 por defecto), escuchando en `0.0.0.0`.
- Sin dependencia de internet: todo el CSS y el JS se sirven desde el propio servidor.
- SQLite en modo WAL, con `busy_timeout` de 5 s. Un solo worker de Uvicorn (suficiente para decenas
  de usuarios y decenas de miles de incidencias).
- Las capturas se guardan en disco, fuera del directorio estático, y se sirven por una ruta que
  comprueba permisos.
- Zona horaria: se guarda todo en UTC y se muestra en `Europe/Madrid` (configurable).

### Stack

- Python 3.11+ (probado con 3.13), FastAPI, Uvicorn, Jinja2, python-multipart, python-dotenv.
- SQLite mediante `sqlite3` de la biblioteca estándar, sin ORM.
- Contraseñas con `hashlib.pbkdf2_hmac` (SHA-256, 600 000 iteraciones, sal por usuario).
- Tests con pytest y `TestClient` (httpx).
- CSS y JS escritos a mano. Nada de frameworks de frontend.

## 7. Modelo de datos

Tablas principales (nombres en inglés en la base de datos, interfaz en español):

**`admins`**
`id`, `username` (único, sin distinguir mayúsculas), `display_name`, `password_hash`, `role`
(`superadmin` | `admin`), `active`, `created_at`, `last_login_at`, `password_changed_at`.

**`admin_sessions`**
`id`, `token_hash`, `admin_id`, `created_at`, `last_seen_at`, `expires_at`, `ip`, `user_agent`.
Permite cerrar sesión de verdad y que desactivar una cuenta expulse al instante.

**`departments`** / **`categories`**
`id`, `name`, `active`, `sort_order`, `created_at`. Se renombran y se archivan (`active=0`); nunca se
borran.

**`requesters`** (usuarios sin contraseña)
`id`, `device_token_hash`, `name`, `department_id`, `device_name`, `last_ip`, `last_mac`,
`last_user_agent`, `created_at`, `updated_at`, `last_seen_at`.
Un requester = un navegador/dispositivo. La cookie es la credencial; en la base solo se guarda su
hash. Se asume **un usuario por PC**: si dos personas comparten el mismo navegador, verán el
historial la una de la otra. Ese caso queda fuera de alcance.

**`tickets`**
`id`, `code`, `requester_id`, `requester_name`, `department_id`, `category_id`, `priority`
(`baja|normal|alta|urgente`), `state` (`nueva|en_curso|en_espera|resuelta`), `subject`,
`description`, `assigned_admin_id` (nullable), `created_at`, `updated_at`, `resolved_at`,
`requester_last_read_at`, `client_ip`, `client_mac`, `client_hostname`, `client_user_agent`,
`reopened_count`.
`code` tiene el formato `INC-2026-0042`, con contador por año y relleno a 4 dígitos.
`requester_name` es una **foto fija** en el momento de crear la incidencia: si la persona cambia de
nombre, el historial antiguo no se reescribe. `department_id` es el departamento elegido en ese
momento; si el departamento se renombra, el nuevo nombre se ve también en el historial porque es el
mismo registro.

**`messages`**
`id`, `ticket_id`, `author_type` (`requester|admin|system`), `author_requester_id`,
`author_admin_id`, `body`, `is_internal`, `created_at`.
Las notas internas (`is_internal=1`) nunca se envían al usuario.

**`attachments`**
`id`, `ticket_id`, `message_id`, `original_name`, `stored_name`, `mime`, `size`, `created_at`.

**`ticket_events`** (auditoría)
`id`, `ticket_id`, `admin_id`, `event_type` (`state`, `priority`, `department`, `category`,
`assignment`, `reopen`, `resolve`), `old_value`, `new_value`, `created_at`.

**`admin_audit`**
`id`, `admin_id`, `action`, `detail`, `ip`, `created_at`. Para altas/bajas de admins y cambios de
contraseña.

**`ticket_reads`**
`admin_id`, `ticket_id`, `last_read_at`. Marca hasta dónde ha leído cada admin una incidencia, para
el aviso de mensajes nuevos en "Mis incidencias".

**`ticket_counters`**
`year`, `value`. Se incrementa dentro de la misma transacción que crea la incidencia.

### Reglas

- Una incidencia siempre conserva su departamento y tipo aunque se archiven después.
- Renombrar un departamento cambia el nombre en el historial (es el mismo registro). Se avisa en la
  interfaz de que el cambio afecta a las incidencias anteriores.
- Archivar no borra. Reactivar vuelve a ofrecerlo en el formulario.
- No se puede archivar el último departamento activo ni el último tipo activo.
- El estado `resuelta` no cierra el hilo: si el usuario responde, vuelve a `en_curso`, se registra
  el evento `reopen` y se avisa al admin asignado (o a todos si no tiene).

## 8. Flujos

### 8.1 Primera visita del usuario

1. `GET /` emite si no existe una cookie `device` (256 bits aleatorios, `HttpOnly`, `SameSite=Lax`,
   un año) y crea el requester con nombre vacío.
2. El formulario pide nombre, departamento, nombre del equipo (opcional, precargado si se pudo
   resolver por DNS inverso), tipo, urgencia, asunto, descripción y hasta 3 capturas.
3. Al enviar se crea la incidencia + primer mensaje + adjuntos en una transacción, y se muestra el
   número (`INC-2026-0042`) con enlace a "Mis incidencias".
4. El nombre y el departamento quedan guardados en el servidor asociados a la cookie: en la
   siguiente visita aparecen rellenos. No se usa `localStorage` para datos personales.

Si el usuario borra las cookies del navegador, pierde el acceso a su historial. Es la consecuencia
de no tener contraseña; se documenta y se acepta.

### 8.2 Usuario: mis incidencias

- Lista todas las suyas, también resueltas, con código, asunto, estado y última actividad.
- Al abrir una, se ve el hilo completo (mensajes públicos, nunca notas internas) y se actualiza
  `requester_last_read_at`.
- Puede responder en cualquier estado. En `resuelta`, la incidencia se reabre.
- Aviso: cada 30 s se consulta `/api/avisos`; si hay mensajes de admin posteriores a la última
  lectura, se muestra un punto rojo en "Mis incidencias" y un `(1)` en el título de la pestaña. No
  se usan notificaciones del navegador: requieren HTTPS y aquí se trabaja por HTTP en la LAN.

### 8.3 Admin: bandeja y detalle

- Login en `/admin/login`. Sesión de 12 h de inactividad y 7 días máximo.
- Contadores: abiertas, sin asignar, urgentes abiertas, resueltas en 7 días, mis incidencias.
- Filtros: estado, prioridad, tipo, departamento, asignación (`todas` / `sin asignar` / `mis`) y
  búsqueda por código, asunto, texto o nombre. Paginación de 50.
- Detalle: datos del equipo, hilo, caja de respuesta con "nota interna", selector de estado,
  prioridad, departamento, tipo y admin asignado.
- **Asignación:** botón "Asignármela" / "Liberar" y selector para reasignar. Al enviar la primera
  respuesta pública a una incidencia sin asignar, se asigna automáticamente a quien responde y se
  registra el evento. Cualquier admin puede reasignársela, pero la interfaz muestra quién la lleva.
- "Marcar resuelta" pide confirmación y guarda `resolved_at`.
- Botón "Copiar datos del equipo" y vista imprimible del detalle.
- Exportación CSV de la vista filtrada, con BOM UTF-8 para que Excel abra bien los acentos.
- **Avisos del admin:** `/api/admin/avisos` cada 30 s devuelve cuántas incidencias hay sin asignar
  (abiertas) y cuántos mensajes nuevos de usuario hay en las asignadas a mí, usando `ticket_reads`.
  Se muestran como dos contadores en la navegación. La primera respuesta pública a una incidencia
  sin asignar también la asigna a quien responde.

### 8.3.1 Máquina de estados

| Desde | Acción | Hacia | Efectos |
|---|---|---|---|
| `nueva` | Primera respuesta pública de un admin | `en_curso` | Asigna si no tiene admin; evento `state` + `assignment` |
| `nueva` / `en_curso` | Admin marca "en espera de usuario" | `en_espera` | Evento `state`; mensaje de sistema visible |
| `en_espera` | Responde el usuario | `en_curso` | Evento `state`; aviso al admin asignado |
| `nueva` / `en_curso` / `en_espera` | Admin marca resuelta | `resuelta` | `resolved_at`, evento `resolve`, mensaje de sistema |
| `resuelta` | Responde el usuario | `en_curso` | `resolved_at=NULL`, `reopened_count++`, evento `reopen`, mensaje de sistema, aviso al admin |
| `resuelta` | Admin elige "reabrir" | `en_curso` | `resolved_at=NULL`, evento `state` (no cuenta como reapertura del usuario) |

- El selector del admin ofrece `en_curso`, `en_espera` y `resuelta`; `nueva` es solo el estado
  inicial y no se puede volver a él. El admin puede fijar cualquiera de los tres desde cualquier
  estado actual.
- Los mensajes de sistema (`author_type=system`) son visibles para el usuario; los cambios de
  asignación no generan mensaje visible, solo auditoría.
- Cualquier cambio manual de estado queda en `ticket_events` con quién y cuándo.

### 8.4 Admin: usuarios

- Listado de requesters con nombre, departamento, equipo, IP, MAC si se conoce, número de
  incidencias, abiertas y última actividad.
- Búsqueda y filtros (todos / activos este mes / con incidencias abiertas).
- Ver historial completo.
- Editar nombre, departamento y nombre del equipo. No se puede bloquear ni borrar (decisión del
  usuario). La corrección afecta a las incidencias futuras; una casilla permite aplicarla también a
  las anteriores para arreglar una errata, dejando registro en `ticket_events`.

### 8.5 Admin: departamentos y tipos

- Dos listas con crear, renombrar, archivar/reactivar y ordenar con flechas arriba/abajo.
- No hay borrado físico: la única forma de retirar un elemento es archivarlo. Se explica en
  pantalla que lo archivado deja de ofrecerse pero conserva el historial.
- No se permite nombre vacío ni duplicado (sin distinguir mayúsculas/acentos).
- No se puede archivar el último departamento activo ni el último tipo activo.

### 8.6 Superadmin: cuentas de admin

- Crear admins o superadmins (usuario, nombre visible, rol y contraseña inicial), resetear
  contraseña, activar/desactivar y cambiar el rol.
- No puede desactivarse a sí mismo ni degradarse, ni dejar el sistema sin al menos un superadmin
  activo.
- Al resetear una contraseña, cambiar el rol o desactivar una cuenta se invalidan sus sesiones.
- Un admin normal puede cambiar su propia contraseña pidiendo la actual.
- No hay recuperación por correo. Si se pierde la contraseña del superadmin, el comando de rescate
  del apartado 8.7 la restablece desde el propio servidor.
- Crear cuentas de admin no está limitado a una sola: puede haber varios superadmins.

### 8.7 Instalación

- `python -m app.manage create-superadmin` pide usuario y contraseña (mínimo 10 caracteres) y crea
  la cuenta. Alternativa no interactiva:
  `SUPERADMIN_USER=... SUPERADMIN_PASSWORD=... python -m app.manage create-superadmin --from-env`.
- No existe página web de primer arranque: nadie puede reclamar la instalación desde la red.
- Semilla inicial de catálogos (solo si están vacíos): departamentos Administración, Comercial,
  Producción, Almacén, Dirección; tipos Correo/Outlook, Hardware, Software, Red/Internet,
  Impresora, Accesos y contraseñas, Otro.
- `python -m app.manage backup --out DIR` copia la base con la API de backup de SQLite y la carpeta
  de adjuntos.
- `python -m app.manage reset-password --username X` restablece la contraseña de un admin o
  superadmin desde el servidor (rescate). No hay ruta web para esto.

## 9. Datos del equipo: qué se puede y qué no

Un navegador no puede leer la MAC ni el nombre del equipo. Se captura lo que el servidor sí puede
ver, y se etiqueta con honestidad:

| Dato | Cómo | Límite |
|---|---|---|
| IP | `request.client.host` | Si hay proxy inverso, solo se acepta `X-Forwarded-For` de proxies en `TRUSTED_PROXIES`; si no, se ignora para evitar suplantación |
| MAC | Tabla de vecinos del servidor para esa IP (`ip neigh` en Linux, `arp -a` / `Get-NetNeighbor` en Windows) | Solo si el equipo está en la misma red local. Si la IP viene enrutada, no hay entrada y se muestra "No disponible". Se descarta la MAC si coincide con la puerta de enlace |
| Nombre del equipo | DNS inverso con tiempo de espera de 1 s + campo editable por el usuario que se recuerda | En grupos de trabajo el DNS inverso suele fallar; por eso el campo manual manda si está relleno |
| Navegador y SO | `User-Agent`, parseo básico por expresiones regulares | Aproximado; se muestra tal cual se detecta |
| Fecha | Servidor | UTC en base, Europe/Madrid en pantalla |

El detalle del admin muestra la IP "vista por el servidor" y una nota cuando la MAC no está
disponible por estar en otra subred. Nunca se rellena con un valor supuesto.

## 10. Seguridad

- **Sesiones de admin:** token aleatorio de 256 bits en cookie `HttpOnly`, `SameSite=Lax` y
  `Secure` cuando hay TLS. En base solo el hash. Expiración por inactividad y absoluta.
- **Contraseñas:** PBKDF2-SHA256, 600 000 iteraciones, sal de 16 bytes, comparación en tiempo
  constante. Mínimo 10 caracteres. Límite de 5 intentos fallidos por IP+usuario cada 15 minutos.
- **CSRF:** token por sesión en todos los formularios que modifican datos.
- **Abuso del formulario público:** límite de 10 incidencias por IP y hora, asunto y descripción
  con longitud máxima, y validación de campos obligatorios. No hay CSRF en el formulario público
  porque no hay sesión que proteger; el límite por IP es la defensa.
- **Autorización:** dependencia `require_admin` en todas las rutas `/admin` y `/api/admin`;
  `require_superadmin` en cuentas. Pruebas automáticas que lo verifican ruta por ruta.
- **Aislamiento del usuario:** "Mis incidencias" se filtra por `requester_id` de la cookie. Un
  código de incidencia no da acceso: no hay ruta pública por código.
- **Adjuntos:** máximo 5 MB y 3 por mensaje; se valida el contenido real (firma PNG/JPEG/WebP/PDF),
  no solo la extensión; nombre en disco aleatorio; descarga solo para el dueño de la incidencia o
  un admin; `Content-Disposition: attachment` y `X-Content-Type-Options: nosniff`.
- **HTTP en la LAN:** por defecto no hay TLS. Las contraseñas de admin viajan sin cifrar dentro de
  la red. Se documenta y se ofrece configuración de certificado en Uvicorn o proxy inverso para
  redes no confiables. No se promete seguridad que no hay.
- **Registro:** sin contraseñas ni tokens en logs. Errores 500 genéricos para el usuario, detalle en
  el log del servidor.

## 11. Interfaz

- **Público:** cabecera "Soporte Informático", pestañas "Nueva incidencia" y "Mis incidencias",
  enlace discreto a Admin. Formulario en una columna, máximo 760 px.
- **Login:** página sobria, sin revelar si el usuario existe.
- **Admin:** navegación Incidencias / Usuarios / Departamentos y tipos / Cuentas / Exportar CSV.
  Bandeja de dos paneles (lista + detalle) que colapsa a una columna en pantallas estrechas.
- Estados con color y texto (no solo color): Nueva azul, En curso ámbar, En espera gris, Resuelta
  verde. Urgencia siempre con etiqueta.
- Accesible con teclado, etiquetas en todos los campos y foco visible.
- Sin recursos externos: funciona en una red sin salida a internet.
- Los textos de la interfaz, en español.

## 12. Estructura del proyecto

```
app/
  main.py            arranque FastAPI y rutas
  config.py          variables de entorno
  db.py              conexión, WAL y migraciones (PRAGMA user_version)
  security.py        hash de contraseñas, sesiones, CSRF, rate limit
  auth.py            dependencias de sesión y permisos
  tickets.py         consultas y reglas de incidencias
  requesters.py      usuarios sin contraseña
  admins.py          cuentas y auditoría
  catalogs.py        departamentos y tipos
  pcinfo.py          IP, MAC, DNS inverso, user-agent
  uploads.py         validación y almacenamiento de adjuntos
  routes/            public.py, admin.py, api.py, auth.py
  templates/         Jinja2
  static/            app.css, app.js
  manage.py          create-superadmin, reset-password, backup, seed
tests/
data/                incidencias.db y uploads/ (creado en ejecución)
docs/
requirements.txt
.env.example
run.sh  run.bat
deploy/              systemd y servicio de Windows
README.md
```

## 13. Despliegue

- Linux: venv, `pip install -r requirements.txt`, servicio systemd con `run.sh`, `Restart=always`.
- Windows Server: venv, `run.bat`, servicio con NSSM o tarea programada al arranque.
- Variables: `APP_HOST`, `APP_PORT`, `DB_PATH`, `UPLOAD_DIR`, `TIMEZONE`, `TRUSTED_PROXIES`,
  `TLS_CERT`, `TLS_KEY`, `SESSION_HOURS`, `MAX_UPLOAD_MB`.
- README con: instalación, creación del superadmin, abrir el puerto en el firewall, copia de
  seguridad, actualización y qué hacer si se pierde la contraseña del superadmin (comando de
  rescate en el servidor).

## 14. Pruebas

Automáticas (pytest):

- Todas las rutas de admin devuelven redirección/401 sin sesión, incluida `/api/admin/*`.
- Un usuario no ve incidencias de otro aunque conozca el código.
- Secuencia de códigos correcta y sin duplicados con envíos simultáneos.
- Responder a una resuelta la reabre y crea evento `reopen`.
- Responder sin asignar asigna al admin que responde.
- No se puede archivar el último departamento/tipo activo.
- Adjunto con extensión falsa o > 5 MB se rechaza.
- CSRF ausente se rechaza.
- Un admin normal no puede entrar en cuentas; un superadmin sí.
- No se puede desactivar al último superadmin.
- `X-Forwarded-For` se ignora si la petición no viene de un proxy de confianza.
- Renombrar a un requester no cambia el nombre congelado en sus incidencias antiguas, salvo que se
  marque "aplicar al historial".
- Los contadores de aviso del admin solo cuentan mensajes de usuario posteriores a su última
  lectura y solo en las incidencias asignadas a él.
- Las transiciones de estado permitidas son las de la tabla 8.3.1; `nueva` no es seleccionable.

Manual: recorrido completo con dos navegadores (usuario y admin), reapertura, aviso de respuesta,
exportación CSV abierta en Excel y reinicio del servicio sin perder datos.

## 15. Decisiones que he tomado yo

1. Cuatro estados: nueva, en curso, en espera de usuario, resuelta. No hay "cerrada" separada.
2. Responder a una resuelta la reabre (elegido por el usuario).
3. Al responder una incidencia sin asignar, se asigna automáticamente a quien responde.
4. Un requester por navegador (un usuario por PC). Sin contraseña no hay recuperación si se borran
   las cookies, y un PC compartido rompe el aislamiento: queda fuera de alcance.
5. Las urgencias son fijas (baja, normal, alta, urgente); no se gestionan como catálogo.
6. Los catálogos los pueden tocar todos los admins; las cuentas de admin, solo el superadmin.
7. Avisos por sondeo cada 30 s en la web (contador, punto rojo y título de pestaña). Sin correo,
   push ni notificaciones del navegador, porque no hay HTTPS.
8. Hasta 3 adjuntos por mensaje y 5 MB cada uno.
9. Búsqueda simple con `LIKE` (no ignora acentos).
10. Exportación CSV y copia de seguridad por comando, sin interfaz de informes.
11. Un solo proceso Uvicorn y SQLite; si algún día crece, se cambia a PostgreSQL sin tocar la
    interfaz.
12. La primera cuenta se crea solo por comando en el servidor, nunca por web.
13. El nombre y el departamento se congelan en cada incidencia; el admin puede corregir el perfil y,
    si quiere, el historial.
14. Varios superadmins posibles; siempre debe quedar uno activo.
15. Los catálogos solo se archivan, nunca se borran.
