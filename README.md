# RDP-Proxy

[License](LICENSE)

Безопасный шлюз удалённого доступа к серверам по протоколу RDP через веб-портал.

Если проект оказался полезен, поставьте **Star** на GitHub — так о нём проще узнают другие и видно интерес к развитию: [github.com/YLisov/rdpproxy](https://github.com/YLisov/rdpproxy).

## О проекте

RDP-Proxy решает задачу организации централизованного и безопасного удалённого доступа к RDP-серверам компании. Вместо того чтобы открывать порты каждого сервера наружу, администратор разворачивает единую точку входа — RDP-Proxy.

**Как это работает для пользователя:**

1. Сотрудник открывает веб-портал в браузере.
2. Входит под своей доменной учётной записью (Active Directory / LDAP).
3. Видит список доступных ему серверов.
4. Нажимает «Подключиться» — скачивается файл `.rdp`.
5. Открывает файл стандартным RDP-клиентом и работает.

**Как это работает для администратора:**

- Единая точка входа вместо множества открытых портов на целевых машинах.
- Управление серверами и пользователями через админ-панель.
- Мониторинг активных сессий с возможностью принудительного отключения.
- Аутентификация через корпоративный LDAP / Active Directory.
- TLS-шифрование трафика; поддержка Let's Encrypt и автоматического обновления сертификатов (сервис `cert-manager`).
- Возможность масштабирования на несколько нод с общей БД и Redis (в разработке)

## Ключевые возможности

- **Веб-портал** — вход по доменным учётным данным, список серверов, выдача `.rdp`.
- **Админ-панель** — серверы, пользователи, сессии, настройки (LDAP, DNS, безопасность, relay и др.).
- **RDP Relay** — проксирование RDP с поддержкой CredSSP и NLA. Пользователю не нужно повторно вводить логин и пароль при подключении RDP.
- **LDAP/AD** — интеграция с каталогом.
- **TLS** — сертификаты Let's Encrypt.
- **Мониторинг** — метрики и heartbeat нод.
- **Кластер** — добавление нод с уникальным `instance.id` и общими PostgreSQL/Redis.
- **Плагины relay** — расширяемая обработка RDP-трафика (см. раздел «Плагины» ниже).

## Системные требования


| Параметр | Минимум                                                                 |
| -------- | ----------------------------------------------------------------------- |
| ОС       | Ubuntu 20.04+ / Debian 11+                                              |
| CPU      | 2 ядра                                                                  |
| RAM      | 2 ГБ                                                                    |
| Диск     | от ~10 ГБ                                                               |
| Сеть     | для Let's Encrypt — доменное имя и доступность порта **80** с интернета |


## Быстрая установка (одна команда)

Установщик рассчитан на **Ubuntu и Debian** (наличие `apt-get`). Он при необходимости установит Docker, задаст вопросы по домену и секретам, подготовит конфигурацию и запустит стек.

**Скачать и запустить установщик с GitHub:**

```bash
curl -fsSL https://raw.githubusercontent.com/YLisov/rdpproxy/main/deploy/install.sh | sudo bash
```

**Если репозиторий уже есть на сервере:**

```bash
sudo bash /opt/rdpproxy/deploy/install.sh
```

> **Другие ОС** (RHEL, Alpine и т.д.) официально скриптом не поддерживаются: установите зависимости вручную и следуйте разделу «Ручная установка».

## Ручная установка

```bash
# 1. Клонировать репозиторий
sudo git clone https://github.com/YLisov/rdpproxy.git /opt/rdpproxy
cd /opt/rdpproxy

# 2. Файлы окружения
cp .env.example .env
cp config.yaml.example config.yaml
# Отредактируйте .env: DB_PASSWORD, REDIS_PASSWORD, LAN_IP
# Отредактируйте config.yaml: database.url, redis.password, security.encryption_key,
#   proxy.cert_path / key_path, instance.id, instance.lan_ip

# 3. Сертификат TLS
# Вариант A — Let's Encrypt на хосте (пример)
sudo certbot certonly --standalone -d ваш-домен.example
# Укажите пути к fullchain.pem и privkey.pem в config.yaml → proxy

# Вариант B — самоподписанный сертификат для теста
./deploy/scripts/gen-dev-cert.sh

# 4. Сборка и запуск
docker compose build
docker compose up -d

# 5. Миграции БД (пароль из .env должен совпадать с подключением в config.yaml)
set -a && source .env && set +a
docker compose exec -T portal python -c "
import os
from alembic.config import Config
from alembic import command
cfg = Config('alembic.ini')
cfg.set_main_option('sqlalchemy.url', 'postgresql+asyncpg://rdpproxy:' + os.environ['DB_PASSWORD'] + '@postgres:5432/rdpproxy')
command.upgrade(cfg, 'head')
"
```

Первый администратор создаётся автоматически при установке через `install.sh`. При чистой ручной установке создайте пользователя `admin` тем же способом, что в `deploy/install.sh` (блок «Create admin user»), либо выполните установку один раз через скрипт.

## Настройка

### Стартовая конфигурация (`config.yaml`)

В файле задаются параметры, нужные **до** полноценной работы с БД из UI:


| Параметр                       | Назначение                               |
| ------------------------------ | ---------------------------------------- |
| `instance.id`                  | Уникальный идентификатор ноды в кластере |
| `database.url`                 | Подключение к PostgreSQL                 |
| `redis.password`               | Пароль Redis (согласован с `.env`)       |
| `security.encryption_key`      | Ключ шифрования (`openssl rand -hex 32`) |
| `proxy.cert_path` / `key_path` | Пути к сертификату и ключу для HAProxy   |


### Основные настройки — админ-панель

LDAP, DNS, таймауты сессий, параметры прокси и relay и др. настраиваются в **Админ-панель → Settings** и хранятся в БД (`portal_settings`). При первом запуске значения из закомментированных блоков `config.yaml` могут быть перенесены в БД как начальный seed.

## Первый вход


| Интерфейс    | Адрес                              | Назначение             |
| ------------ | ---------------------------------- | ---------------------- |
| Портал       | `https://<домен или LAN_IP>:8443`  | Вход для пользователей |
| Админ-панель | `http://<LAN_IP>:9090/admin/login` | Управление системой    |


**Учётная запись по умолчанию (после установщика):** `admin` / `admin` — **смените пароль** при первом входе.

Рекомендуемые шаги: смена пароля → настройка LDAP/AD → добавление RDP-серверов → проверка входа через портал.

## Управление сервисом

После установки стек обычно управляется unit-файлом `rdpproxy.service` (создаётся установщиком).

```bash
# Статус контейнеров
cd /opt/rdpproxy && docker compose ps

# Остановка / запуск (через systemd)
sudo systemctl stop rdpproxy
sudo systemctl start rdpproxy
sudo systemctl restart rdpproxy

# Или напрямую Compose
docker compose down
docker compose up -d

# Логи
docker compose logs -f
docker compose logs -f portal
```

## Обновление

```bash
cd /opt/rdpproxy
git pull
docker compose build
docker compose up -d
set -a && source .env && set +a
docker compose exec -T portal python -c "
import os
from alembic.config import Config
from alembic import command
cfg = Config('alembic.ini')
cfg.set_main_option('sqlalchemy.url', 'postgresql+asyncpg://rdpproxy:' + os.environ['DB_PASSWORD'] + '@postgres:5432/rdpproxy')
command.upgrade(cfg, 'head')
"
```

## Резервное копирование

```bash
# Разовый дамп PostgreSQL (по умолчанию каталог /opt/rdpproxy/backups)
./deploy/scripts/pg-backup.sh

# Пример cron: ежедневно в 03:00, хранить 7 дней (значение по умолчанию в скрипте)
echo "0 3 * * * /opt/rdpproxy/deploy/scripts/pg-backup.sh" | crontab -
```

Другой срок хранения: `KEEP_DAYS=14 ./deploy/scripts/pg-backup.sh`.

## SSL-сертификаты

```bash
# Продление и сборка bundle для HAProxy (домен можно не указывать — возьмётся из БД)
./deploy/scripts/renew-cert.sh
./deploy/scripts/renew-cert.sh example.com

# Смена домена
./deploy/scripts/change-domain.sh новый-домен.example
```

Для автоматической выдачи Let's Encrypt в стеке используется сервис **cert-manager** (порт **80** должен быть доступен из интернета в момент выпуска/продления).

## Сетевые порты


| Порт     | Доступ                         | Назначение                                            |
| -------- | ------------------------------ | ----------------------------------------------------- |
| **8443** | Обычно публичный               | RDP и HTTPS-портал (мультиплексирование на HAProxy)   |
| **9090** | Рекомендуется только LAN       | Админ-панель (в `docker-compose` привязка к `LAN_IP`) |
| **80**   | Публичный при использовании LE | HTTP-01 для cert-manager                              |


## Архитектура (кратко)

```
                        ┌──────────────┐
         Порт 8443      │              │
  ──────────────────────►   HAProxy    │
  (RDP или HTTPS)       │  L4 mux      │
                        └───┬─────┬────┘
                  RDP       │     │  HTTPS
                ┌───────────┘     └────────────┐
                ▼                              ▼
        ┌──────────────┐              ┌──────────────┐
        │  RDP Relay   │              │   Portal     │
        │  CredSSP+MCS │              │   вход / RDP │
        └──────┬───────┘              └──────┬───────┘
               │                             │
        ┌──────┴─────────────────────────────┴───┐
        │         PostgreSQL  +  Redis            │
        └─────────────────────────────────────────┘

  Порт 9090 (LAN) ──► HAProxy ──► Админ-панель
```


| Сервис           | Роль                            |
| ---------------- | ------------------------------- |
| **portal**       | Веб-портал                      |
| **admin**        | Админ-панель                    |
| **rdp-relay**    | Прокси RDP                      |
| **metrics**      | Метрики и heartbeat             |
| **haproxy**      | Входной балансировщик, TLS, mux |
| **postgres**     | БД                              |
| **redis**        | Сессии, кеш, pub/sub            |
| **cert-manager** | Выпуск/обновление сертификатов  |


Подробнее о модулях и потоках данных — в `SuperAgent/Context/project-architecture.md` (если вы ведёте внутреннюю документацию репозитория).

## Плагины (RDP Relay)

Relay поддерживает плагины преобразования трафика, например:

- **McsPatchPlugin** — правки MCS Connect-Initial для моста SSL↔HYBRID.
- **SessionMonitorPlugin** — учёт активности и лимиты по времени/простою.

Свой плагин: наследуйте `RdpPlugin` и зарегистрируйте в `services/rdp_relay/main.py`.

```python
from services.rdp_relay.plugins.base import RdpPlugin, SessionContext

class MyPlugin(RdpPlugin):
    name = "my_plugin"

    async def on_client_packet(self, data: bytes, ctx: SessionContext) -> bytes:
        return data
```

## Полезные команды


| Команда                                     | Действие               |
| ------------------------------------------- | ---------------------- |
| `docker compose ps`                         | Статус сервисов        |
| `docker compose logs -f <имя>`              | Логи сервиса           |
| `docker compose restart <имя>`              | Перезапуск сервиса     |
| `./deploy/scripts/pg-backup.sh`             | Бэкап БД               |
| `./deploy/scripts/renew-cert.sh`            | Обновление сертификата |
| `./deploy/scripts/change-domain.sh <домен>` | Смена домена           |
| `./deploy/scripts/gen-dev-cert.sh`          | Dev-сертификат         |


## Частые вопросы

**Какие ОС поддерживает установщик?**  
Только дистрибутивы с **apt** (Ubuntu, Debian). На других ОС — ручная установка Docker и шаги из раздела «Ручная установка».

**Можно ли без публичного домена?**  
Да: при пропуске домена установщик может выдать самоподписанный сертификат; браузер покажет предупреждение. Для продакшена лучше домен и Let's Encrypt.

**Как сбросить пароль `admin`?**  
Надёжный способ — через контейнер `admin` и функцию хеширования пароля проекта (`security.passwords`), обновив запись в таблице `admin_users`, либо восстановление из бэкапа БД. Не храните пароли в открытом виде.

**Безопасно ли открывать 8443 в интернет?**  
Трафик терминируется на HAProxy с TLS для HTTPS; для RDP используется контролируемая выдача токенов через портал. Ограничьте **9090** только LAN; настройте политики и мониторинг по политике вашей организации.

## Лицензия и вклад

**Лицензия.** Исходный код этого репозитория распространяется на условиях **[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)** (SPDX: `Apache-2.0`).

**Гарантии.** ПО поставляется **«как есть»** (*as is*), без явных или подразумеваемых гарантий; ответственность за эксплуатацию в вашей инфраструктуре несёт тот, кто её разворачивает.

**Идеи и пожелания.** Предложения по развитию удобно оставлять в [Issues на GitHub](https://github.com/YLisov/rdpproxy/issues): ясный заголовок, описание сценария или проблемы, по возможности версия/ОС и способ установки. Похожие темы лучше связать с уже открытым issue.

**Патчи.** Pull request’ы приветствуются: небольшой объём, понятное описание изменений, без посторонних правок. Крупные изменения разумно сначала обсудить в issue.

**Безопасность.** Уязвимости не раскрывайте публично в issue до исправления; используйте [Security Advisories](https://docs.github.com/code-security/security-advisories) репозитория (если включены) или иной контакт, указанный владельцем проекта.

**Звезда на GitHub.** Если RDP-Proxy вам подошёл, нажмите **Star** в [репозитории](https://github.com/YLisov/rdpproxy) — это простая поддержка проекта и его заметности.