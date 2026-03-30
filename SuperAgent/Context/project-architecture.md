# Архитектура проекта — RDPProxy v2 (подробная)

## 1) Архитектурный обзор

`RDPProxy v2` построен как набор изолированных сервисов в Docker, объединенных bridge-сетью `rdpproxy`.
Единственная внешняя точка входа — контейнер `haproxy`, который:
- принимает весь публичный трафик на `8443`;
- делит RDP и HTTPS на L4-уровне;
- проксирует админ-панель на `9090` только через LAN интерфейс.

Ключевая цель архитектуры: сохранить функциональность v1 и добавить масштабируемость/наблюдаемость/расширяемость.

## 2) Логическая диаграмма потоков

```
Internet Client
   │
   ├── HTTPS / RDP ─────► HAProxy :8443
   │                       ├── HTTPS ► Portal :8001 (L7, XFF/X-Real-IP)
   │                       └── RDP   ► RDP Relay :8002 (L4, Proxy Protocol v2)
   │
LAN Admin
   └── HTTP ─────────────► HAProxy :9090 ► Admin :9090

Portal/Admin/Relay/Metrics ───► PostgreSQL
Portal/Admin/Relay/Metrics ───► Redis
RDP Relay ─────────────────────► Target RDP Servers in LAN (3389/tcp)
```

## 3) Физическая/файловая структура

### 3.1 Корень проекта

```
/opt/rdpproxy-v2/
├── assets/
│   └── images/
│       └── ReceiverFullScreenBackground.jpg   # локальная копия фона страницы входа ADC
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── alembic.ini
├── config.yaml.example
├── config.yaml                # локальный runtime, gitignored
├── .env.example
├── .env                       # локальный runtime, gitignored
├── README.md
├── styleguide.md              # детальный стайлгайд по дизайну ADC/Citrix Gateway
├── deploy/
└── src/
```

Примечание по сборке контейнеров:
- `Dockerfile` включает `COPY assets/ ./assets/`, чтобы статические ассеты (например фон логина) были доступны внутри `portal` контейнера по пути `/app/assets`.

### 3.2 Shared libs (`src/libs`)

- `config/loader.py`: Pydantic-модель всего `config.yaml`.
- `db/engine.py`: async engine/session factory (`create_engine`, `create_sessionmaker`, `build_session_factory`).
- `db/models/*`: предметные сущности:
  - `RdpServer`, `RdpTemplate`
  - `ConnectionHistory`, `ConnectionEvent`
  - `PortalSetting`, `AdGroupCache`
  - `AdminUser`, `AdminAuditLog`
  - `ClusterNode` (состояние нод кластера)
- `db/migrations/*`: Alembic environment и миграции.
- `redis_store/client.py`: фабрика Redis-клиента.
- `redis_store/sessions.py`: web/admin/rdp session lifecycle + fingerprint checks.
- `redis_store/encryption.py`: AES-256-GCM helper.
- `redis_store/active_tracker.py`: трекинг активных сессий (Redis + PostgreSQL).
- `identity/ldap_auth.py`: LDAP/AD auth, поиск/резолвинг групп, password-change для LDAPS/STARTTLS.
- `rdp/*`: низкоуровневые RDP блоки (TPKT, X.224, MCS patch, CredSSP, RDP file generation).
- `proxy_protocol/parser.py`: parser PP v1/v2 для реального IP.
- `security/*`: Argon2, CSRF, rate-limit.
- `common/*`: structured logging, health helpers, async DNS resolver.

### 3.3 Сервисы (`src/services`)

#### Portal (`services/portal`)
- `app.py`: app factory, middleware stack, роуты.
- `routes/auth.py`: login/logout и LDAP auth flow.
- `routes/servers.py`: листинг доступных серверов и выдача `.rdp`.
- `routes/health.py`: health endpoint.
- `dependencies.py`: DI, session extraction, config/ldap access.
- `middleware/*`: security headers, correlation id, real-ip.
- `templates/login.html`: единый шаблон auth + пользовательского портала:
  - страница входа использует фон `assets/images/ReceiverFullScreenBackground.jpg` с `background-size: cover`, класс `auth-html` на `<html>` и запасной цвет фона; высота вьюпорта через `100dvh` / `-webkit-fill-available` для уменьшения белой полосы на мобильных;
  - после входа портал рендерится на однотонном фоне (`#f9f9f9`) в стиле Citrix Gateway.
