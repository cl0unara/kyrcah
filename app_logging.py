"""Налаштування логування модулем logging у файл budget.log (п. 4.5 завдання)."""
import logging
import os

# Журнал лежить поруч зі скриптами, а не в поточній папці запуску
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "budget.log")


def setup_logging(log_file: str = LOG_FILE) -> None:
    """Викликається один раз при старті застосунку (main.py)."""
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(threadName)s - %(message)s",
        encoding="utf-8",
    )
