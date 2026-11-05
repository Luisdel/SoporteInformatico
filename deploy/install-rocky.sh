#!/usr/bin/env bash
# Instalación automatizada en Rocky Linux 9/10 (también RHEL compatible).
#
# Uso, desde el repositorio clonado:
#   sudo DOMAIN=incidencias.midominio.com bash deploy/install-rocky.sh
#
# Variables opcionales:
#   APP_DIR   ruta de instalación (por defecto /opt/incidencias)
#   APP_USER  usuario del servicio (por defecto incidencias)
#   DOMAIN    dominio para Nginx (por defecto _, solo HTTP)
#
# No sobrescribe .env ni data/ si ya existen. Revísalo antes de ejecutarlo.

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/incidencias}"
APP_USER="${APP_USER:-incidencias}"
DOMAIN="${DOMAIN:-_}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "Ejecuta el script con sudo."
[[ -f "${REPO_DIR}/app/main.py" ]] || die "No encuentro app/main.py. Ejecuta el script desde el repositorio."
command -v dnf >/dev/null 2>&1 || die "Este script es para sistemas con dnf (Rocky/RHEL)."

log "Instalando paquetes base"
dnf install -y git nginx firewalld rsync sqlite

log "Buscando Python 3.11 o superior"
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11; do
    if dnf install -y "${candidate}" >/dev/null 2>&1 && command -v "${candidate}" >/dev/null 2>&1; then
        if "${candidate}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
            PYTHON_BIN="${candidate}"
            break
        fi
    fi
done
[[ -n "${PYTHON_BIN}" ]] || die "No hay Python 3.11+ disponible. Instálalo y vuelve a ejecutar."
dnf install -y "${PYTHON_BIN}-pip" >/dev/null 2>&1 || true
log "Usando ${PYTHON_BIN} ($("${PYTHON_BIN}" --version))"

log "Creando usuario y directorio"
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --home-dir "${APP_DIR}" --shell /sbin/nologin "${APP_USER}"
fi
install -d -o "${APP_USER}" -g "${APP_USER}" "${APP_DIR}"

log "Copiando aplicación a ${APP_DIR}"
if [[ "${REPO_DIR}" != "${APP_DIR}" ]]; then
    rsync -a --delete \
        --exclude '.git' \
        --exclude '.venv' \
        --exclude '__pycache__' \
        --exclude '.pytest_cache' \
        --exclude 'data' \
        --exclude '.env' \
        "${REPO_DIR}/" "${APP_DIR}/"
fi
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

log "Creando entorno virtual e instalando dependencias"
if [[ ! -x "${APP_DIR}/.venv/bin/python" ]]; then
    sudo -u "${APP_USER}" "${PYTHON_BIN}" -m venv "${APP_DIR}/.venv"
fi
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --upgrade pip
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

log "Configurando .env"
if [[ ! -f "${APP_DIR}/.env" ]]; then
    install -o "${APP_USER}" -g "${APP_USER}" -m 600 \
        "${APP_DIR}/.env.example" "${APP_DIR}/.env"
    sed -i 's|^TRUSTED_PROXIES=.*|TRUSTED_PROXIES=127.0.0.1/32|' "${APP_DIR}/.env"
fi
chown "${APP_USER}:${APP_USER}" "${APP_DIR}/.env"
chmod 600 "${APP_DIR}/.env"
install -d -o "${APP_USER}" -g "${APP_USER}" "${APP_DIR}/data" "${APP_DIR}/data/uploads"

log "Instalando servicio systemd"
sed "s|/opt/incidencias|${APP_DIR}|g" \
    "${APP_DIR}/deploy/incidencias.service" > /etc/systemd/system/incidencias.service
systemctl daemon-reload
systemctl enable incidencias >/dev/null
systemctl restart incidencias

log "Configurando Nginx"
sed -e "s|/opt/incidencias|${APP_DIR}|g" \
    -e "s|server_name _;|server_name ${DOMAIN};|" \
    "${APP_DIR}/deploy/nginx-incidencias.conf" > /etc/nginx/conf.d/incidencias.conf
nginx -t
systemctl enable nginx >/dev/null
systemctl restart nginx

log "Ajustando SELinux y firewall"
if command -v setsebool >/dev/null 2>&1; then
    setsebool -P httpd_can_network_connect 1 || true
fi
systemctl enable firewalld >/dev/null 2>&1 || true
systemctl start firewalld >/dev/null 2>&1 || true
firewall-cmd --permanent --add-service=http >/dev/null 2>&1 || true
firewall-cmd --permanent --add-service=https >/dev/null 2>&1 || true
firewall-cmd --reload >/dev/null 2>&1 || true

sleep 2
if curl -fsS "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
    log "Servicio funcionando correctamente"
else
    printf '\nAVISO: el servicio no responde aún. Revisa: journalctl -u incidencias -n 50\n'
fi

cat <<EOF

====================================================================
Instalación terminada.

Crea el primer administrador:
  cd ${APP_DIR}
  sudo -u ${APP_USER} .venv/bin/python -m app.manage create-admin admin \\
      --display-name "Administrador" --role superadmin

Acceso:
  http://${DOMAIN/#_/TU-SERVIDOR}/

Servicio:
  systemctl status incidencias
  journalctl -u incidencias -f

Si vas a usar HTTPS:
  dnf install -y certbot python3-certbot-nginx
  certbot --nginx -d tu.dominio.com
  sed -i 's/^SECURE_COOKIES=.*/SECURE_COOKIES=1/' ${APP_DIR}/.env
  systemctl restart incidencias
====================================================================
EOF
