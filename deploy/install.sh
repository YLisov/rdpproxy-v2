#!/usr/bin/env bash
set -euo pipefail

# ─── Hardcoded repo URL ─────────────────────────────────────────────
REPO_URL="https://github.com/YLisov/rdpproxy.git"
INSTALL_DIR="/opt/rdpproxy"

# ─── Colors ─────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

step_num=0
step() { step_num=$((step_num + 1)); printf "\n${CYAN}[%d] %s${NC}\n" "$step_num" "$1"; }
info()  { printf "${GREEN}  ✓ %s${NC}\n" "$1"; }
warn()  { printf "${YELLOW}  ⚠ %s${NC}\n" "$1"; }
fail()  { printf "${RED}  ✗ %s${NC}\n" "$1"; exit 1; }

# ═════════════════════════════════════════════════════════════════════
#  i18n
# ═════════════════════════════════════════════════════════════════════

setup_i18n() {
  case "${LANG_CHOICE}" in
    2)
      MSG_WELCOME="Установщик RDPProxy"
      MSG_CHECK_ROOT="Проверка прав root..."
      MSG_NOT_ROOT="Запустите скрипт от root: sudo bash install.sh"
      MSG_CHECK_OS="Проверка операционной системы..."
      MSG_UNSUPPORTED_OS="Поддерживаются только дистрибутивы с apt (Ubuntu, Debian)."
      MSG_UPDATE_SYS="Обновление системных пакетов..."
      MSG_UPDATE_LIST="Обновление списка пакетов..."
      MSG_UPGRADE="Обновление установленных пакетов..."
      MSG_INSTALL_DEPS="Установка зависимостей..."
      MSG_INSTALL_DOCKER="Установка Docker..."
      MSG_DOCKER_OK="Docker уже установлен"
      MSG_CLONE="Клонирование репозитория..."
      MSG_CLONE_EXISTS="Репозиторий уже существует, работаем на месте"
      MSG_DIALOG_HEADER="Настройка параметров"
      MSG_NODEID="Node ID (Enter — сгенерировать случайный):"
      MSG_DBPASS="Пароль базы данных (Enter — сгенерировать):"
      MSG_REDISPASS="Пароль Redis (Enter — сгенерировать):"
      MSG_GEN_SECRETS="Генерация секретов..."
      MSG_WRITE_ENV="Создание .env..."
      MSG_WRITE_CONFIG="Создание config.yaml..."
      MSG_SYSCTL="Настройка параметров ядра (TCP/BBR)..."
      MSG_SYSTEMD="Создание systemd-юнита..."
      MSG_BUILD="Сборка Docker-образов..."
      MSG_CERTS_DIR="Каталог сертификатов (права для ACME в admin)..."
      MSG_START="Запуск сервисов..."
      MSG_WAIT_HEALTH="Ожидание готовности сервисов..."
      MSG_CREATE_ADMIN="Создание администратора (admin/admin)..."
      MSG_DONE="Установка завершена!"
      MSG_ADMIN_URL="Панель администратора:"
      MSG_CREDS="Логин: admin / Пароль: admin"
      MSG_CHANGE_PASS="(система попросит сменить пароль при первом входе)"
      MSG_SECRETS_AT="Секреты сохранены в:"
      MSG_NEXT_STEP="Следующий шаг: войдите в админку → Настройки → укажите домен."
      MSG_NEXT_STEP2="Сертификат Let's Encrypt будет получен автоматически."
      MSG_NEXT_STEP3="Затем выполните: docker compose up -d"
      MSG_REBOOT_HINT="Для применения обновлений ядра может потребоваться перезагрузка."
      MSG_HEALTH_FAIL="Сервис %s не поднялся за отведённое время."
      MSG_STOP_PREV="Обнаружены контейнеры от предыдущего запуска — останавливаю..."
      ;;
    *)
      MSG_WELCOME="RDPProxy Installer"
      MSG_CHECK_ROOT="Checking root privileges..."
      MSG_NOT_ROOT="Run as root: sudo bash install.sh"
      MSG_CHECK_OS="Checking operating system..."
      MSG_UNSUPPORTED_OS="Only apt-based distros (Ubuntu, Debian) are supported."
      MSG_UPDATE_SYS="Updating system packages..."
      MSG_UPDATE_LIST="Updating package lists..."
      MSG_UPGRADE="Upgrading installed packages..."
      MSG_INSTALL_DEPS="Installing dependencies..."
      MSG_INSTALL_DOCKER="Installing Docker..."
      MSG_DOCKER_OK="Docker is already installed"
      MSG_CLONE="Cloning repository..."
      MSG_CLONE_EXISTS="Repository already present, using local copy"
      MSG_DIALOG_HEADER="Configuration"
      MSG_NODEID="Node ID (Enter to generate random):"
      MSG_DBPASS="Database password (Enter to generate):"
      MSG_REDISPASS="Redis password (Enter to generate):"
      MSG_GEN_SECRETS="Generating secrets..."
      MSG_WRITE_ENV="Creating .env..."
      MSG_WRITE_CONFIG="Creating config.yaml..."
      MSG_SYSCTL="Configuring kernel parameters (TCP/BBR)..."
      MSG_SYSTEMD="Creating systemd unit..."
      MSG_BUILD="Building Docker images..."
      MSG_CERTS_DIR="TLS certificate directory (permissions for ACME in admin)..."
      MSG_START="Starting services..."
      MSG_WAIT_HEALTH="Waiting for services to become healthy..."
      MSG_CREATE_ADMIN="Creating admin user (admin/admin)..."
      MSG_DONE="Installation complete!"
      MSG_ADMIN_URL="Admin panel:"
      MSG_CREDS="Login: admin / Password: admin"
      MSG_CHANGE_PASS="(you will be asked to change password on first login)"
      MSG_SECRETS_AT="Secrets saved to:"
      MSG_NEXT_STEP="Next step: log into admin panel → Settings → set your domain."
      MSG_NEXT_STEP2="A Let's Encrypt certificate will be obtained automatically."
      MSG_NEXT_STEP3="Then run: docker compose up -d"
      MSG_REBOOT_HINT="A reboot may be required to apply kernel updates."
      MSG_HEALTH_FAIL="Service %s did not become healthy in time."
      MSG_STOP_PREV="Found containers from a previous run — stopping..."
      ;;
  esac
}

