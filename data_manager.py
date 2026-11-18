"""
Робота з файлами: імпорт/експорт JSON (модуль json), експорт звіту в XML (xml.etree.ElementTree),
фоновий імпорт у threading.Thread. Тут немає коду Tkinter.
"""
import json
import logging
import os
import threading
import xml.etree.ElementTree as ET
from queue import Queue

from errors import BudgetError, DataFileError
from models import Budget, Category, TransactionFactory

# Захищає читання/запис файлів: фоновий імпорт і збереження з головного потоку не перетинаються
file_lock = threading.Lock()

PROGRESS_STEP = 500   # як часто (у записах) імпорт повідомляє про прогрес


class DataManager:
    @staticmethod
    def load_from_json(file_path: str, progress=None) -> Budget:
        """
        Завантаження бюджету з JSON. Імпорт атомарний: у разі помилки повертається виняток,
        а поточні дані застосунку не змінюються. progress(done, total) — необов'язковий виклик для індикатора.
        """
        with file_lock:
            try:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except FileNotFoundError:
                    raise DataFileError(f"Файл не знайдено: {file_path}")
                except json.JSONDecodeError as e:
                    raise DataFileError(f"Файл пошкоджено (некоректний JSON): рядок {e.lineno}, стовпець {e.colno}.")
                except (OSError, UnicodeDecodeError) as e:
                    raise DataFileError(f"Не вдалося прочитати файл: {e}")

                budget = DataManager._build_budget(data, progress)
                logging.info(f"Успішно завантажено файл: {file_path} "
                             f"(категорій: {len(budget.categories)}, транзакцій: {len(budget.transactions)})")
                return budget
            except Exception as e:
                logging.error(f"Помилка завантаження файлу {file_path}: {e}")
                raise

    @staticmethod
    def _build_budget(data, progress=None) -> Budget:
        """Перетворює словник із JSON на об'єкти моделі, перевіряючи структуру та значення."""
        if not isinstance(data, dict) or not isinstance(data.get("categories"), list) \
                or not isinstance(data.get("transactions"), list):
            raise DataFileError("Неправильна структура файлу: очікуються списки 'categories' та 'transactions'.")

        budget = Budget()
        for number, cat in enumerate(data["categories"], start=1):
            try:
                budget.add_category(Category(cat["name"], cat["type"], cat.get("monthly_limit", 0.0)))
            except (KeyError, TypeError, AttributeError):
                raise DataFileError(f"Категорія №{number}: відсутнє обов'язкове поле або неправильний формат.")
            except BudgetError as e:
                raise DataFileError(f"Категорія №{number}: {e}")

        transactions = data["transactions"]
        total = len(transactions)
        for number, t in enumerate(transactions, start=1):
            try:
                budget.add_transaction(TransactionFactory.create(
                    t["type"], t["trans_id"], t["amount"], t["date"], t["category"],
                    t.get("description", ""), t.get("frequency", "monthly"),
                    t.get("person", ""),
                    t.get("created_at", "")  # старі файли без поля: дата створення невідома
                ))
            except (KeyError, TypeError, AttributeError, ValueError) as e:
                if isinstance(e, BudgetError):
                    raise DataFileError(f"Транзакція №{number}: {e}")
                raise DataFileError(f"Транзакція №{number}: відсутнє обов'язкове поле або неправильний формат.")
            if progress and (number % PROGRESS_STEP == 0 or number == total):
                progress(number, total)
        return budget

    @staticmethod
    def save_to_json(budget: Budget, file_path: str):
        """
        Збереження бюджету у JSON (також використовується для «Експорт JSON» у довільний файл).
        Запис іде у тимчасовий файл, який потім атомарно замінює оригінал,
        тому збій під час запису не пошкодить попередню версію файлу.
        """
        tmp_path = f"{file_path}.tmp"
        with file_lock:
            try:
                data = {
                    "categories": [cat.to_dict() for cat in list(budget.categories.values())],
                    "transactions": [t.to_dict() for t in budget.snapshot()]
                }
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                os.replace(tmp_path, file_path)
                logging.info(f"Дані успішно збережено у: {file_path}")
            except Exception as e:
                logging.error(f"Помилка збереження файлу {file_path}: {e}")
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                if isinstance(e, OSError):
                    raise DataFileError(f"Не вдалося записати файл: {e}")
                raise

    @staticmethod
    def export_report_to_xml(report: dict, file_path: str):
        """Експорт готового місячного звіту (див. Budget.get_report_data) у XML."""
        if not report.get("month"):
            raise DataFileError("XML-звіт формується за конкретний місяць: оберіть місяць.")

        root = ET.Element("MonthlyReport", period=report["month"])
        summary = ET.SubElement(root, "Summary")
        ET.SubElement(summary, "TransactionCount").text = str(report["transaction_count"])
        ET.SubElement(summary, "Balance").text = f"{report['balance']:.2f}"
        ET.SubElement(summary, "TotalIncome").text = f"{report['total_income']:.2f}"
        ET.SubElement(summary, "TotalExpense").text = f"{report['total_expense']:.2f}"

        overlimits = ET.SubElement(root, "OverlimitCategories")
        for cat_name, details in report["overlimit_categories"].items():
            cat_elem = ET.SubElement(overlimits, "Category", name=cat_name)
            ET.SubElement(cat_elem, "Spent").text = f"{details['spent']:.2f}"
            ET.SubElement(cat_elem, "Limit").text = f"{details['limit']:.2f}"
            ET.SubElement(cat_elem, "ExceededBy").text = f"{details['exceeded_by']:.2f}"

        ET.indent(root)  # відступи для зручного читання файлу
        try:
            ET.ElementTree(root).write(file_path, encoding="utf-8", xml_declaration=True)
        except OSError as e:
            logging.error(f"Помилка запису XML {file_path}: {e}")
            raise DataFileError(f"Не вдалося записати файл: {e}")
        logging.info(f"XML-звіт за {report['month']} експортовано у: {file_path}")

    @staticmethod
    def load_async(file_path: str, result_queue: Queue):
        """
        Фонове завантаження великих файлів (10 000+ записів) в окремому threading.Thread.
        Потік НЕ торкається Tkinter: повідомлення (вид, дані) передаються лише через queue.Queue,
        а головне вікно забирає їх через after() і оновлює ttk.Progressbar.
        Види повідомлень: "progress" (частка 0..1), "import_ok" (Budget), "import_error" (текст).
        """

        def on_progress(done: int, total: int):
            result_queue.put(("progress", done / total if total else 1.0))

        def worker():
            try:
                budget = DataManager.load_from_json(file_path, progress=on_progress)
                result_queue.put(("import_ok", budget))
            except Exception as e:  # будь-яка помилка має дійти до користувача, а не загинути в потоці
                result_queue.put(("import_error", str(e)))

        threading.Thread(target=worker, name="import-thread", daemon=True).start()
