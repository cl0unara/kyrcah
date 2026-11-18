"""
Функціональні тести (п. 6 завдання): пошкоджений файл, граничні значення, категорії, звіт, фонові потоки.
Запуск з папки проєкту:  python -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controller import BudgetController, FINAL_EVENTS  # noqa: E402
from data_manager import DataManager  # noqa: E402
from errors import BudgetError, CategoryError, DataFileError, ValidationError  # noqa: E402
from models import (Budget, Category, Expense, Income, RegularExpense, Reportable,  # noqa: E402
                    Transaction, TransactionFactory)
from generate_data import generate  # noqa: E402


def make_budget() -> Budget:
    b = Budget.create_default()
    b.add_transaction(Income(1, 20000, "2026-10-01", "Зарплата"))
    b.add_transaction(Expense(2, 3000.0, "2026-10-05", "Продукти"))
    b.add_transaction(RegularExpense(3, 3500.0, "2026-10-10", "Комунальні"))   # рівно на ліміті
    b.add_transaction(Expense(4, 0.01, "2026-10-11", "Комунальні"))            # +1 копійка -> перевищення
    b.add_transaction(Expense(5, 500.0, "2026-09-30", "Продукти"))             # інший місяць
    return b


class ModelValidationTests(unittest.TestCase):
    def test_hierarchy_and_interface(self):
        self.assertTrue(issubclass(Income, Transaction) and issubclass(RegularExpense, Expense))
        self.assertTrue(issubclass(Budget, Reportable))
        with self.assertRaises(TypeError):
            Transaction(1, 10, "2026-01-01", "Продукти")  # абстрактний клас

    def test_apply_to_is_polymorphic(self):
        self.assertEqual(Income(1, 100, "2026-01-01", "Зарплата").apply_to(50), 150)
        self.assertEqual(Expense(1, 100, "2026-01-01", "Продукти").apply_to(50), -50)
        self.assertEqual(RegularExpense(1, 100, "2026-01-01", "Продукти").apply_to(50), -50)

    def test_amount_boundaries(self):
        for bad in (0, -1, -0.01, "abc", None, float("nan"), float("inf"), Transaction.MAX_AMOUNT + 1):
            with self.assertRaises(ValidationError, msg=str(bad)):
                Expense(1, bad, "2026-01-01", "Продукти")
        self.assertEqual(Expense(1, 0.01, "2026-01-01", "Продукти").amount, 0.01)
        self.assertEqual(Expense(1, Transaction.MAX_AMOUNT, "2026-01-01", "Продукти").amount, Transaction.MAX_AMOUNT)

    def test_date_validation(self):
        for bad in ("2026-02-30", "2026-13-01", "01.02.2026", "", "abc", "2026-1"):
            with self.assertRaises(ValidationError, msg=bad):
                Expense(1, 10, bad, "Продукти")
        self.assertEqual(Expense(1, 10, "2024-02-29", "Продукти").date_str, "2024-02-29")  # високосний рік
        self.assertEqual(Expense(1, 10, "2026-1-5", "Продукти").date_str, "2026-01-05")    # нормалізація

    def test_category_required_and_text_limits(self):
        with self.assertRaises(ValidationError):
            Expense(1, 10, "2026-01-01", "  ")
        with self.assertRaises(ValidationError):
            Expense(1, 10, "2026-01-01", "Продукти", description="x" * (Transaction.MAX_DESCRIPTION + 1))
        Expense(1, 10, "2026-01-01", "Продукти", description="x" * Transaction.MAX_DESCRIPTION)

    def test_regular_expense_frequency(self):
        with self.assertRaises(ValidationError):
            RegularExpense(1, 10, "2026-01-01", "Комунальні", frequency="daily")
        self.assertEqual(RegularExpense(1, 10, "2026-01-01", "Комунальні", frequency="weekly").to_dict()["frequency"],
                         "weekly")

    def test_factory_unknown_type(self):
        with self.assertRaises(ValidationError):
            TransactionFactory.create("Gift", 1, 10, "2026-01-01", "Продукти")

    def test_category_validation(self):
        with self.assertRaises(ValidationError):
            Category("", "Expense")
        with self.assertRaises(ValidationError):
            Category("X", "Other")
        with self.assertRaises(ValidationError):
            Category("X", "Expense", -1)
        with self.assertRaises(ValidationError):
            Category("X", "Income", 100)   # ліміт лише для витрат
        self.assertEqual(Category("X", "Expense", 0).monthly_limit, 0)


class BudgetTests(unittest.TestCase):
    def test_nonexistent_category_and_wrong_type(self):
        b = Budget.create_default()
        with self.assertRaises(CategoryError):
            b.add_transaction(Expense(1, 10, "2026-01-01", "Немає такої"))
        with self.assertRaises(CategoryError):
            b.add_transaction(Expense(1, 10, "2026-01-01", "Зарплата"))   # категорія доходів
        self.assertEqual(len(b.transactions), 0)

    def test_duplicate_id_and_missing_transaction(self):
        b = make_budget()
        with self.assertRaises(ValidationError):
            b.add_transaction(Expense(1, 10, "2026-01-01", "Продукти"))
        with self.assertRaises(ValidationError):
            b.remove_transaction(999)

    def test_category_crud(self):
        b = make_budget()
        with self.assertRaises(CategoryError):
            b.add_category(Category("Продукти", "Expense"))            # дубль
        with self.assertRaises(CategoryError):
            b.remove_category("Продукти")                              # є транзакції
        with self.assertRaises(CategoryError):
            b.remove_category("Немає")
        b.remove_category("Тварини")                                    # без транзакцій — можна
        self.assertFalse(b.has_category("Тварини"))

        position = list(b.categories).index("Продукти")
        b.update_category("Продукти", "Їжа", 9000)                      # перейменування разом із транзакціями
        self.assertEqual(list(b.categories).index("Їжа"), position)
        self.assertEqual(b.categories["Їжа"].monthly_limit, 9000)
        self.assertEqual(b.get_transaction(2).category_name, "Їжа")
        with self.assertRaises(CategoryError):
            b.update_category("Їжа", "Транспорт", 1)                    # назва зайнята
        with self.assertRaises(ValidationError):
            b.update_category("Їжа", "Їжа", -5)

    def test_report_limits_boundaries(self):
        report = make_budget().get_report_data("2026-10")
        self.assertEqual(report["total_income"], 20000)
        self.assertEqual(report["total_expense"], 6500.01)
        self.assertEqual(report["balance"], 13499.99)                  # баланс через apply_to()
        self.assertEqual(report["transaction_count"], 4)
        self.assertEqual(list(report["overlimit_categories"]), ["Комунальні"])
        self.assertEqual(report["overlimit_categories"]["Комунальні"]["exceeded_by"], 0.01)
        self.assertNotIn("Продукти", report["overlimit_categories"])   # 3000 < 8000

    def test_report_exactly_at_limit_is_not_exceeded(self):
        b = Budget.create_default()
        b.add_transaction(Expense(1, 3500.0, "2026-10-10", "Комунальні"))
        self.assertEqual(b.get_report_data("2026-10")["overlimit_categories"], {})

    def test_report_empty_month_and_all_time(self):
        b = make_budget()
        empty = b.get_report_data("2020-01")
        self.assertEqual((empty["total_income"], empty["total_expense"], empty["balance"]), (0, 0, 0))
        total = b.get_report_data()                                     # весь час: ліміти не перевіряються
        self.assertFalse(total["limits_checked"])
        self.assertEqual(total["overlimit_categories"], {})
        self.assertEqual(total["transaction_count"], 5)

    def test_chunked_report_equals_single_pass(self):
        big = DataManager._build_budget(generate(5000, days=120, seed=7))
        month = big.get_months()[0]
        big.CHUNK_SIZE = 7
        chunked = big.get_report_data(month)
        big.CHUNK_SIZE = 10 ** 9
        self.assertEqual(chunked, big.get_report_data(month))

    def test_progress_callback(self):
        big = DataManager._build_budget(generate(2500, days=30, seed=3))
        calls = []
        big.get_report_data(None, progress=lambda done, total: calls.append((done, total)))
        self.assertEqual(calls[-1], (2500, 2500))
        self.assertEqual([c[0] for c in calls], sorted(c[0] for c in calls))


class DataFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def path(self, name):
        return os.path.join(self.dir.name, name)

    def write(self, name, text):
        with open(self.path(name), "w", encoding="utf-8") as f:
            f.write(text)
        return self.path(name)

    VALID_CAT = '{"name": "Продукти", "type": "Expense", "monthly_limit": 100}'

    def test_corrupted_files(self):
        cases = {
            "not_json": "це не json {",
            "truncated": '{"categories": [], "transactions": [',
            "empty": "",
            "list_root": "[1, 2, 3]",
            "no_lists": '{"categories": 5, "transactions": "x"}',
            "missing_field": '{"categories": [%s], "transactions": [{"trans_id": 1}]}' % self.VALID_CAT,
            "bad_amount": '{"categories": [%s], "transactions": [{"trans_id": 1, "type": "Expense", "amount": -5,'
                          ' "date": "2026-01-01", "category": "Продукти"}]}' % self.VALID_CAT,
            "bad_date": '{"categories": [%s], "transactions": [{"trans_id": 1, "type": "Expense", "amount": 5,'
                        ' "date": "31.12.2026", "category": "Продукти"}]}' % self.VALID_CAT,
            "unknown_category": '{"categories": [%s], "transactions": [{"trans_id": 1, "type": "Expense",'
                                ' "amount": 5, "date": "2026-01-01", "category": "Ніяка"}]}' % self.VALID_CAT,
            "unknown_type": '{"categories": [%s], "transactions": [{"trans_id": 1, "type": "Gift", "amount": 5,'
                            ' "date": "2026-01-01", "category": "Продукти"}]}' % self.VALID_CAT,
            "bad_category": '{"categories": [{"name": "", "type": "Expense"}], "transactions": []}',
            "transaction_not_object": '{"categories": [%s], "transactions": [42]}' % self.VALID_CAT,
        }
        for name, text in cases.items():
            with self.subTest(name):
                with self.assertRaises(DataFileError):
                    DataManager.load_from_json(self.write(name + ".json", text))

    def test_missing_file(self):
        with self.assertRaises(DataFileError):
            DataManager.load_from_json(self.path("немає.json"))

    def test_error_message_names_the_record(self):
        text = '{"categories": [%s], "transactions": [{"trans_id": 1, "type": "Expense", "amount": 5,' \
               ' "date": "2026-01-01", "category": "Продукти"}, {"trans_id": 2, "type": "Expense", "amount": 0,' \
               ' "date": "2026-01-01", "category": "Продукти"}]}' % self.VALID_CAT
        with self.assertRaises(DataFileError) as ctx:
            DataManager.load_from_json(self.write("x.json", text))
        self.assertIn("№2", str(ctx.exception))

    def test_save_and_load_roundtrip(self):
        original = make_budget()
        file_path = self.path("round.json")
        DataManager.save_to_json(original, file_path)
        loaded = DataManager.load_from_json(file_path)
        self.assertEqual([t.to_dict() for t in loaded.transactions], [t.to_dict() for t in original.transactions])
        self.assertEqual([c.to_dict() for c in loaded.categories.values()],
                         [c.to_dict() for c in original.categories.values()])
        self.assertFalse(os.path.exists(file_path + ".tmp"))

    def test_failed_save_keeps_previous_file(self):
        file_path = self.path("keep.json")
        DataManager.save_to_json(make_budget(), file_path)
        with open(file_path, encoding="utf-8") as f:
            before = f.read()
        with self.assertRaises(DataFileError):
            DataManager.save_to_json(make_budget(), os.path.join(self.dir.name, "немає_папки", "x.json"))
        with open(file_path, encoding="utf-8") as f:
            self.assertEqual(f.read(), before)

    def test_xml_report(self):
        report = make_budget().get_report_data("2026-10")
        file_path = self.path("report.xml")
        DataManager.export_report_to_xml(report, file_path)
        root = ET.parse(file_path).getroot()
        self.assertEqual(root.tag, "MonthlyReport")
        self.assertEqual(root.get("period"), "2026-10")
        self.assertEqual(root.findtext("Summary/TotalExpense"), "6500.01")
        cats = root.findall("OverlimitCategories/Category")
        self.assertEqual([c.get("name") for c in cats], ["Комунальні"])
        self.assertEqual(cats[0].findtext("ExceededBy"), "0.01")

    def test_xml_requires_month(self):
        with self.assertRaises(DataFileError):
            DataManager.export_report_to_xml(make_budget().get_report_data(None), self.path("x.xml"))


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.data_file = os.path.join(self.dir.name, "budget.json")
        self.ctrl = BudgetController(self.data_file, os.path.join(self.dir.name, "settings.json"))

    def wait_final(self, timeout=10):
        """Те саме, що робить головне вікно через after(): опитує чергу, поки не прийде завершальна подія."""
        events, deadline = [], time.time() + timeout
        while time.time() < deadline:
            events += self.ctrl.poll()
            if any(kind in FINAL_EVENTS for kind, _ in events):
                return events
            time.sleep(0.01)
        self.fail("фонова задача не завершилась")

    def test_add_validates_input(self):
        c = self.ctrl
        for args in (("Expense", "abc", "2026-10-01", "Продукти", ""),
                     ("Expense", "-5", "2026-10-01", "Продукти", ""),
                     ("Expense", "0", "2026-10-01", "Продукти", ""),
                     ("Expense", "10", "2026-02-30", "Продукти", ""),
                     ("Expense", "10", "2026-10-01", "", ""),
                     ("Expense", "10", "2026-10-01", "Немає такої", ""),
                     ("Income", "10", "2026-10-01", "Продукти", "")):
            with self.assertRaises(BudgetError, msg=str(args)):
                c.add_transaction(*args)
        self.assertEqual(len(c.budget.transactions), 0)
        self.assertFalse(c.dirty)

    def test_crud_and_dirty_flag(self):
        c = self.ctrl
        t = c.add_transaction("Expense", "1 250,50", "2026-10-01", "Продукти", " хліб ", "Іван")
        self.assertEqual((t.amount, t.description, c.dirty), (1250.5, "хліб", True))
        c.update_transaction(t.trans_id, "RegularExpense", "99", "2026-10-02", "Комунальні", "газ", "Іван", "weekly")
        self.assertIsInstance(c.get_transaction(t.trans_id), RegularExpense)
        self.assertEqual(c.get_transaction(t.trans_id).created_at, t.created_at)   # дата створення не змінюється
        c.delete_transaction(t.trans_id)
        self.assertIsNone(c.get_transaction(t.trans_id))
        with self.assertRaises(BudgetError):
            c.delete_transaction(t.trans_id)

    def test_find_transactions_search_filter_sort(self):
        c = self.ctrl
        c.budget = make_budget()
        rows, total = c.find_transactions()
        self.assertEqual((len(rows), total), (5, 5))
        self.assertEqual([t.trans_id for t in rows][:2], [4, 3])                     # за датою спадання, потім ID
        rows, _ = c.find_transactions(sort_col="date", descending=False)
        self.assertEqual(rows[0].trans_id, 5)                                       # 2026-09-30 найстаріша
        rows, _ = c.find_transactions(sort_col="amount", descending=True)
        self.assertEqual(rows[0].trans_id, 1)                                       # дохід — найбільша сума
        self.assertEqual(rows[-1].trans_id, 3)                                      # витрата 3500 — найменше значення
        rows, total = c.find_transactions(month="2026-10", category="Комунальні")
        self.assertEqual(([t.trans_id for t in rows], total), ([4, 3], 2))   # дата спадає
        rows, total = c.find_transactions(month="2026-10", text="ПРОДУКТИ")         # без урахування регістру
        self.assertEqual(([t.trans_id for t in rows], total), ([2], 4))
        self.assertEqual(c.find_transactions(text="немає такого")[0], [])

    def test_ukrainian_sorting_order(self):
        c = self.ctrl
        for name in ("Яблука", "Іграшки", "Їжа", "Ґанок", "Гриби", "Дім"):
            c.add_category(name, "Expense", "")
            c.add_transaction("Expense", "10", "2026-10-01", name, "")
        rows, _ = c.find_transactions(sort_col="category", descending=False)
        names = [t.category_name for t in rows]
        self.assertEqual(names, ["Гриби", "Ґанок", "Дім", "Іграшки", "Їжа", "Яблука"])

    def test_category_operations_through_controller(self):
        c = self.ctrl
        c.add_category("Хобі", "Expense", "1 500,5")
        self.assertEqual(c.get_category("Хобі").monthly_limit, 1500.5)
        c.update_category("Хобі", "Хобі та ігри", "2000")
        self.assertIsNone(c.get_category("Хобі"))
        c.delete_category("Хобі та ігри")
        with self.assertRaises(ValidationError):
            c.add_category("Нова", "Expense", "abc")
        with self.assertRaises(ValidationError):
            c.add_category("Нова", "Expense", "-1")
        with self.assertRaises(ValidationError):
            c.add_category("", "Expense", "")

    def test_background_import_reports_progress_and_applies_result(self):
        DataManager.save_to_json(self.make_big(3000), self.data_file)
        self.ctrl.start_import(self.data_file)
        self.assertTrue(self.ctrl.is_busy)
        with self.assertRaises(BudgetError):                      # під час фонової задачі зміни заборонені
            self.ctrl.add_transaction("Expense", "10", "2026-10-01", "Продукти", "")
        events = self.wait_final()
        kinds = [k for k, _ in events]
        self.assertIn("progress", kinds)
        self.assertEqual(kinds[-1], "import_ok")
        self.assertFalse(self.ctrl.is_busy)
        self.assertEqual(len(self.ctrl.budget.transactions), 3000)
        self.assertFalse(self.ctrl.dirty)                         # імпорт із budget.json = збережений стан

    @staticmethod
    def make_big(count):
        return DataManager._build_budget(generate(count, days=200, seed=1))

    def test_background_import_of_corrupted_file_keeps_data(self):
        self.ctrl.add_transaction("Expense", "10", "2026-10-01", "Продукти", "")
        bad = os.path.join(self.dir.name, "bad.json")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("{ пошкоджено")
        self.ctrl.start_import(bad)
        events = self.wait_final()
        self.assertEqual(events[-1][0], "import_error")
        self.assertIn("пошкоджено", events[-1][1])
        self.assertEqual(len(self.ctrl.budget.transactions), 1)   # старі дані не втрачено
        self.assertFalse(self.ctrl.is_busy)

    def test_background_report(self):
        self.ctrl.budget = self.make_big(4000)
        month = self.ctrl.get_months()[0]
        self.ctrl.start_report(month)
        events = self.wait_final()
        self.assertEqual(events[-1][0], "report_ok")
        self.assertEqual(events[-1][1], self.ctrl.budget.get_report_data(month))
        self.assertIn("progress", [k for k, _ in events])
        self.assertFalse(self.ctrl.is_busy)
        with self.assertRaises(ValidationError):
            self.ctrl.start_report("")

    def test_export_json_does_not_reset_dirty(self):
        self.ctrl.add_transaction("Expense", "10", "2026-10-01", "Продукти", "")
        self.ctrl.export_json(os.path.join(self.dir.name, "copy.json"))
        self.assertTrue(self.ctrl.dirty)
        self.ctrl.save()
        self.assertFalse(self.ctrl.dirty)

    def test_lock_protects_shared_data(self):
        """Один потік додає транзакції, інший одночасно рахує звіт: помилок і втрат немає."""
        import threading
        b = Budget.create_default()
        errors = []

        def writer():
            try:
                for i in range(1, 2001):
                    b.add_transaction(Expense(i, 1.0, "2026-10-01", "Продукти"))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        def reader():
            try:
                for _ in range(200):
                    report = b.get_report_data("2026-10")
                    assert report["total_expense"] == report["transaction_count"] * 1.0
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(len(b.transactions), 2000)


if __name__ == "__main__":
    unittest.main()
