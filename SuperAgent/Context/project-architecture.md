# Архитектура проекта — RDPProxy (подробная)

## 1) Архитектурный обзор

`RDPProxy` построен как набор изолированных сервисов в Docker, объединенных bridge-сетью `rdpproxy`.
Единственная внешняя точка входа — контейнер `haproxy`, который:
- принимает весь публичный трафик на `8443`;
- делит RDP и HTTPS на L4-уровне;
- проксирует админ-панель на `9090` только через LAN интерфейс.

Ключевая цель архитектуры: масштабируемость, наблюдаемость и расширяемость.

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
/opt/rdpproxy/
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
├── LICENSE                    # Apache License 2.0 (исходный код репозитория)
├── README.md                  # пользовательская документация: назначение продукта, установка, эксплуатация, FAQ
├── deploy/
└── src/
```

Примечание по сборке контейнеров:
- `Dockerfile` включает `COPY assets/ ./assets/`, чтобы статические ассеты (например фон логина) были доступны внутри `portal` контейнера по пути `/app/assets`.

### 3.2 Shared libs (`src/libs`)

- `config/loader.py`: Pydantic-модель всего `config.yaml`. `ldap` сделан optional (`LdapConfig | None`) для поддержки первого запуска без LDAP. Добавлены deprecation warnings для полей, управляемых через БД. `ProxyConfig.secure_cookies`, `RdpRelayConfig.trusted_proxies`, `RdpRelayConfig.max_connections`.
- `config/settings_manager.py`: Центральный класс `SettingsManager` для загрузки, кэширования и обновления настроек из таблицы `portal_settings`. Поддерживает:
  - TTL-кэш (30 сек) с автообновлением
  - Fallback к значениям из YAML
  - Seed при первом запуске: автоперенос из `config.yaml` в БД
  - Шифрование секретов (LDAP bind_password) через `AESEncryptor`
  - Хуки горячей перезагрузки (`on_change()`)
  - Redis pub/sub оповещение других сервисов (`rdp:settings:changed`)
  - Типизированные свойства: `ldap`, `dns`, `proxy_params`, `security_params`, `redis_ttl`, `relay_params`
- `db/engine.py`: async engine/session factory (`create_engine`, `create_sessionmaker`, `build_session_factory`).
- `db/models/*`: предметные сущности:
  - `RdpServer`, `RdpTemplate`
  - `ConnectionHistory`, `ConnectionEvent`
  - `PortalSetting`, `AdGroupCache`
  - `AdminUser`, `AdminAuditLog`
  - `ClusterNode` (состояние нод кластера)
- `db/migrations/*`: Alembic environment и миграции.
- `redis_store/keys.py`: централизованные Redis-ключи, паттерны и TTL для всего приложения. Включает `CONN_TOKEN` — маппинг connection_id→token для удаления токена при admin kill.
- `redis_store/client.py`: фабрика Redis-клиента.
- `redis_store/sessions.py`: web/admin/rdp session lifecycle + fingerprint checks. Атомарные WATCH/pipeline для TOCTOU-безопасности. `AdminWebSessionData` содержит `allowed_ips`.
- `redis_store/encryption.py`: AES-256-GCM helper.
- `redis_store/active_tracker.py`: трекинг активных сессий (Redis + PostgreSQL). Метод `finish()` защищён от перезаписи записей со `status="killed"` (WHERE `status != 'killed'`), чтобы admin kill статус не затирался финализацией handler. Метод `reconcile_stale_active_on_startup()` при рестарте очищает все транзиентные Redis-ключи: `rdp:token:*`, `rdp:conn-token:*`, `rdp:kill:*`, `rdp:web:*`, `rdp:admin:web:*`, `rdp:active:{instance}:*`.
- `identity/ldap_auth.py`: LDAP/AD auth, поиск/резолвинг групп, password-change для LDAPS/STARTTLS. Поддерживает `user_filter` — дополнительный LDAP-фильтр при поиске пользователя (фильтрация по группе, OID `1.2.840.113556.1.4.1941` для вложенных подгрупп).
- `rdp/*`: низкоуровневые RDP блоки (TPKT, X.224, MCS patch, CredSSP, RDP file generation).
- `proxy_protocol/parser.py`: parser PP v1/v2 для реального IP.
- `security/passwords.py`: Argon2 хэширование.
- `security/csrf.py`: CSRF-защита.
- `security/login_limiter.py`: унифицированный rate-limiter для portal и admin логинов (класс `LoginLimiter` + фабрики `portal_limiter`/`admin_limiter`).
- `common/*`: structured logging, health helpers, async DNS resolver.

### 3.3 Сервисы (`src/services`)

#### Portal (`services/portal`)
- `app.py`: app factory, middleware stack, роуты. Интегрирован `SettingsManager` с горячей перезагрузкой (LDAP, TTL). Фоновая задача `_settings_listener` подписана на Redis pub/sub `rdp:settings:changed`.
- `routes/auth.py`: login/logout и LDAP auth flow.
- `routes/servers.py`: листинг доступных серверов и выдача `.rdp`.
- `routes/health.py`: health endpoint.
- `dependencies.py`: DI, session extraction, config/ldap access. Добавлены `get_db_session()`, `get_redis_client()` для устранения дублирования в route-файлах.
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
- `settings.py` полностью переписан для работы через `SettingsManager`: GET читает из менеджера, PUT сохраняет через менеджер с publish в Redis pub/sub. Добавлен endpoint `POST /ldap-test` для проверки LDAP с несохраненными параметрами.
- `admin_settings.html` расширен 8 вкладками: Общие, LDAP, DNS, Безопасность, Сессии, RDP Relay (max_connections, idle_timeout, max_session_duration), Администраторы. У каждой группы — цветная метка "Применяется сразу" (зеленая) или "Требует перезапуска" (оранжевая).

#### Admin (`services/admin`)
- `app.py`: app factory + HTML endpoints. Интегрирован `SettingsManager` с хуками горячей перезагрузки для LDAP, Redis TTL и Portal name. LDAP authenticator создается из DB-настроек при старте.
- `routes/auth.py`: admin login/logout/change password.
- `routes/servers.py`, `templates.py`: CRUD серверов и шаблонов.
- `routes/sessions.py`: активные/исторические сессии, kill. Модель `QualityDetail` (rtt_ms, rtt_var_ms, jitter_ms, retransmits, total_retrans, lost, cwnd, rating) и поле `quality_detail` в `ActiveSessionOut` — данные парсятся из Redis для эндпоинта `GET /api/admin/sessions/active`. При admin kill (`kill_session`, `kill_all_sessions`) помимо установки kill-флага также удаляется RDP-токен из Redis через маппинг `CONN_TOKEN`, чтобы клиент не мог авто-переподключиться.
- `routes/admin_users.py`: управление локальными админ-аккаунтами.
- `routes/ad_groups.py`: резолвинг/обновление AD-групп.
- `routes/settings.py`: системные настройки.
- `routes/stats.py`: агрегированные метрики.
- `routes/cluster.py`: обзор нод.
- `routes/services_mgmt.py`: статус сервисов.
- `middleware/audit.py`: аудит мутаций API.

#### RDP Relay (`services/rdp_relay`)
- `main.py`: TCP listener и graceful shutdown. Интегрирован `SettingsManager` с фоновой задачей `_settings_listener` (Redis pub/sub). DNS resolver и настройки handler обновляются на лету.
- `handler.py`: полный lifecycle одной RDP-сессии. Динамические параметры (token_fingerprint_enforce, delete_token_on_disconnect, ldap.domain) читаются из `SettingsManager`. Proxy Protocol v2 всегда включён (хардкод). Методы `update_dns()` и `update_settings()` для горячей подмены. При старте сессии сохраняет маппинг connection_id→token в Redis (`CONN_TOKEN`). После завершения реле определяет реальную причину (`admin_kill` / `idle_timeout` / `normal`) по анализу `result.legs` и наличию kill-ключа. Опционально удаляет токен при завершении если включена настройка `delete_token_on_disconnect`.
  - optional PPv2 read
  - token extraction + `extract_requested_protocols` из X.224 CR клиента
  - X.224 confirm
  - TLS upgrade
  - CredSSP backend auth (всегда запрашивает `PROTOCOL_HYBRID` 0x03 у backend)
  - bidirectional relay
  - `client_requested_protocols` из X.224 CR сохраняется в `SessionContext.extra` и пробрасывается в плагины для корректного патча MCS-ответа.
  - `client_socket` и `backend_socket` (raw `socket.socket`) передаются в `SessionContext.extra` для плагина `ConnectionQualityPlugin`.
- `relay.py`: двунаправленная передача данных; логика остановки — `FIRST_COMPLETED` (если одна нога закрылась, принудительно закрываются обе стороны). Оптимизации TCP throughput: условный `drain()` (только при переполнении write buffer), увеличенные `READ_CHUNK=128KB`, asyncio write buffer limits `high=512KB/low=64KB`, kill_checker вынесен в отдельную async-задачу `_kill_poller` (sync Redis GET выполняется в thread executor раз в 2 сек, не блокирует event loop).
- `tcp_utils.py`: keepalive/abort helpers + `tune_writer_buffers()` для настройки asyncio transport water marks + увеличение `SO_SNDBUF`/`SO_RCVBUF` до 512KB + включение `TCP_NODELAY`.
- `plugins/base.py`: контракт плагинов.
- `plugins/registry.py`: chain dispatcher.
- `plugins/mcs_patch.py`: MCS patch plugin; считывает `client_requested_protocols` из `ctx.extra` и передаёт в `patch_mcs_server`, чтобы поле `clientRequestedProtocols` в SC_CORE ответе бэкенда соответствовало оригинальному запросу клиента (важно для iPhone / Windows App, которые проверяют точное совпадение).
- `plugins/session_monitor.py`: session activity/idle monitor + абсолютный лимит длительности. Параметры `idle_timeout` и `max_session_duration` обновляются на лету через `update_timeouts()`. `idle_timeout=0` отключает idle check, `max_session_duration=0` — без ограничения.
- `plugins/connection_quality.py`: мониторинг качества TCP-соединения через Linux `TCP_INFO`. Содержит ctypes-структуру `_TcpInfo` (31 поле из `struct tcp_info`), датакласс `QualitySnapshot` (rtt_ms, rtt_var_ms, jitter_ms, retransmits, total_retrans, lost, cwnd, rating). Плагин `ConnectionQualityPlugin` запускает фоновую asyncio-задачу при `on_session_start`, которая каждые 5 секунд читает `TCP_INFO` с обоих сокетов (client + backend), считает суммарный RTT и jitter по скользящему окну 20 замеров, определяет рейтинг (excellent/good/fair/poor) и публикует метрики в Redis-ключ `rdp:active:{instance_id}:{connection_id}`.
- `active_tracker.py` + `rdp_relay/main.py`: при старте relay выполняется `reconcile_stale_active_on_startup()` — закрытие зависших `status=active` сессий (DB+Redis) после рестартов, причина `relay-restart`.

##### Libs: `rdp/x224.py`
- `extract_requested_protocols(x224_payload: bytes) -> int` — извлекает `requestedProtocols` из RDP Negotiation Request (последние 4 байта X.224 CR). Используется в `handler.py`.

##### Libs: `rdp/mcs.py`
- `patch_mcs_server(data, *, client_requested_protocols=None)` — патчит `clientRequestedProtocols` в SC_CORE ответе сервера. Если `client_requested_protocols` передан — ставит его значение, иначе fallback на `PROTOCOL_SSL`.

#### Metrics (`services/metrics`)
- `collector.py`: psutil snapshot -> Redis latest/series + PostgreSQL heartbeat upsert. Сетевые метрики читаются из `/host/proc/1/net/dev` (хостовой network namespace через volume `/proc:/host/proc:ro`).
- `main.py`: цикл сбора с graceful shutdown.

### 3.4 Инфраструктура (`deploy`)

- `haproxy/haproxy.cfg`: ingress правила. Секция `resolvers docker` (127.0.0.11) + `resolvers docker init-addr libc,none` на серверах `portal`/`admin`/`rdp-relay` — пересоздание контейнеров не оставляет HAProxy со старым IP (иначе 503). Frontend `ft_mux`: `timeout client 24h` для long-lived RDP; backend `bk_rdp`: `timeout tunnel 24h`, `timeout server 24h`.
- `haproxy/certs/rdp.pem`: runtime cert bundle (не коммитится).
- `install.sh`: двуязычный (EN/RU) скрипт-установщик для развёртывания на чистом apt-based Linux. Выполняет: apt update/upgrade, установку Docker, клон репо, интерактивную настройку (домен, node-id, пароли), генерацию секретов, выпуск сертификата (Let's Encrypt или self-signed), sysctl-тюнинг, создание systemd-юнита, сборку и запуск контейнеров, Alembic-миграции, создание admin-пользователя.
- `scripts/gen-dev-cert.sh`: dev-сертификат.
- `scripts/pg-backup.sh`: backup PostgreSQL.
- `scripts/renew-cert.sh`: сборка LE cert bundle + reload haproxy + restart rdp-relay. Домен определяется из БД (`portal_settings.proxy.public_host`), можно передать аргументом.
- `scripts/change-domain.sh`: выпуск нового LE-сертификата для указанного домена через certbot standalone + сборка pem + reload. Используется сервисом `cert-manager`.
- `cert-manager/Dockerfile`: образ sidecar-сервиса cert-manager (python + certbot + docker CLI).

### 3.5 Сервис cert-manager (`services/cert_manager`)
- `main.py`: sidecar-процесс, подписан на Redis pub/sub канал `rdp:cert:renew`. При получении сообщения с доменом запускает `change-domain.sh` через subprocess. Graceful shutdown по SIGTERM/SIGINT. Автоматический реконнект к Redis при потере связи.
- Контейнер `cert-manager` в `docker-compose.yml`: порт 80 для certbot HTTP-01 challenge, монтирует `/etc/letsencrypt`, `/var/run/docker.sock`, `./deploy`, конфиги.

## 4) Схема зависимостей между модулями

```
services.portal
  ├── libs.config (loader + settings_manager)
  ├── libs.identity.ldap_auth
  ├── libs.redis_store.sessions
  ├── libs.db.models + libs.db.engine
  ├── libs.rdp.rdp_file
  └── libs.security.*

services.admin
  ├── libs.config (loader + settings_manager)
  ├── libs.identity.ldap_auth
  ├── libs.redis_store.sessions + active_tracker
  ├── libs.db.models + libs.db.engine
  ├── libs.rdp.rdp_file
  └── libs.security.*

services.rdp_relay
  ├── libs.config (loader + settings_manager)
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

services.cert_manager
  ├── libs.config
  ├── libs.common.logging
  └── libs.redis_store.keys
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
1. Metrics сервис публикует heartbeat и метрики (CPU, RAM, SWAP, сеть) в Redis ключи `rdp:metrics:{instance_id}:latest` и `rdp:metrics:{instance_id}:series`.
2. Admin читает cluster/status данные из PostgreSQL/Redis. `stats.py` поддерживает параметр `period` (1h/6h/24h) для серии точек.
3. Admin может завершать сессии через kill-ключ в Redis (одиночные и массовые через `/api/admin/sessions/kill-all`). При admin kill также удаляется RDP-токен, чтобы предотвратить авто-реконнект клиента. В истории сессий admin kill корректно отображается как `status=killed`, `disconnect_reason=admin_kill`.
4. Дашборд отображает виджеты CPU (с load avg), RAM, SWAP, сеть, активные сессии + графики с переключением периода.

## 6) Реализованные возможности

- LDAP login, `.rdp`, CredSSP relay, admin CRUD, session tracking;
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
- `portal_name` передаётся во все шаблоны через `_make_handler` (кэш в `app.state.portal_name_cache`).
- Страница "Администраторы" встроена во вкладку "Настройки" (не отдельная страница).

### 7.3 Добавление новой бизнес-сущности
- Новая модель в `libs/db/models/`.
- Экспорт в `models/__init__.py`.
- Миграция в `libs/db/migrations/versions/`.

## 8) Операционные риски и known pitfalls

- Сервисы `admin` и `metrics` в `docker-compose.yml` монтируют `./src:/app/src:ro` — правки шаблонов и кода видны после пересоздания контейнера; без тома нужен `docker compose build` после каждой правки UI.
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

## 10) TCP throughput оптимизации relay

- `docker-compose.yml`: контейнеры `rdp-relay` и `haproxy` включают `net.ipv4.tcp_congestion_control=bbr`; для `rdp-relay` также заданы `net.ipv4.tcp_rmem/wmem` (default=256KB, max=16MB). На хосте в `/etc/sysctl.conf`: `net.core.rmem_max=16MB`, `net.core.wmem_max=16MB`, `net.core.default_qdisc=fq`, `net.ipv4.tcp_congestion_control=bbr`.
- `tcp_utils.py`: SO_SNDBUF/SO_RCVBUF = 512KB, TCP_NODELAY включён.
- `relay.py`: READ_CHUNK = 128KB, asyncio write buffer high=512KB/low=64KB, drain() вызывается только при переполнении буфера (условный drain). kill_checker вынесен из hot-path в отдельный async-поток с интервалом 2 сек.
- `rdp_file.py`: `networkautodetect:i:0` — отключена попытка UDP multitransport (прокси TCP-only), `connection type:i:6` — LAN hint для клиента.
- `haproxy.cfg`: `resolvers docker`; `ft_mux` — `timeout client 24h`; `bk_rdp` — `timeout tunnel` + `timeout server` 24h; бэкенды с динамическим DNS.

## 11) Debug runtime observations

- `rdp-relay` запускается из docker image (код не смонтирован как bind-mount), поэтому изменения Python-кода для диагностики требуют `docker compose up -d --build rdp-relay`.
