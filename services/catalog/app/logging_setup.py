"""Structured JSON logging.

One JSON object per line, so log tools (Loki, CloudWatch, ELK) can search by
field: level, service, request_id, path, status, duration_ms.
"""
import contextvars
import json
import logging
import sys
import time

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, version: str):
        super().__init__()
        self.service = service
        self.version = version

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "service": self.service,
            "version": self.version,
            "logger": record.name,
            "request_id": request_id_var.get(),
            "msg": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(service: str, version: str, level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service, version))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # uvicorn's own access log duplicates ours; keep only its errors
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("uvicorn.error").setLevel(level)


def log_fields(**fields):
    """Attach structured fields to a log call: log.info("msg", extra=log_fields(a=1))."""
    return {"fields": fields}
