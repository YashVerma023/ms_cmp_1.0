"""
helper.py

Central helper module for:
1. Terminal logging
2. CSV log writing
3. Basic project monitoring utilities

This file should stay in the main project directory.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional


# =========================
# Project Paths
# =========================

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "logs.csv"


# =========================
# Logging Setup
# =========================

def ensure_log_file_exists() -> None:
    """
    Ensures logs directory and logs.csv file exist.
    Creates them if missing.
    """

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if not LOG_FILE.exists():
        with LOG_FILE.open(mode="w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "timestamp",
                    "level",
                    "module",
                    "action",
                    "message",
                    "status",
                    "error",
                ]
            )


def setup_terminal_logger() -> logging.Logger:
    """
    Sets up terminal logger with timestamp.
    Prevents duplicate handlers if imported multiple times.
    """

    logger = logging.getLogger("cmp_operation_app")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


logger = setup_terminal_logger()
ensure_log_file_exists()


def write_log(
    *,
    level: str,
    module: str,
    action: str,
    message: str,
    status: str,
    error: Optional[str] = None,
) -> None:
    """
    Writes one log entry into logs/logs.csv.

    Args:
        level: INFO, WARNING, ERROR, DEBUG
        module: File or module name
        action: What operation is being performed
        message: Human-readable message
        status: SUCCESS, FAILED, SKIPPED, STARTED
        error: Optional error message
    """

    ensure_log_file_exists()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with LOG_FILE.open(mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                timestamp,
                level.upper(),
                module,
                action,
                message,
                status.upper(),
                error or "",
            ]
        )


def log_info(
    *,
    module: str,
    action: str,
    message: str,
    status: str = "SUCCESS",
) -> None:
    """
    Logs info message in terminal and CSV.
    """

    logger.info(f"{module} | {action} | {message} | {status}")

    write_log(
        level="INFO",
        module=module,
        action=action,
        message=message,
        status=status,
    )


def log_warning(
    *,
    module: str,
    action: str,
    message: str,
    status: str = "WARNING",
) -> None:
    """
    Logs warning message in terminal and CSV.
    """

    logger.warning(f"{module} | {action} | {message} | {status}")

    write_log(
        level="WARNING",
        module=module,
        action=action,
        message=message,
        status=status,
    )


def log_error(
    *,
    module: str,
    action: str,
    message: str,
    error: Exception | str,
    status: str = "FAILED",
) -> None:
    """
    Logs error message in terminal and CSV.
    """

    error_message = str(error)

    logger.error(f"{module} | {action} | {message} | {status} | ERROR: {error_message}")

    write_log(
        level="ERROR",
        module=module,
        action=action,
        message=message,
        status=status,
        error=error_message,
    )


def log_startup_banner() -> None:
    """
    Logs a simple startup banner.
    """

    log_info(
        module="helper",
        action="startup",
        message="CMP Operation App monitoring started",
        status="STARTED",
    )