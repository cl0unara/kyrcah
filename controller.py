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

# Види повідомлень, якими завершується фонова задача
FINAL_EVENTS = ("import_ok", "import_error", "report_ok", "report_error")

# Український алфавіт: щоб «і», «ї», «є», «ґ» сортувались на своїх місцях, а не після «я»
_UK_ORDER = {ch: 1000 + i for i, ch in enumerate("абвгґдеєжзиіїйклмнопрстуфхцчшщьюя")}


def text_key(value: str) -> tuple:
    return tuple(_UK_ORDER.get(ch, ord(ch)) for ch in value.lower())


# Ключі сортування таблиці транзакцій (колонка -> функція ключа)
SORT_KEYS = {
    "id": lambda t: t.trans_id,
    "type": lambda t: text_key(t.type_label),
    "amount": lambda t: t.amount if t.kind == "Income" else -t.amount,  # як у таблиці: витрати зі знаком «−»
    "date": lambda t: t.date_str,
    "category": lambda t: text_key(t.category_name),
    "person": lambda t: text_key(t.person),
    "description": lambda t: text_key(t.description),
    "created": lambda t: t.created_at,
}


class BudgetController:
    """
    Controller (MVC): посередник між View (Tkinter) та Model (Budget, DataManager).
    Не містить жодного коду Tkinter. Уся валідація введення, пошук, фільтрація, сортування
    та запуск фонових задач — тут і в моделі; View лише показує результат.
    """

    def __init__(self, data_file: str = DEFAULT_DATA_FILE, settings_file: str = DEFAULT_SETTINGS_FILE):
        self.budget: Budget = Budget.create_default()
        self.data_file = data_file
        self.settings_file = settings_file
        self.settings: dict = self._load_settings()
        self.queue: Queue = Queue()   # канал зв'язку з фоновими потоками
        self.is_busy = False          # виконується фонова задача (імпорт або розрахунок звіту)
        self.dirty = False            # є незбережені зміни
        self._import_path = ""

    # ---------- Налаштування інтерфейсу ----------
    def _load_settings(self) -> dict:
        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def get_setting(self, key: str, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key: str, value):
        self.settings[key] = value
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
        except OSError as e:
            logging.error(f"Не вдалося зберегти налаштування: {e}")

    # ---------- Допоміжні ----------
    def _ensure_idle(self):
        if self.is_busy:
            raise BudgetError("Зачекайте завершення фонової операції.")

    @staticmethod
    def _parse_number(text: str, field: str) -> float:
        try:
            value = float(str(text).strip().replace(" ", "").replace(",", "."))
        except ValueError:
            raise ValidationError(f"Поле «{field}» повинно бути числом.")
        if not math.isfinite(value):
            raise ValidationError(f"Поле «{field}» повинно бути скінченним числом.")
        return value

    def _mark_changed(self, message: str):
        self.dirty = True
        logging.info(message)

    # ---------- Фонові задачі (threading.Thread + queue.Queue) ----------
    def has_saved_file(self) -> bool:
        return os.path.isfile(self.data_file)

    def start_import(self, file_path: str):
        """Запускає фоновий імпорт. Результат забирає View через poll() у циклі after()."""
        self._ensure_idle()
        self.is_busy = True
        self._import_path = file_path
        DataManager.load_async(file_path, self.queue)

    # ШІ: Claude (Sonnet 5.5) – чернетка методу start_report() за специфікацією студента (п. 4.4 завдання).
    # Змінено: потік лише читає копію даних (snapshot під Lock) і передає результат через queue.Queue;
    # перевірено тестами tests/test_budget.py.
    def start_report(self, month: str):
        """Запускає розрахунок місячного звіту в окремому threading.Thread (з індикатором виконання)."""
        self._ensure_idle()
        if not month:
            raise ValidationError("Оберіть місяць для звіту.")
        self.is_busy = True

        def worker():
            try:
                report = self.budget.get_report_data(
                    month, progress=lambda done, total: self.queue.put(("progress", done / total)))
                self.queue.put(("report_ok", report))
            except Exception as e:
                logging.exception("Помилка розрахунку звіту")
                self.queue.put(("report_error", str(e)))

        threading.Thread(target=worker, name="report-thread", daemon=True).start()

    def poll(self) -> list[tuple]:
        """
        Неблокуюча перевірка черги (викликається з головного потоку через after()).
        Повертає список повідомлень (вид, дані); порожній список — результатів ще немає.
        Підсумок імпорту застосовується тут, тож View лише оновлює відображення.
        """
        events = []
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except Empty:
                break
            if kind == "import_ok":
                self.is_busy = False
                self.budget = payload
                # дані з іншого файлу ще не збережені в budget.json
                self.dirty = os.path.abspath(self._import_path) != os.path.abspath(self.data_file)
            elif kind in ("import_error", "report_ok", "report_error"):
                self.is_busy = False
            events.append((kind, payload))
        return events

    # ---------- Транзакції ----------
    def get_transaction(self, trans_id: int):
        return self.budget.get_transaction(trans_id)

    def find_transactions(self, month: str | None = None, category: str | None = None, text: str = "",
                          sort_col: str = "date", descending: bool = True) -> tuple[list, int]:
        """
        Пошук за текстом, фільтрація за місяцем і категорією, сортування (п. 4.2 завдання).
        Повертає (відфільтровані записи, кількість записів до пошуку за текстом).
        """
        period = self.budget.snapshot(month)
        if category:
            period = [t for t in period if t.category_name == category]
        query = text.strip().lower()
        rows = [t for t in period if t.matches(query)] if query else list(period)
        key = SORT_KEYS[sort_col]
        rows.sort(key=lambda t: (key(t), t.trans_id), reverse=descending)
        return rows, len(period)

    def add_transaction(self, t_type: str, amount_text: str, date_str: str, category: str, description: str,
                        person: str = "", frequency: str = "monthly"):
        self._ensure_idle()
        transaction = TransactionFactory.create(
            t_type,
            self.budget.next_transaction_id(),
            self._parse_number(amount_text, "Сума"),
            date_str,
            category,
            description,
            frequency,
            person,
        )
        self.budget.add_transaction(transaction)
        self._mark_changed(f"Додано транзакцію #{transaction.trans_id} ({transaction.type_label}, {transaction.amount})")
        return transaction

    def update_transaction(self, trans_id: int, t_type: str, amount_text: str, date_str: str, category: str,
                           description: str, person: str = "", frequency: str = "monthly"):
        self._ensure_idle()
        old = self.budget.get_transaction(trans_id)
        if old is None:
            raise ValidationError(f"Транзакцію з ID {trans_id} не знайдено.")
        new = TransactionFactory.create(
            t_type, trans_id, self._parse_number(amount_text, "Сума"), date_str, category,
            description, frequency, person, created_at=old.created_at  # дата створення не змінюється
        )
        self.budget.replace_transaction(trans_id, new)
        self._mark_changed(f"Змінено транзакцію #{trans_id}")
        return new

    def delete_transaction(self, trans_id: int):
        self._ensure_idle()
        self.budget.remove_transaction(trans_id)
        self._mark_changed(f"Видалено транзакцію #{trans_id}")

    # ---------- Категорії та ліміти ----------
    def get_categories(self, cat_type: str | None = None) -> list:
        """Категорії (усі або лише 'Income' / 'Expense') у порядку додавання."""
        return [c for c in list(self.budget.categories.values()) if cat_type is None or c.cat_type == cat_type]

    def get_category(self, name: str):
        return self.budget.categories.get(name)

    def add_category(self, name: str, cat_type: str, limit_text: str):
        self._ensure_idle()
        limit = 0.0
        if cat_type == "Expense" and limit_text.strip():
            limit = self._parse_number(limit_text, "Місячний ліміт")
        self.budget.add_category(Category(name, cat_type, limit))
        self._mark_changed(f"Додано категорію '{name.strip()}' ({cat_type}, ліміт {limit})")

    def update_category(self, name: str, new_name: str, limit_text: str):
        """Редагування категорії: назва та місячний ліміт."""
        self._ensure_idle()
        limit = self._parse_number(limit_text or "0", "Місячний ліміт")
        self.budget.update_category(name, new_name, limit)
        self._mark_changed(f"Змінено категорію '{name}' -> '{new_name.strip()}', ліміт {limit}")

    def delete_category(self, name: str):
        self._ensure_idle()
        self.budget.remove_category(name)
        self._mark_changed(f"Видалено категорію '{name}'")

    # ---------- Користувачі та аналітика ----------
    def get_persons(self) -> list[str]:
        return self.budget.get_persons()

    def get_months(self) -> list[str]:
        """Місяці (РРРР-ММ), у яких є транзакції; нові — першими."""
        return self.budget.get_months()

    def has_transactions(self) -> bool:
        return bool(self.budget.transactions)

    def get_monthly_summary(self) -> list[dict]:
        return self.budget.get_monthly_summary()

    def get_summary(self, month: str | None = None) -> dict:
        """Швидкі підсумки для карток головного вікна (синхронно: це лише додавання чисел)."""
        return self.budget.get_report_data(month)

    def get_analytics(self, month: str | None = None) -> dict:
        spent = self.budget.get_expenses_by_category(month)
        spent = dict(sorted(spent.items(), key=lambda item: item[1], reverse=True))
        limits = {name: self.budget.categories[name].monthly_limit
                  for name in spent if name in self.budget.categories}
        return {
            "spent": spent,
            "limits": limits,
            "total": sum(spent.values()),
            # місячні ліміти коректно порівнювати лише з витратами за конкретний місяць
            "check_limits": month is not None,
        }

    # ---------- Збереження та експорт ----------
    def save(self) -> str:
        """Перезаписує budget.json поточним станом."""
        self._ensure_idle()
        DataManager.save_to_json(self.budget, self.data_file)
        self.dirty = False
        return self.data_file

    def export_json(self, file_path: str):
        """Експорт поточного набору у довільний JSON-файл (стан «є незбережені зміни» не змінюється)."""
        self._ensure_idle()
        DataManager.save_to_json(self.budget, file_path)

    def export_xml(self, file_path: str, report: dict):
        """Експорт готового місячного звіту (отриманого через start_report) у XML."""
        DataManager.export_report_to_xml(report, file_path)
