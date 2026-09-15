"""Local JSON event logs with bounded rotation; no raw note text in logs."""
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .storage import timestamp


class JsonFormatter(logging.Formatter):
    def format(self, record):
        event = {"timestamp": timestamp(), "level": record.levelname, "event": record.getMessage(),
                 **getattr(record, "details", {})}
        if record.exc_info:
            event["exception"] = self.formatException(record.exc_info)
        return json.dumps(event, ensure_ascii=False, default=str)


def configure(directory):
    path = Path(directory).resolve() / "logs" / "ingestion.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("cognyx")
    logger.setLevel(logging.INFO)
    # Dagster may call multiple assets in one process. Avoid duplicate handlers.
    for handler in list(logger.handlers):
        if getattr(handler, "baseFilename", None) == str(path):
            return logger
        logger.removeHandler(handler)
        handler.close()
    handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger
