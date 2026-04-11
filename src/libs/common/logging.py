"""Structured JSON logging configuration for all services."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            payload["exception"] = self.formatException(record.exc_info)
        extra_keys = {"correlation_id", "instance_id", "service"}
        for key in extra_keys:
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        return json.dumps(payload, ensure_ascii=False)


class FD2Handler(logging.Handler):
    """Logging handler that writes directly to file descriptor 2 (stderr).

    Bypasses sys.stderr entirely to avoid issues with uvicorn replacing it.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record) + "\n"
            os.write(2, msg.encode("utf-8", errors="replace"))
        except Exception:
            self.handleError(record)


def setup_logging(*, level: str = "INFO", service: str = "rdpproxy") -> None:
    """Configure root logger with JSON formatter writing directly to FD 2."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for h in root.handlers[:]:
        root.removeHandler(h)
    handler = FD2Handler()
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
    old_factory = logging.getLogRecordFactory()

    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = old_factory(*args, **kwargs)
        record.service = service  # type: ignore[attr-defined]
        return record

    logging.setLogRecordFactory(factory)