- `app.py`: добавлен mount статики `/assets` через `StaticFiles` для выдачи локальных ассетов портала.
- `dependencies.py`: добавлен `get_portal_name()` — чтение `portal.name` из `portal_settings` с дефолтом `DC319`.
- `routes/auth.py` и `routes/servers.py`: в контекст `login.html` прокидывается `portal_name` для динамического `<title>`.
- `templates/login.html` дополнительно:
  - убрана верхняя серая полоса с текстом `RDP Proxy Portal`;
  - добавлена полноширинная полупрозрачная серая полоса (`auth-band`) под формой входа;
  - форма входа перенесена внутрь `auth-band` (без отдельного внешнего блока `section.auth-card`);
  - удален внутренний контейнер `div.auth-form-wrap`; заголовок/форма рендерятся напрямую в `auth-band`;
  - высота `auth-band` синхронизирована с высотой формы входа (`292px`);
  - прозрачность `auth-band` настроена через `background: rgba(63, 54, 67, 0.75)`;
  - вертикальное центрирование формы входа переведено с `position: absolute` на flex-выравнивание в `auth-viewport`, чтобы форма стабильно отображалась на всех экранах;
  - контейнер `auth-band` использует `display: flex` + `justify-content: center` и `min-height: 292px`, чтобы заголовок и поля входа были строго по центру полосы;
  - для строгого центрирования полосы по вертикали относительно окна браузера `auth-band` позиционируется как `position: fixed` с `top: 50%` и `transform: translateY(-50%)`;
  - `<title>` страницы берется из `portal_name`.
  - авторизованный экран (ПК):
    - верхняя тёмная панель (`portal-topbar-main`): слева `portal_name`, по центру меню (`Рабочие столы`), справа переключатель темы + имя пользователя + `Выход`;
    - под topbar — `portal-subbar` с полем поиска справа;
    - плитки рабочих столов: `/assets/images/Desktop.png`, клик по плитке ведёт на `/rdp/<id>`;
    - поиск фильтрует плитки по началу названия (`startsWith`, без учёта регистра).
  - авторизованный экран (мобильный, `max-width: 768px`):
    - меню в боковом выезжающем drawer слева (бургер); в drawer — те же пункты навигации, внизу логин и «Выйти»; оверлей по клику закрывает меню;
    - в шапке по центру остаётся активный раздел («Рабочие столы»); справа — кнопка темы и иконка поиска (поле поиска в subbar скрыто);
    - по тапу на поиск шапка переключается в режим полноширинного поля с кнопкой «Отмена»; значение синхронизируется с полем поиска на ПК;
    - `Escape` закрывает drawer и режим поиска.

#### Admin Settings (`services/admin/routes/settings.py` + `templates/admin_settings.html`)
- Добавлен новый раздел настроек `portal` с полем **Наименование портала** (`portal.name`).
- При отсутствии записи в БД используется дефолт `DC319`.

#### Admin (`services/admin`)
- `app.py`: app factory + HTML endpoints.
- `routes/auth.py`: admin login/logout/change password.
- `routes/servers.py`, `templates.py`: CRUD серверов и шаблонов.
- `routes/sessions.py`: активные/исторические сессии, kill.
- `routes/admin_users.py`: управление локальными админ-аккаунтами.
- `routes/ad_groups.py`: резолвинг/обновление AD-групп.
- `routes/settings.py`: системные настройки.
- `routes/stats.py`: агрегированные метрики.
- `routes/cluster.py`: обзор нод.
- `routes/services_mgmt.py`: статус сервисов.
- `middleware/audit.py`: аудит мутаций API.

#### RDP Relay (`services/rdp_relay`)
- `main.py`: TCP listener и graceful shutdown.
- `handler.py`: полный lifecycle одной RDP-сессии:
  - optional PPv2 read
  - token extraction
  - X.224 confirm
  - TLS upgrade
  - CredSSP backend auth
  - bidirectional relay
- `relay.py`: двунаправленная передача данных.
- `tcp_utils.py`: keepalive/abort helpers.
- `relay.py`: логика остановки изменена на `FIRST_COMPLETED` (если одна нога закрылась, принудительно закрываются обе стороны и сессия корректно финализируется).
- `plugins/base.py`: контракт плагинов.
- `plugins/registry.py`: chain dispatcher.
- `plugins/mcs_patch.py`: MCS patch plugin.
- `plugins/session_monitor.py`: session activity/idle monitor.

#### Metrics (`services/metrics`)
- `collector.py`: psutil snapshot -> Redis latest/series + PostgreSQL heartbeat upsert.
- `main.py`: цикл сбора с graceful shutdown.

### 3.4 Инфраструктура (`deploy`)

