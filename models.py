"""
Модель предметної області (Model у MVC): транзакції, категорії, бюджет.
Тут немає жодного коду Tkinter і введення-виведення файлів.
"""
import math
import threading
from abc import ABC, abstractmethod
from datetime import datetime

from errors import CategoryError, ValidationError


class Reportable(ABC):
    """Інтерфейс для об'єктів, які можуть формувати звіт."""

    @abstractmethod
    def get_report_data(self, month: str | None = None) -> dict:
        """Звіт за місяць РРРР-ММ (або за весь час, якщо month=None)."""


class Transaction(ABC):
    """Абстрактний базовий клас для транзакцій (інкапсуляція + валідація через властивості)."""

    DATE_FORMAT = "%Y-%m-%d"
    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
    MAX_AMOUNT = 1_000_000_000
    MAX_DESCRIPTION = 200
    MAX_PERSON = 60
    kind: str = ""        # "Income" або "Expense" — до якого типу категорій належить операція
    type_label: str = ""  # назва типу для відображення в інтерфейсі

    def __init__(self, trans_id: int, amount: float, date_str: str, category_name: str, description: str = "",
                 person: str = "", created_at: str | None = None):
        self._trans_id = int(trans_id)
        self.amount = amount                  # усі поля проходять через setter з валідацією
        self.date_str = date_str
        self.category_name = category_name
        self.description = description
        self.person = person
        # None -> новий запис (час створення = зараз); "" -> старий запис без відомої дати створення
        self._created_at = datetime.now().strftime(self.DATETIME_FORMAT) if created_at is None else str(created_at)

    # ---------- Властивості ----------
    @property
    def trans_id(self) -> int:
        return self._trans_id

    @property
    def amount(self) -> float:
        return self._amount

    @amount.setter
    def amount(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValidationError("Сума повинна бути числом.")
        if not math.isfinite(value) or value <= 0:
            raise ValidationError("Сума транзакції повинна бути більшою за нуль.")
        if value > self.MAX_AMOUNT:
            raise ValidationError(f"Сума не може перевищувати {self.MAX_AMOUNT:,}.".replace(",", " "))
        self._amount = value

    @property
    def date_str(self) -> str:
        return self._date_str

    @date_str.setter
    def date_str(self, value):
        try:
            parsed = datetime.strptime(str(value).strip(), self.DATE_FORMAT)
        except ValueError:
            raise ValidationError("Дата повинна бути коректною та мати формат РРРР-ММ-ДД.")
        self._date_str = parsed.strftime(self.DATE_FORMAT)  # нормалізація (2026-1-5 -> 2026-01-05)

    @property
    def category_name(self) -> str:
        return self._category_name

    @category_name.setter
    def category_name(self, value):
        value = (value or "").strip()
        if not value:
            raise ValidationError("Оберіть категорію!")
        self._category_name = value

    @property
    def description(self) -> str:
        return self._description

    @description.setter
    def description(self, value):
        value = (value or "").strip()
        if len(value) > self.MAX_DESCRIPTION:
            raise ValidationError(f"Опис не може бути довшим за {self.MAX_DESCRIPTION} символів.")
        self._description = value

    @property
    def person(self) -> str:
        return self._person

    @person.setter
    def person(self, value):
        value = (value or "").strip()
        if len(value) > self.MAX_PERSON:
            raise ValidationError(f"Ім'я користувача не може бути довшим за {self.MAX_PERSON} символів.")
        self._person = value

    @property
    def created_at(self) -> str:
        """Дата й час створення запису (РРРР-ММ-ДД ГГ:ХХ:СС); для старих записів може бути порожнім."""
        return self._created_at

    # ---------- Поліморфні методи ----------
    @abstractmethod
    def apply_to(self, current_balance: float) -> float:
        """Повертає баланс після застосування цієї транзакції (перевизначається в нащадках)."""

    def matches(self, query: str) -> bool:
        """Пошук підрядка (у нижньому регістрі) в описі, категорії, даті, типі та імені користувача."""
        text = f"{self.description} {self.category_name} {self.date_str} {self.type_label} {self.person}"
        return query in text.lower()

    def to_dict(self) -> dict:
        return {
            "trans_id": self.trans_id,
            "type": self.__class__.__name__,
            "amount": self.amount,
            "date": self.date_str,
            "category": self.category_name,
            "description": self.description,
            "person": self.person,
            "created_at": self.created_at
        }


class Income(Transaction):
    """Клас доходів."""

    kind = "Income"
    type_label = "Дохід"

    def apply_to(self, current_balance: float) -> float:
        return current_balance + self.amount


class Expense(Transaction):
    """Клас витрат."""

    kind = "Expense"
    type_label = "Витрата"

    def apply_to(self, current_balance: float) -> float:
        return current_balance - self.amount


class RegularExpense(Expense):
    """Клас регулярних (періодичних) витрат."""

    type_label = "Регулярна витрата"
    FREQUENCIES = ("weekly", "monthly", "yearly")

    def __init__(self, trans_id: int, amount: float, date_str: str, category_name: str, description: str = "",
                 frequency: str = "monthly", person: str = "", created_at: str | None = None):
        super().__init__(trans_id, amount, date_str, category_name, description, person, created_at)
        self.frequency = frequency

    @property
    def frequency(self) -> str:
        return self._frequency

    @frequency.setter
    def frequency(self, value):
        if value not in self.FREQUENCIES:
            raise ValidationError(f"Періодичність повинна бути однією з: {', '.join(self.FREQUENCIES)}.")
        self._frequency = value

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["frequency"] = self.frequency
        return data


class TransactionFactory:
    """Фабрика транзакцій: створює об'єкт потрібного підкласу за назвою типу."""

    @staticmethod
    def create(t_type: str, trans_id: int, amount: float, date_str: str, category_name: str,
               description: str = "", frequency: str = "monthly", person: str = "",
               created_at: str | None = None) -> Transaction:
        if t_type == "Income":
            return Income(trans_id, amount, date_str, category_name, description, person, created_at)
        if t_type == "Expense":
            return Expense(trans_id, amount, date_str, category_name, description, person, created_at)
        if t_type == "RegularExpense":
            return RegularExpense(trans_id, amount, date_str, category_name, description, frequency, person,
                                  created_at)
        raise ValidationError(f"Невідомий тип транзакції: {t_type}")


class Category:
    """Клас категорії витрат/доходів з місячним лімітом."""

    MAX_NAME = 60

    def __init__(self, name: str, cat_type: str, monthly_limit: float = 0.0):
        name = (name or "").strip()
        if not name:
            raise ValidationError("Назва категорії не може бути порожньою.")
        if len(name) > self.MAX_NAME:
            raise ValidationError(f"Назва категорії не може бути довшою за {self.MAX_NAME} символів.")
        if cat_type not in ("Income", "Expense"):
            raise ValidationError("Тип категорії повинен бути 'Income' або 'Expense'.")
        self._name = name
        self._cat_type = cat_type
        self.monthly_limit = monthly_limit  # через setter

    @property
    def name(self) -> str:
        return self._name

    @property
    def cat_type(self) -> str:
        return self._cat_type

    @property
    def monthly_limit(self) -> float:
        return self._monthly_limit

    @monthly_limit.setter
    def monthly_limit(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValidationError("Ліміт повинен бути числом.")
        if not math.isfinite(value) or value < 0:
            raise ValidationError("Ліміт не може бути від'ємним.")
        if value > 0 and self._cat_type == "Income":
            raise ValidationError("Ліміти встановлюються лише для категорій витрат.")
        self._monthly_limit = value

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.cat_type,
            "monthly_limit": self.monthly_limit
        }


DEFAULT_CATEGORIES = [
    # Доходи
    ("Зарплата", "Income", 0.0),
    ("Фріланс / Бонуси", "Income", 0.0),
    ("Інвестиції", "Income", 0.0),
    ("Подарунки", "Income", 0.0),
    ("Підробіток", "Income", 0.0),
    ("Стипендія / Допомога", "Income", 0.0),
    ("Відсотки / Кешбек", "Income", 0.0),
    ("Продаж речей", "Income", 0.0),
    ("Повернення боргів", "Income", 0.0),
    ("Інші доходи", "Income", 0.0),
    # Витрати з лімітами
    ("Продукти", "Expense", 8000.0),
    ("Комунальні", "Expense", 3500.0),
    ("Розваги", "Expense", 3000.0),
    ("Транспорт", "Expense", 2000.0),
    ("Кафе та ресторани", "Expense", 2500.0),
    ("Здоров'я та спорт", "Expense", 2000.0),
    ("Покупки / Одяг", "Expense", 4000.0),
    ("Техніка", "Expense", 10000.0),
    ("Зв'язок та інтернет", "Expense", 800.0),
    ("Освіта", "Expense", 3000.0),
    ("Подорожі", "Expense", 5000.0),
    ("Дім та ремонт", "Expense", 4000.0),
    ("Краса та догляд", "Expense", 1500.0),
    ("Побутова хімія", "Expense", 1500.0),
    ("Тварини", "Expense", 1500.0),
    ("Благодійність", "Expense", 0.0),
    ("Інші витрати", "Expense", 3000.0),
]


class Budget(Reportable):
    """
    Центральний клас-агрегатор для управління транзакціями та категоріями.

    Потокобезпечність (п. 4.4 завдання): спільні дані (категорії та список транзакцій) змінюються
    й копіюються лише під threading.Lock. Фоновий потік розрахунку звіту працює з копією (snapshot()),
    тому довгі обчислення не блокують інші операції. Методи з блокуванням не викликають один одного,
    щоб уникнути повторного захоплення звичайного Lock.
    """

    CHUNK_SIZE = 1000   # розмір частини, на які ділиться розрахунок звіту

    def __init__(self):
        self.categories: dict[str, Category] = {}
        self.transactions: list[Transaction] = []
        self._by_id: dict[int, Transaction] = {}  # індекс для швидкого пошуку за ID
        self._lock = threading.Lock()

    @classmethod
    def create_default(cls) -> "Budget":
        """Бюджет із набором категорій за замовчуванням."""
        budget = cls()
        for name, cat_type, limit in DEFAULT_CATEGORIES:
            budget.add_category(Category(name, cat_type, limit))
        return budget

    # ---------- Категорії ----------
    def has_category(self, name: str) -> bool:
        return name in self.categories

    def add_category(self, category: Category):
        with self._lock:
            if category.name in self.categories:
                raise CategoryError(f"Категорія '{category.name}' вже існує.")
            self.categories[category.name] = category

    def set_category_limit(self, name: str, limit: float):
        with self._lock:
            category = self.categories.get(name)
            if category is None:
                raise CategoryError(f"Категорія '{name}' не існує в бюджеті.")
            category.monthly_limit = limit

    # ШІ: Claude (Sonnet 5.5) – чернетка методу update_category() за специфікацією студента (п. 4.1 завдання).
    # Змінено: перевірено тестами tests/test_budget.py; студент має самостійно пояснити логіку перейменування.
    def update_category(self, name: str, new_name: str, limit: float):
        """Редагування категорії: нова назва (транзакції переходять разом із нею) та місячний ліміт."""
        with self._lock:
            old = self.categories.get(name)
            if old is None:
                raise CategoryError(f"Категорія '{name}' не існує в бюджеті.")
            new = Category(new_name, old.cat_type, limit)  # валідація назви та ліміту
            if new.name != name and new.name in self.categories:
                raise CategoryError(f"Категорія '{new.name}' вже існує.")
            # словник перебудовується, щоб категорія залишилась на своєму місці в списку
            self.categories = {(new.name if key == name else key): (new if key == name else value)
                               for key, value in self.categories.items()}
            if new.name != name:
                for t in self.transactions:
                    if t.category_name == name:
                        t.category_name = new.name

    # ШІ: Claude (Sonnet 5.5) – чернетка методу remove_category() за специфікацією студента (п. 4.1 завдання).
    # Змінено: перевірено тестами tests/test_budget.py.
    def remove_category(self, name: str):
        """Видалення категорії; заборонене, якщо в ній є транзакції (щоб не втратити цілісність даних)."""
        with self._lock:
            if name not in self.categories:
                raise CategoryError(f"Категорія '{name}' не існує в бюджеті.")
            used = sum(1 for t in self.transactions if t.category_name == name)
            if used:
                raise CategoryError(f"Категорію '{name}' неможливо видалити: у ній {used} транзакцій. "
                                    f"Спочатку видаліть або перенесіть їх.")
            del self.categories[name]

    # ---------- Транзакції ----------
    def _validate_category(self, transaction: Transaction):
        category = self.categories.get(transaction.category_name)
        if category is None:
            raise CategoryError(f"Категорія '{transaction.category_name}' не існує в бюджеті.")
        if category.cat_type != transaction.kind:
            raise CategoryError(f"Категорія '{category.name}' не підходить для цього типу операції.")

    def next_transaction_id(self) -> int:
        with self._lock:
            return max(self._by_id, default=0) + 1

    def get_transaction(self, trans_id: int):
        return self._by_id.get(trans_id)

    def add_transaction(self, transaction: Transaction):
        with self._lock:
            self._validate_category(transaction)
            if transaction.trans_id in self._by_id:
                raise ValidationError(f"Транзакція з ID {transaction.trans_id} вже існує.")
            self.transactions.append(transaction)
            self._by_id[transaction.trans_id] = transaction

    def replace_transaction(self, trans_id: int, new_transaction: Transaction):
        """Заміна транзакції (тип може змінитись: Income <-> Expense) зі збереженням позиції та ID."""
        with self._lock:
            old = self._by_id.get(trans_id)
            if old is None:
                raise ValidationError(f"Транзакцію з ID {trans_id} не знайдено.")
            if new_transaction.trans_id != trans_id:
                raise ValidationError("ID транзакції змінювати не можна.")
            self._validate_category(new_transaction)
            index = self.transactions.index(old)
            self.transactions[index] = new_transaction
            self._by_id[trans_id] = new_transaction

    def remove_transaction(self, trans_id: int):
        with self._lock:
            old = self._by_id.pop(trans_id, None)
            if old is None:
                raise ValidationError(f"Транзакцію з ID {trans_id} не знайдено.")
            self.transactions.remove(old)

    def snapshot(self, month: str | None = None) -> list[Transaction]:
        """Копія списку транзакцій (за місяць РРРР-ММ або всіх) — безпечна для читання з фонового потоку."""
        with self._lock:
            if month is None:
                return list(self.transactions)
            return [t for t in self.transactions if t.date_str[:7] == month]

    # ---------- Звіти та аналітика ----------
    def get_months(self) -> list[str]:
        """Список місяців (РРРР-ММ), у яких є транзакції; нові — першими."""
        return sorted({t.date_str[:7] for t in self.snapshot()}, reverse=True)

    def get_persons(self) -> list[str]:
        """Унікальні імена користувачів (за алфавітом)."""
        return sorted({t.person for t in self.snapshot() if t.person}, key=str.lower)

    def get_monthly_summary(self) -> list[dict]:
        """Підсумки по місяцях (за зростанням): доходи, витрати, баланс, кількість записів та користувачів."""
        months: dict[str, dict] = {}
        for t in self.snapshot():
            key = t.date_str[:7]
            row = months.get(key)
            if row is None:
                row = months[key] = {"month": key, "income": 0.0, "expense": 0.0, "count": 0, "_people": set()}
            row["income" if t.kind == "Income" else "expense"] += t.amount
            row["count"] += 1
            if t.person:
                row["_people"].add(t.person)
        result = []
        for key in sorted(months):
            row = months[key]
            row["people"] = len(row.pop("_people"))
            row["balance"] = row["income"] - row["expense"]
            result.append(row)
        return result

    def get_expenses_by_category(self, month: str | None = None) -> dict[str, float]:
        """Сума витрат за категоріями (за весь час або за місяць РРРР-ММ)."""
        result: dict[str, float] = {}
        for t in self.snapshot(month):
            if t.kind == "Expense":
                result[t.category_name] = result.get(t.category_name, 0.0) + t.amount
        return result

    # ШІ: Claude (Sonnet 5.5) – чернетка трьох методів розрахунку звіту частинами (summarize_chunk, merge_parts,
    # build_report) та get_report_data() за специфікацією студента (п. 4.4 і 6 завдання).
    # Змінено: баланс рахується поліморфно через apply_to(); ліміти перевіряються лише для конкретного місяця
    # і з округленням до копійок; перевірено тестами tests/test_budget.py та benchmark.py.
    @staticmethod
    def summarize_chunk(chunk: list[Transaction]) -> dict:
        """Часткові підсумки для однієї частини списку (виконується в потоці; змінних спільних даних не має)."""
        income = expense = balance = 0.0
        by_category: dict[str, float] = {}
        for t in chunk:
            balance = t.apply_to(balance)       # поліморфізм: Income додає, Expense віднімає
            if t.kind == "Income":
                income += t.amount
            else:
                expense += t.amount
                by_category[t.category_name] = by_category.get(t.category_name, 0.0) + t.amount
        return {"income": income, "expense": expense, "balance": balance, "by_category": by_category}

    @staticmethod
    def merge_parts(parts: list[dict]) -> dict:
        """Об'єднує часткові підсумки в загальний."""
        total = {"income": 0.0, "expense": 0.0, "balance": 0.0, "by_category": {}, "count": 0}
        for part in parts:
            total["income"] += part["income"]
            total["expense"] += part["expense"]
            total["balance"] += part["balance"]
            for name, amount in part["by_category"].items():
                total["by_category"][name] = total["by_category"].get(name, 0.0) + amount
        return total

    def build_report(self, totals: dict, month: str | None, count: int) -> dict:
        """Формує підсумковий звіт із загальних сум та перевіряє місячні ліміти категорій."""
        spent = {name: round(amount, 2) for name, amount in
                 sorted(totals["by_category"].items(), key=lambda item: item[1], reverse=True)}
        with self._lock:
            limits = {name: cat.monthly_limit for name, cat in self.categories.items()}

        overlimit = {}
        if month is not None:  # місячний ліміт має сенс порівнювати лише з витратами за конкретний місяць
            for name, amount in spent.items():
                limit = limits.get(name, 0.0)
                if limit > 0 and amount > limit:
                    overlimit[name] = {"spent": amount, "limit": limit, "exceeded_by": round(amount - limit, 2)}

        return {
            "month": month,
            "transaction_count": count,
            "balance": round(totals["balance"], 2),
            "total_income": round(totals["income"], 2),
            "total_expense": round(totals["expense"], 2),
            "spent_by_category": spent,
            "limits": {name: limits.get(name, 0.0) for name in spent},
            "limits_checked": month is not None,
            "overlimit_categories": overlimit,
        }

    def get_report_data(self, month: str | None = None, progress=None) -> dict:
        """
        Розрахунок звіту послідовно по частинах (CHUNK_SIZE записів).
        progress(done, total) — необов'язкова функція зворотного виклику для індикатора виконання.
        """
        transactions = self.snapshot(month)
        total = len(transactions)
        parts = []
        for start in range(0, total, self.CHUNK_SIZE):
            parts.append(self.summarize_chunk(transactions[start:start + self.CHUNK_SIZE]))
            if progress:
                progress(min(start + self.CHUNK_SIZE, total), total)
        return self.build_report(self.merge_parts(parts), month, total)
