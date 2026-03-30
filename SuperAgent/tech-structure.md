# Техническая структура проекта (актуальная, v2)

## 1) Профиль проекта

- **Название**: `rdpproxy-v2`
- **Тип**: backend-платформа (RDP proxy + web portal + admin + monitoring)
- **Архитектура**: микросервисная, контейнерная, модульная
- **Основной язык**: Python 3.12
- **Цель**: безопасный и масштабируемый RDP ingress с AD/LDAP SSO и единым внешним портом

## 2) Платформа и окружение

- **OS (target)**: Ubuntu 24.04 LTS
- **CPU/RAM baseline**: 2 vCPU / 4 GB RAM
- **Disk baseline**: 20 GB (`/` расширен до 20 GB)
- **Container runtime**: Docker 29.x
- **Orchestration (single-node)**: Docker Compose
- **Network model**: Docker bridge (`rdpproxy`), без `network_mode: host`

## 3) Технологический стек

### 3.1 Web/API
- FastAPI
- Uvicorn
- Starlette/Jinja2 templates (portal + admin)

### 3.2 Data/Storage
- PostgreSQL 16 (контейнер)
- Redis 7 (контейнер)
- SQLAlchemy 2.x async
- Alembic (миграции схемы)

### 3.3 Security/Auth
- LDAP/AD auth через `ldap3`
- Argon2 для локальных админ-аккаунтов
- AES-256-GCM для чувствительных значений в Redis
- CSRF + rate-limit / lockout в web-auth потоке

### 3.4 RDP/Network
- TPKT/X.224/MCS/CredSSP стек (переиспользован из v1 + рефакторинг)
- Proxy Protocol v1/v2 parser (для real client IP на relay)
- HAProxy 2.9 (L4 mux + TLS termination + admin proxy)
- nftables (ограничение админ-порта LAN-подсетью)

### 3.5 Observability/Operations
- Structured JSON logging
- Health endpoints/health checks
- Metrics collector (psutil -> Redis + PostgreSQL `cluster_nodes`)
- Backup script (`pg_dump`)

## 4) Сервисная топология

- `haproxy`: внешняя точка входа (`8443`, `9090`)
- `portal`: пользовательский UI/API (`8001`, внутренний)
- `admin`: админ UI/API (`9090`, внутренний backend для haproxy)
- `rdp-relay`: RDP relay (`8002`, внутренний)
- `metrics`: фоновый сборщик метрик/heartbeat
- `postgres`: основная БД
- `redis`: session/cache/heartbeat store

## 5) Сетевые правила

- Публично экспонируется только:
  - `8443/tcp` (RDP + HTTPS через HAProxy)
  - `${LAN_IP}:9090/tcp` (админка, только LAN)
- Внутренние сервисы (`8001`, `8002`, `5432`, `6379`) не публикуются наружу.
- Для HTTP-пути используется `X-Forwarded-For`/`X-Real-IP`.
- Для RDP-пути используется Proxy Protocol v2.

## 6) Конфигурация и секреты

- Основная runtime-конфигурация: `config.yaml` (gitignored)
- Пример конфигурации: `config.yaml.example`
- Переменные окружения: `.env` (gitignored), шаблон `.env.example`
- В git нельзя коммитить:
  - реальные LDAP bind credentials
  - приватные ключи/сертификаты
  - локальные секреты окружения

## 7) Структурные конвенции кода

- Shared-код размещается в `src/libs/*`.
- Сервисы не должны импортировать друг друга напрямую.
- Dependency Injection через `FastAPI Depends` и app state.
- Каждая зона ответственности — отдельным модулем/роутером.
- Для изменений схемы БД — только через Alembic.
- Комментарии в коде: английский; документация проекта: русский.

## 8) Git/релизные правила

- Ветка разработки: `main` (trunk-based).
- Рекомендуемый формат коммитов: `feat|fix|refactor|docs|chore`.
- Перед коммитом обязательны:
  - запуск контейнеров
  - базовые проверки health/login/auth flow
  - проверка отсутствия секретов в индексе git

## 9) Эволюция HA (roadmap)

- Этап 1: single-node (текущий baseline).
- Этап 2: multi-node с общим PostgreSQL/Redis и внешним L4 балансировщиком.
- Этап 3: репликация/failover для PostgreSQL (Patroni) и Redis (Sentinel/Cluster).

## 10) Быстрый технический онбординг AI-агента

1. Прочитать `SuperAgent/project-brief.md`.
2. Прочитать `SuperAgent/Context/project-architecture.md`.
3. Проверить `docker-compose.yml`, `deploy/haproxy/haproxy.cfg`, `config.yaml`.
4. Запустить `docker compose ps` и убедиться, что все сервисы `Up`.
5. Проверить:
   - `https://<host>:8443/health`
   - `http://<LAN_IP>:9090/admin/login`
6. Только после этого вносить изменения по фичам.
