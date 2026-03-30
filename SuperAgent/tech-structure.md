# Техническая структура проекта

## Основные параметры
- **Тип проекта**: Backend (микросервисная RDP-прокси система)
- **Язык**: Python 3.12
- **Фреймворки**: FastAPI, Uvicorn, SQLAlchemy 2.0, Alembic, asyncio

## Среда разработки
- **ОС**: Ubuntu 24.04 LTS
- **Runtime**: Python 3.12, Docker 29.x, Docker Compose 5.x
- **Пакетный менеджер**: pip + requirements.txt

## Git конвенции
- **Формат коммитов**: conventional commits (feat/fix/refactor/docs/chore)
- **Стратегия веток**: trunk-based (main)

## Архитектура
- **Тип**: Микросервисная (Docker containers, единый Dockerfile, bridge network)
- **Сервисы**: Portal, Admin, RDP Relay, Metrics, HAProxy
- **Хранилища**: PostgreSQL 16 (контейнер), Redis 7 (контейнер)

## Настройки агента
- **Режим работы**: Автономный
- **Язык комментариев**: Английский
- **Документация**: Русский
