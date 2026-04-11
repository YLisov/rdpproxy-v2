"""Admin service entry point — runs migrations then starts Uvicorn on port 9090."""

from __future__ import annotations

import logging

import uvicorn

from common.logging import setup_logging
from config.loader import load_config
from services.admin.app import create_app

logger = logging.getLogger("rdpproxy.admin")


def _run_migrations() -> None:
    """Run ``alembic upgrade head`` using the project's async migration env."""
    from alembic.config import Config
    from alembic import command

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    logger.info("Database migrations applied successfully")


def main() -> None:
    setup_logging(service="admin")
    config = load_config()

    logger.info("Running database migrations...")
    try:
        _run_migrations()
    except Exception:
        logger.exception("Migration failed — starting anyway (tables may already be up-to-date)")

    app = create_app(config)
    uvicorn.run(
        app,
        host=config.admin.host,
        port=config.admin.port,
        log_level="warning",
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
