from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        extra = getattr(record, 'extra_data', None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class PrettyFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now().strftime('%H:%M:%S')
        extra = getattr(record, 'extra_data', None)
        suffix = ''
        if isinstance(extra, dict) and extra:
            suffix = ' | ' + ' '.join(f'{k}={v}' for k, v in extra.items())
        base = f'[{ts}] {record.levelname:<7} {record.name}: {record.getMessage()}'
        if record.exc_info:
            base += '\n' + self.formatException(record.exc_info)
        return base + suffix


class ContextAdapter(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: Dict[str, Any]):
        supplied = kwargs.pop('extra', {}) or {}
        merged = dict(self.extra)
        merged.update(supplied)
        kwargs['extra'] = {'extra_data': merged}
        return msg, kwargs


def setup_logging() -> None:
    level_name = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_format = os.getenv('LOG_FORMAT', 'pretty').lower()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(JsonFormatter() if log_format == 'json' else PrettyFormatter())
    root.addHandler(handler)


def get_logger(name: str, **context: Any) -> ContextAdapter:
    return ContextAdapter(logging.getLogger(name), context)