- `haproxy/haproxy.cfg`: ingress правила.
- `haproxy/certs/rdp.pem`: runtime cert bundle (не коммитится).
- `nftables/rules.nft`: ограничение доступа к `9090`.
- `scripts/gen-dev-cert.sh`: dev-сертификат.
- `scripts/pg-backup.sh`: backup PostgreSQL.
- `scripts/renew-cert.sh`: сборка LE cert bundle + reload haproxy.

## 4) Схема зависимостей между модулями

```
services.portal
  ├── libs.config
  ├── libs.identity.ldap_auth
  ├── libs.redis_store.sessions
  ├── libs.db.models + libs.db.engine
  ├── libs.rdp.rdp_file
  └── libs.security.*

services.admin
  ├── libs.config
  ├── libs.identity.ldap_auth
  ├── libs.redis_store.sessions + active_tracker
  ├── libs.db.models + libs.db.engine
  ├── libs.rdp.rdp_file
  └── libs.security.*

services.rdp_relay
  ├── libs.config
  ├── libs.rdp.(tpkt/x224/mcs/credssp)
  ├── libs.proxy_protocol.parser
  ├── libs.redis_store.sessions + active_tracker
  ├── libs.db.engine + models.history
  ├── libs.common.dns_resolver
  └── plugins.*

services.metrics
  ├── libs.config
  ├── libs.db.models.node + engine
  └── libs.redis_store.client
```

## 5) Потоки данных (детально)

### 5.1 Login + выдача `.rdp`
1. `portal/auth.py` принимает форму логина.
2. LDAP bind/search проверяется через `libs.identity.ldap_auth`.
3. Web-session пишется в Redis (`rdp:web:*`).
4. При выборе сервера формируется RDP token session (`rdp:token:*`).
5. Пользователь скачивает `.rdp`, где указан внешний host/port и токен.

### 5.2 RDP-соединение
1. Клиент идет на `8443`; HAProxy определяет RDP-трафик.
2. HAProxy направляет в relay и добавляет PPv2.
3. Relay читает PPv2, извлекает токен из X.224, валидирует Redis session.
4. Relay отправляет X.224 CC + поднимает TLS.
5. Relay выполняет CredSSP к целевому RDP backend.
6. Включается двусторонний прокси (плагины client/backend packet hooks).
7. Метаданные сессии пишутся в Redis + PostgreSQL history/events.

### 5.3 Admin monitoring
1. Metrics сервис публикует heartbeat.
2. Admin читает cluster/status данные из PostgreSQL/Redis.
3. Admin может завершать сессии через kill-ключ в Redis.

## 6) Как проект отражает требования v1 + v2

- **v1 функционал не потерян**: LDAP login, `.rdp`, CredSSP relay, admin CRUD, session tracking.
- **v2 дополнения реализованы**:
  - all-in-docker;
  - L4 mux на `8443`;
  - PPv2 для RDP;
  - LAN-only admin;
  - metrics + cluster awareness;
  - plugin-based extensibility.

## 7) Точки расширения (важно для AI-агента)

### 7.1 Добавление новой RDP-фичи
- Создать новый плагин в `services/rdp_relay/plugins/`.
- Реализовать нужные hooks (`on_client_packet`, `on_backend_packet`, etc.).
- Зарегистрировать в `services/rdp_relay/main.py`.
- Не менять `handler.py` без крайней необходимости.

### 7.2 Добавление новой админ-функции
- Добавить отдельный route модуль в `services/admin/routes/`.
- Подключить роутер в `services/admin/app.py`.
- При необходимости: новая модель + миграция Alembic.

### 7.3 Добавление новой бизнес-сущности
- Новая модель в `libs/db/models/`.
- Экспорт в `models/__init__.py`.
- Миграция в `libs/db/migrations/versions/`.

## 8) Операционные риски и known pitfalls

- Неверный LDAP endpoint/credential в `config.yaml` вызывает login fail (частый кейс).
- Если HAProxy стартует раньше сервисов, может временно дать `503`; лечится health checks/restart.
- HSTS + неправильный сертификат блокируют доступ к порталу в браузере.
- Нельзя коммитить runtime `config.yaml`, `.env`, сертификаты и приватные ключи.

## 9) Мини-чеклист перед изменениями

1. Проверить `docker compose ps`.
2. Проверить `https://<host>:8443/health`.
3. Проверить `http://<LAN_IP>:9090/admin/login`.
4. Проверить, что LDAP доступен из контейнера portal (`socket/ldap bind test`).
5. Только после этого изменять код.

## 10) Debug runtime observations

- `rdp-relay` запускается из docker image (код не смонтирован как bind-mount), поэтому изменения Python-кода для диагностики требуют `docker compose up -d --build rdp-relay`.
