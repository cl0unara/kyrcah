"""Налаштування логування модулем logging у файл budget.log (п. 4.5 завдання)."""
import logging
import os
import sys

# У зібраному EXE журнал має зберігатися поруч із програмою, а не в тимчасовій папці PyInstaller.
BASE_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
LOG_FILE = os.path.join(BASE_DIR, "budget.log")


def setup_logging(log_file: str = LOG_FILE) -> None:
    """Викликається один раз при старті застосунку (main.py)."""
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(threadName)s - %(message)s",
        encoding="utf-8",
    )
