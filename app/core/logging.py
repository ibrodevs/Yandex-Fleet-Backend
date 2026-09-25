import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

SENSITIVE_KEYS = {
    "x-api-key",
    "x_api_key",
    "api_key",
    "apikey",
    "x-client-id",
    "x_client_id",
    "client_id",
    "secret",
    "secret_key",
    "password",
    "authorization",
    "token",
    "access_token",
    "refresh_token",
}


def mask_sensitive_data(data: Any) -> Any:
    """Recursively mask sensitive values in dictionaries and lists."""
    if isinstance(data, dict):
        masked: dict[str, Any] = {}
        for key, val in data.items():
            if str(key).lower() in SENSITIVE_KEYS:
                masked[key] = "***MASKED***"
            else:
                masked[key] = mask_sensitive_data(val)
        return masked
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    return data


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as structured JSON, guaranteeing no secrets leak."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include structured extra attributes if present
        if hasattr(record, "event"):
            log_obj["event"] = record.event
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            for k, v in record.extra_fields.items():
                if k not in log_obj:
                    log_obj[k] = v

        # If exc_info is present, include traceback
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Mask sensitive data before dumping
        safe_obj = mask_sensitive_data(log_obj)
        return json.dumps(safe_obj, default=str, ensure_ascii=False)


def setup_logging(log_level: str = "INFO", json_logs: bool = True) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    # Remove existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if json_logs:
        handler.setFormatter(StructuredJsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
        )
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, event: str, level: str = "info", **kwargs: Any) -> None:
    """Convenience helper to emit structured event logs."""
    safe_kwargs = mask_sensitive_data(kwargs)
    extra = {
        "event": event,
        "extra_fields": safe_kwargs,
    }
    msg = f"event={event}"
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(msg, extra=extra)