# ═════════════════════════════════════════════════════════════════════
#  Language selection (before anything else)
# ═════════════════════════════════════════════════════════════════════

echo ""
echo "Select language / Выберите язык:"
echo "  1) English"
echo "  2) Русский"
read -rp "> " LANG_CHOICE < /dev/tty
LANG_CHOICE="${LANG_CHOICE:-1}"
setup_i18n

printf "\n${BOLD}══════════════════════════════════════════════════${NC}\n"
printf "${BOLD}  %s${NC}\n" "$MSG_WELCOME"
printf "${BOLD}══════════════════════════════════════════════════${NC}\n"

# ═════════════════════════════════════════════════════════════════════
#  1. Check root
# ═════════════════════════════════════════════════════════════════════

step "$MSG_CHECK_ROOT"
[ "$(id -u)" -eq 0 ] || fail "$MSG_NOT_ROOT"
info "root OK"

# ═════════════════════════════════════════════════════════════════════
#  2. Check OS (apt-based)
# ═════════════════════════════════════════════════════════════════════

step "$MSG_CHECK_OS"
command -v apt-get >/dev/null 2>&1 || fail "$MSG_UNSUPPORTED_OS"
info "$(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-Linux}" || echo "Linux")"

# ═════════════════════════════════════════════════════════════════════
#  3. System update
# ═════════════════════════════════════════════════════════════════════

step "$MSG_UPDATE_SYS"
export DEBIAN_FRONTEND=noninteractive
info "$MSG_UPDATE_LIST"
apt-get update -y -qq < /dev/null
info "$MSG_UPGRADE"
apt-get upgrade -y -qq < /dev/null

# ═════════════════════════════════════════════════════════════════════
#  4. Install dependencies
# ═════════════════════════════════════════════════════════════════════

step "$MSG_INSTALL_DEPS"
apt-get install -y -qq git curl openssl ca-certificates < /dev/null >/dev/null
info "git, curl, openssl"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  info "$MSG_DOCKER_OK ($(docker --version | cut -d' ' -f3 | tr -d ','))"
else
  info "$MSG_INSTALL_DOCKER"
  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  sh /tmp/get-docker.sh < /dev/null
  rm -f /tmp/get-docker.sh
  systemctl enable --now docker
  info "Docker $(docker --version | cut -d' ' -f3 | tr -d ',')"
