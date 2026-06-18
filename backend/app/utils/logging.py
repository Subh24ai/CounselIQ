"""Structured JSON logging configuration.

Emits one JSON object per log record on stdout so that container log
collectors (CloudWatch / ECS) can parse them natively.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from app.config import settings
from app.middleware.request_id import request_id_ctx


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "environment": settings.ENVIRONMENT,
        }

        # Correlate every log line emitted while handling a request.
        request_id = request_id_ctx.get()
        if request_id:
            payload["request_id"] = request_id

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Attach any structured "extra" fields without clobbering reserved keys.
        reserved = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
        for key, value in record.__dict__.items():
            if key not in reserved and not key.startswith("_"):
                payload[key] = value

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Install the JSON formatter on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL.upper())

    # Align uvicorn loggers with our handler so output stays consistent.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
