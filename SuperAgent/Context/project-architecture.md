# Архитектура проекта — RDPProxy v2

## Структура файлов

```
rdpproxy-v2/
├── src/
│   ├── libs/
│   │   ├── config/loader.py           # Pydantic-валидация config.yaml
│   │   ├── db/
│   │   │   ├── engine.py              # AsyncEngine, session_factory
│   │   │   ├── models/
│   │   │   │   ├── base.py            # SQLAlchemy Base
│   │   │   │   ├── server.py          # RdpServer, ServerGroupBinding
│   │   │   │   ├── template.py        # RdpTemplate, TemplateGroupBinding
│   │   │   │   ├── history.py         # ConnectionHistory, ConnectionEvent
│   │   │   │   ├── settings.py        # PortalSetting, AdGroupCache
│   │   │   │   ├── admin_user.py      # AdminUser
│   │   │   │   ├── audit.py           # AdminAuditLog
│   │   │   │   ├── node.py            # ClusterNode
│   │   │   │   └── __init__.py        # exports all models
│   │   │   └── migrations/
│   │   │       ├── env.py             # Alembic env (reads config.yaml)
│   │   │       ├── script.py.mako
│   │   │       └── versions/          # Alembic migration scripts
│   │   ├── redis_store/
│   │   │   ├── client.py              # Redis client factory
│   │   │   ├── encryption.py          # AES-256-GCM helpers
│   │   │   ├── sessions.py            # Web/RDP/Admin session management
│   │   │   └── active_tracker.py      # ConnectionTracker (Redis+PG)
│   │   ├── identity/ldap_auth.py      # LDAP authenticator
│   │   ├── rdp/
│   │   │   ├── constants.py           # Protocol constants
│   │   │   ├── tpkt.py               # TPKT frame builder/reader
│   │   │   ├── x224.py               # X.224 CR/CC, token extraction
│   │   │   ├── mcs.py                # MCS patching (SSL↔HYBRID)
│   │   │   ├── credssp.py            # CredSSP/NTLM auth
│   │   │   └── rdp_file.py           # .rdp file builder
│   │   ├── proxy_protocol/parser.py   # PP v1/v2 parser
│   │   ├── security/
│   │   │   ├── passwords.py           # Argon2 hashing
│   │   │   ├── csrf.py               # CSRF tokens
│   │   │   └── rate_limit.py         # Redis rate limiter
│   │   └── common/
│   │       ├── logging.py            # Structured JSON logging
│   │       ├── health.py             # Health check helpers
│   │       └── dns_resolver.py       # Async DNS with cache
│   └── services/
│       ├── portal/
│       │   ├── app.py                # FastAPI factory + bootstrap
│       │   ├── main.py               # Uvicorn entry point
│       │   ├── dependencies.py       # DI helpers
│       │   ├── middleware/            # security_headers, correlation_id, real_ip
│       │   ├── routes/               # auth, servers, health
│       │   └── templates/login.html
│       ├── admin/
│       │   ├── app.py                # FastAPI factory + HTML routing
│       │   ├── main.py               # Uvicorn entry point
│       │   ├── dependencies.py       # DI helpers
│       │   ├── middleware/audit.py   # Audit logger
│       │   ├── routes/               # servers, templates, sessions,
│       │   │                         # admin_users, ad_groups, stats,
│       │   │                         # settings, auth, cluster, services_mgmt
│       │   └── templates/            # admin_*.html (all from v1)
│       ├── rdp_relay/
│       │   ├── handler.py            # Full RDP lifecycle handler
│       │   ├── relay.py              # Bidirectional pipe with plugins
│       │   ├── tcp_utils.py          # TCP keepalive, abort
│       │   ├── main.py               # asyncio.start_server entry
│       │   └── plugins/
│       │       ├── base.py           # RdpPlugin + SessionContext
│       │       ├── registry.py       # PluginRegistry dispatch
│       │       ├── mcs_patch.py      # MCS patching plugin
│       │       └── session_monitor.py # Idle timeout plugin
│       └── metrics/
│           ├── collector.py          # psutil + Redis + PG heartbeat
│           └── main.py              # asyncio entry point
├── deploy/
│   ├── haproxy/
│   │   ├── haproxy.cfg              # L4 mux + TLS term + admin
│   │   └── certs/rdp.pem           # TLS cert (dev: self-signed)
│   ├── nftables/rules.nft           # Firewall: 8443 public, 9090 LAN
│   └── scripts/
│       ├── gen-dev-cert.sh          # Self-signed cert generator
│       └── pg-backup.sh            # pg_dump backup script
├── docker-compose.yml               # All 7 services
├── Dockerfile                       # Multi-stage Python image
├── config.yaml                      # Runtime configuration
├── config.yaml.example
├── alembic.ini
├── requirements.txt
├── .env / .env.example
├── .gitignore
└── README.md
```

## Схема зависимостей

```
HAProxy (:8443 public, :9090 LAN)
├──[TLS + HTTP]──► Portal (:8001)
│                  ├── libs/config
│                  ├── libs/db (models, engine)
│                  ├── libs/redis_store (sessions)
│                  ├── libs/identity (LDAP)
│                  ├── libs/rdp (rdp_file)
│                  └── libs/security (csrf, rate_limit)
├──[TCP + PP v2]──► RDP Relay (:8002)
│                   ├── libs/config
│                   ├── libs/db (engine, history)
│                   ├── libs/redis_store (sessions, tracker)
│                   ├── libs/rdp (tpkt, x224, mcs, credssp)
│                   ├── libs/proxy_protocol
│                   ├── libs/common (dns_resolver)
│                   └── plugins/ (mcs_patch, session_monitor)
└──[HTTP]─────────► Admin (:9090)
                    ├── libs/config
                    ├── libs/db (all models)
                    ├── libs/redis_store (sessions, tracker)
                    ├── libs/identity (LDAP)
                    └── libs/security (passwords, csrf)

Metrics (background)
├── libs/config
├── libs/db (ClusterNode)
└── libs/redis_store (heartbeat)

PostgreSQL ◄── all services (SQLAlchemy async)
Redis      ◄── all services (sessions, metrics, heartbeats)
```

## Описание модулей

- **Portal**: Веб-портал для пользователей. LDAP-авторизация, список серверов по AD-группам, генерация .rdp файлов с токенами.
- **Admin**: Админ-панель. CRUD серверов/шаблонов, управление сессиями, админ-пользователи, мониторинг кластера, настройки.
- **RDP Relay**: TCP-сервер, принимает RDP подключения. Proxy Protocol v2 для реального IP, X.224 → TLS → CredSSP → bidirectional relay с плагинами.
- **Metrics**: Фоновый сборщик метрик (psutil). Публикует в Redis (real-time) и PostgreSQL (cluster_nodes heartbeat).
- **HAProxy**: L4 мультиплексор на порту 8443 (RDP vs HTTPS по первому байту), TLS терминация для портала, PP v2 для RDP relay.
- **Shared libs**: Общий код между сервисами — конфигурация, БД, Redis, LDAP, RDP-протокол, безопасность.
