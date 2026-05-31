"""Structured (JSON-lines) logging that can also feed the TUI (design §13a)."""

from __future__ import annotations

import json
import logging
import sys
from typing import Optional


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(*, verbose: bool = False, log_file: Optional[str] = None,
                  json_lines: bool = False) -> None:
    """Configure root logging. JSON lines mode is intended for headless/TUI use."""
    root = logging.getLogger("fofo_censor")
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers.clear()

    handler: logging.Handler
    if log_file:
        handler = logging.FileHandler(log_file, encoding="utf-8")
    else:
        handler = logging.StreamHandler(sys.stderr)

    if json_lines:
        handler.setFormatter(JsonLineFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    root.addHandler(handler)
