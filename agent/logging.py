"""Structured logging. JSON to file, human-readable to stderr."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog

from agent.config import settings

_configured = False


def setup_logging(log_path: Path | None = None, level: str | None = None) -> None:
    global _configured
    if _configured:
        return

    log_path = log_path or settings.agent_log_path
    level_name = (level or settings.agent_log_level).upper()
    log_level = getattr(logging, level_name, logging.INFO)

    log_path.parent.mkdir(parents=True, exist_ok=True)

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
            ],
        )
    )

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(stderr_handler)

    for noisy in ("urllib3", "httpx", "botocore", "boto3", "web3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    setup_logging()
    return structlog.get_logger(name)