fi

# ═════════════════════════════════════════════════════════════════════
#  5. Get source code
# ═════════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/../docker-compose.yml" ]; then
  PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
  info "$MSG_CLONE_EXISTS ($PROJECT_DIR)"
elif [ -f "${INSTALL_DIR}/docker-compose.yml" ]; then
  PROJECT_DIR="${INSTALL_DIR}"
  info "$MSG_CLONE_EXISTS ($PROJECT_DIR)"
else
  step "$MSG_CLONE"
  git clone "$REPO_URL" "$INSTALL_DIR" < /dev/null
  PROJECT_DIR="$INSTALL_DIR"
  info "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

# ═════════════════════════════════════════════════════════════════════
#  6. Interactive dialog
# ═════════════════════════════════════════════════════════════════════

step "$MSG_DIALOG_HEADER"

printf "\n  ${BOLD}%s${NC}\n" "$MSG_NODEID"
read -rp "  > " INPUT_NODEID < /dev/tty
NODE_ID="${INPUT_NODEID:-node-$(openssl rand -hex 4)}"

printf "\n  ${BOLD}%s${NC}\n" "$MSG_DBPASS"
read -rp "  > " INPUT_DBPASS < /dev/tty
DB_PASSWORD="${INPUT_DBPASS:-$(openssl rand -hex 24)}"

printf "\n  ${BOLD}%s${NC}\n" "$MSG_REDISPASS"
read -rp "  > " INPUT_REDISPASS < /dev/tty
REDIS_PASSWORD="${INPUT_REDISPASS:-$(openssl rand -hex 24)}"

ENCRYPTION_KEY="$(openssl rand -hex 32)"
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
LAN_IP="${LAN_IP:-127.0.0.1}"

# ═════════════════════════════════════════════════════════════════════
#  7. Generate .env
# ═════════════════════════════════════════════════════════════════════

