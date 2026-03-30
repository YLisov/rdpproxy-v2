# Лог итераций проекта

---
## Итерация #1
**Дата**: 2026-03-30
**Запрос**: Портирование admin API-модулей из rdpproxy v1 в rdpproxy-v2.

### Действие 1.1
**Описание**: Добавлены файлы в `src/services/admin/routes/`: servers, templates, sessions, admin_users, ad_groups, stats, settings. Импорты обновлены под v2 shared libs.

---
## Итерация #2
**Дата**: 2026-03-30
**Запрос**: Фаза 2 — Portal + Admin сервисы: app.py, main.py, middleware, routes, templates.

### Действие 2.1
Созданы Portal service: `app.py` (FastAPI factory), `main.py`, `dependencies.py`, middleware (security_headers, correlation_id, real_ip), routes (auth, servers, health).

### Действие 2.2
Созданы Admin service: `app.py`, `main.py`, `dependencies.py`, middleware (audit), routes (auth, cluster, services_mgmt).

### Действие 2.3
Скопированы HTML-шаблоны из v1 (login.html → portal, admin_*.html → admin).

### Действие 2.4
Исправлен `TemplateResponse` API (Starlette 1.0.0): `TemplateResponse(request, name, context)`.

### Действие 2.5
Docker compose build + up → portal (8001) и admin (9090) работают, health check OK.

---
## Итерация #3
**Дата**: 2026-03-30
**Запрос**: Фаза 3 — RDP Relay сервис.

### Действие 3.1
Созданы: `tcp_utils.py` (keepalive, abort), `plugins/base.py` (RdpPlugin, SessionContext), `plugins/registry.py` (PluginRegistry), `plugins/mcs_patch.py` (McsPatchPlugin), `plugins/session_monitor.py` (SessionMonitorPlugin).

### Действие 3.2
Создан `relay.py`: bidirectional pipe с хуками on_client_packet / on_backend_packet.

### Действие 3.3
Создан `handler.py`: полный lifecycle — PP v2 → X.224 → TLS → CredSSP → relay + tracking.

### Действие 3.4
Создан `main.py`: asyncio TCP server с graceful shutdown.

### Действие 3.5
Добавлена `build_session_factory()` в `db/engine.py`.

### Действие 3.6
Docker build + up → RDP Relay слушает на :8002, оба плагина зарегистрированы.

---
## Итерация #4
**Дата**: 2026-03-30
**Запрос**: Фаза 4 — HAProxy конфигурация + nftables.

### Действие 4.1
Создана HAProxy конфигурация (`deploy/haproxy/haproxy.cfg`):
- ft_mux (:8443) — L4 мультиплексер по первому байту (0x03=RDP, 0x16=TLS)
- bk_rdp → rdp-relay:8002 с send-proxy-v2
- ft_portal_https (127.0.0.1:8444) — TLS терминация → bk_portal (portal:8001)
- ft_admin (:9090) → bk_admin (admin:9090) с X-Forwarded-For

### Действие 4.2
Исправлен `req.peek` → `req.payload` (HAProxy 2.9), путь сертификата `/usr/local/etc/haproxy/certs/rdp.pem`.

### Действие 4.3
Создан `deploy/scripts/gen-dev-cert.sh` — генерация self-signed сертификата для dev.

### Действие 4.4
Созданы nftables правила (`deploy/nftables/rules.nft`): 8443 public, 9090 LAN-only.

### Действие 4.5
HAProxy запущен: `Loading success`. Portal health через HTTPS OK, admin через LAN IP OK.

---
## Итерация #5
**Дата**: 2026-03-30
**Запрос**: Фаза 5 — Metrics collector.

### Действие 5.1
Создан `services/metrics/collector.py`: psutil snapshot (CPU, RAM, disk), Redis publish (latest, series, heartbeat), PostgreSQL upsert (cluster_nodes).

### Действие 5.2
Создан `services/metrics/main.py`: asyncio event loop с graceful shutdown.

### Действие 5.3
Docker build + up → метрики пишутся в Redis и PostgreSQL. `cluster_nodes` содержит node-1.

---
## Итерация #6
**Дата**: 2026-03-30
**Запрос**: Фаза 6 — Стабилизация.

### Действие 6.1
Обновлён `docker-compose.yml`: healthchecks для portal и admin, HAProxy ждёт healthy перед стартом.

### Действие 6.2
Создан `deploy/scripts/pg-backup.sh` — pg_dump → gzip с ротацией.

### Действие 6.3
Создан `README.md` с архитектурой, инструкциями, plugin system, backup, firewall.

### Действие 6.4
Все 7 контейнеров запущены и работают: postgres (healthy), redis (healthy), portal (healthy), admin (healthy), rdp-relay, metrics, haproxy.
