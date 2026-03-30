"""Admin service entry point — starts Uvicorn on port 9090."""

from __future__ import annotations

import uvicorn

from common.logging import setup_logging
from config.loader import load_config
from services.admin.app import create_app


def main() -> None:
    setup_logging(service="admin")
    config = load_config()
    app = create_app(config)
    uvicorn.run(
        app,
        host=config.admin.host,
        port=config.admin.port,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