step "$MSG_WRITE_ENV"
cat > "${PROJECT_DIR}/.env" <<EOF
DB_PASSWORD=${DB_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
PUBLIC_PORT=443
LAN_IP=${LAN_IP}
HOST_PROJECT_DIR=${PROJECT_DIR}
EOF
chmod 666 "${PROJECT_DIR}/.env"
info ".env"

# ═════════════════════════════════════════════════════════════════════
#  8. Generate config.yaml
# ═════════════════════════════════════════════════════════════════════

step "$MSG_WRITE_CONFIG"
sed \
  -e "s|\"node-1\"|\"${NODE_ID}\"|" \
  -e "s|\"10.120.0.13\"|\"${LAN_IP}\"|" \
  -e "s|rdpproxy:CHANGE_ME@postgres|rdpproxy:${DB_PASSWORD}@postgres|" \
  -e "s|password: \"CHANGE_ME\"|password: \"${REDIS_PASSWORD}\"|" \
  -e "s|\"GENERATE_WITH_openssl_rand_hex_32\"|\"${ENCRYPTION_KEY}\"|" \
  "${PROJECT_DIR}/config.yaml.example" > "${PROJECT_DIR}/config.yaml"
info "config.yaml"

# ═════════════════════════════════════════════════════════════════════
#  9. Sysctl tuning (BBR + TCP buffers)
# ═════════════════════════════════════════════════════════════════════

step "$MSG_SYSCTL"
cat > /etc/sysctl.d/99-rdpproxy.conf <<'SYSCTL'
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
SYSCTL
sysctl --system -q 2>/dev/null || sysctl -p /etc/sysctl.d/99-rdpproxy.conf
info "BBR + TCP buffers"

# ═════════════════════════════════════════════════════════════════════
#  10. systemd unit
# ═════════════════════════════════════════════════════════════════════

step "$MSG_SYSTEMD"
cat > /etc/systemd/system/rdpproxy.service <<EOF
[Unit]
Description=RDPProxy
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${PROJECT_DIR}
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable rdpproxy.service
info "rdpproxy.service"

# ═════════════════════════════════════════════════════════════════════
#  11. Build images
# ═════════════════════════════════════════════════════════════════════

step "$MSG_BUILD"

# Stop containers from a previous run
if docker compose ps -q 2>/dev/null | grep -q .; then
  warn "$MSG_STOP_PREV"
  docker compose down --remove-orphans < /dev/null 2>/dev/null || true
fi

docker compose build --quiet < /dev/null
info "docker compose build"

# ═════════════════════════════════════════════════════════════════════
#  11b. Certificate directory: admin runs as non-root (appuser), must own /app/certs mount
# ═════════════════════════════════════════════════════════════════════

step "$MSG_CERTS_DIR"
mkdir -p "${PROJECT_DIR}/deploy/haproxy/certs"
CERT_UID="$(docker compose run --rm --no-deps -T admin id -u < /dev/null)"
chown -R "${CERT_UID}:${CERT_UID}" "${PROJECT_DIR}/deploy/haproxy/certs"
chmod -R u+rwX "${PROJECT_DIR}/deploy/haproxy/certs"
info "deploy/haproxy/certs (uid ${CERT_UID})"

# ═════════════════════════════════════════════════════════════════════
#  12. Start minimal stack (postgres + redis + admin)
# ═════════════════════════════════════════════════════════════════════

wait_healthy() {
  local svc="$1" max_wait="${2:-120}" elapsed=0
  while [ $elapsed -lt $max_wait ]; do
    status="$(docker compose ps --format '{{.Health}}' "$svc" 2>/dev/null || true)"
    if [ "$status" = "healthy" ]; then
      info "$svc"
      return 0
    fi
    sleep 3
    elapsed=$((elapsed + 3))
  done
  warn "$(printf "$MSG_HEALTH_FAIL" "$svc")"
  return 1
}

step "$MSG_START"
docker compose up -d postgres redis < /dev/null
info "postgres + redis"

step "$MSG_WAIT_HEALTH"
wait_healthy postgres 60
wait_healthy redis 60

docker compose up -d admin metrics < /dev/null
info "admin + metrics"

step "$MSG_WAIT_HEALTH"
wait_healthy admin 120

# ═════════════════════════════════════════════════════════════════════
#  13. Create admin user
# ═════════════════════════════════════════════════════════════════════

step "$MSG_CREATE_ADMIN"
cat > /tmp/_create_admin.py <<'PYEOF'
import asyncio, uuid, sys, os
sys.path.insert(0, '/app/src/libs')
sys.path.insert(0, '/app/src')
from security.passwords import hash_password
import asyncpg

async def main():
    db_pass = os.environ["DB_PASSWORD"]
    conn = await asyncpg.connect(f'postgresql://rdpproxy:{db_pass}@postgres:5432/rdpproxy')
    existing = await conn.fetchval(
        "SELECT count(*) FROM admin_users WHERE username = $1", 'admin'
    )
    if existing == 0:
        await conn.execute(
            'INSERT INTO admin_users (id, username, password_hash, must_change_password) '
            'VALUES ($1, $2, $3, true)',
            uuid.uuid4(), 'admin', hash_password('admin'),
        )
    await conn.close()

asyncio.run(main())
PYEOF
docker cp /tmp/_create_admin.py "$(docker compose ps -q admin)":/tmp/_create_admin.py
docker compose exec -T -e DB_PASSWORD="${DB_PASSWORD}" admin python /tmp/_create_admin.py
rm -f /tmp/_create_admin.py
info "admin / admin (must_change_password=true)"

# ═════════════════════════════════════════════════════════════════════
#  14. Summary
# ═════════════════════════════════════════════════════════════════════

printf "\n${BOLD}══════════════════════════════════════════════════${NC}\n"
printf "${GREEN}${BOLD}  %s${NC}\n" "$MSG_DONE"
printf "${BOLD}══════════════════════════════════════════════════${NC}\n\n"

printf "  ${BOLD}%s${NC}\n" "$MSG_ADMIN_URL"
printf "  → ${CYAN}http://%s:9090/admin/settings${NC}\n\n" "$LAN_IP"

printf "  %s\n" "$MSG_CREDS"
printf "  %s\n\n" "$MSG_CHANGE_PASS"

printf "  %s\n" "$MSG_NEXT_STEP"
printf "  %s\n" "$MSG_NEXT_STEP2"
printf "  %s\n\n" "$MSG_NEXT_STEP3"

printf "  %s ${CYAN}%s/.env${NC}\n" "$MSG_SECRETS_AT" "$PROJECT_DIR"
printf "  %s\n" "$MSG_REBOOT_HINT"
printf "\n${BOLD}══════════════════════════════════════════════════${NC}\n"
