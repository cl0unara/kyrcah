import json
import logging
import math
import os
import sys
import threading
from queue import Queue, Empty

from errors import BudgetError, ValidationError
from models import Budget, Category, TransactionFactory
from data_manager import DataManager

# У звичайному запуску файли лежать поруч зі скриптами.
# У зібраному PyInstaller EXE — поруч із самим exe, а не в тимчасовій папці розпакування.
BASE_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
DEFAULT_DATA_FILE = os.path.join(BASE_DIR, "budget.json")
# налаштування інтерфейсу (наприклад, обрана тема) — окремо від даних бюджету
DEFAULT_SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

