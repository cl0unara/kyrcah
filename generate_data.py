"""
Генератор тестових даних (НЕ входить до самого застосунку).

    python generate_data.py budget.json --count 120 --days 90      # невеликий файл (не менше 50 записів)
    python generate_data.py test_10000.json --count 10000          # великий набір для фонового імпорту

Результат відтворюваний (--seed). Об'єднує колишні generate_data.py та enrich_data.py.
"""
import argparse
import json
import random
import sys
from datetime import date, datetime, timedelta

from models import DEFAULT_CATEGORIES
from sample_data import make_people, random_description

# Орієнтовні діапазони сум за категоріями
AMOUNT_RANGES = {
    "Продукти": (80, 2500), "Комунальні": (400, 3200), "Транспорт": (30, 1800), "Розваги": (100, 2800),
    "Кафе та ресторани": (90, 2200), "Здоров'я та спорт": (150, 2500), "Покупки / Одяг": (300, 4500),
    "Техніка": (400, 12000), "Зв'язок та інтернет": (150, 450), "Освіта": (300, 3500), "Подорожі": (500, 6000),
    "Дім та ремонт": (150, 4000), "Краса та догляд": (200, 1800), "Побутова хімія": (60, 700),
    "Тварини": (100, 1500), "Благодійність": (50, 1500), "Інші витрати": (50, 1500),
    "Зарплата": (12000, 32000), "Фріланс / Бонуси": (1500, 15000), "Інвестиції": (200, 6000),
    "Подарунки": (300, 5000), "Підробіток": (300, 3500), "Стипендія / Допомога": (1000, 3500),
    "Відсотки / Кешбек": (30, 800), "Продаж речей": (200, 9000), "Повернення боргів": (200, 5000),
    "Інші доходи": (100, 2000),
}
REGULAR_CATEGORIES = {"Комунальні", "Зв'язок та інтернет"}


def pick_person(people: list[str], rng: random.Random) -> str:
    """Користувачі «активні» нерівномірно: перші в списку трапляються частіше."""
    return people[min(int(rng.expovariate(3.0) * len(people)), len(people) - 1)]


def make_created_at(date_str: str, rng: random.Random) -> str:
    """Запис зазвичай створюється в день операції, іноді — наступного дня (внесли із запізненням)."""
    day = datetime.strptime(date_str, "%Y-%m-%d")
    if rng.random() < 0.15:
        day += timedelta(days=rng.randint(1, 3))
    return day.replace(hour=rng.randint(7, 23), minute=rng.randint(0, 59),
                       second=rng.randint(0, 59)).strftime("%Y-%m-%d %H:%M:%S")


def generate(count: int, days: int = 548, end: date | None = None, seed: int = 42) -> dict:
    rng = random.Random(seed)
    categories = [{"name": n, "type": k, "monthly_limit": lim} for n, k, lim in DEFAULT_CATEGORIES]
    income_cats = [c["name"] for c in categories if c["type"] == "Income"]
    expense_cats = [c["name"] for c in categories if c["type"] == "Expense"]
    # Зарплата частіше за інші доходи, продукти й транспорт частіше за інші витрати
    income_weights = [10 if n == "Зарплата" else 1 for n in income_cats]
    expense_weights = [6 if n in ("Продукти", "Транспорт") else 3 if n in ("Кафе та ресторани", "Комунальні")
                       else 1 for n in expense_cats]

    end = end or date.today()
    people = make_people(max(5, min(250, count // 50)), rng)

    transactions = []
    for trans_id in range(1, count + 1):
        is_income = rng.random() < 0.12
        category = rng.choices(income_cats if is_income else expense_cats,
                               weights=income_weights if is_income else expense_weights)[0]
        low, high = AMOUNT_RANGES.get(category, (50, 1500))
        day = (end - timedelta(days=rng.randint(0, days))).strftime("%Y-%m-%d")
        kind = "Income" if is_income else "Expense"
        record = {
            "trans_id": trans_id,
            "type": "RegularExpense" if category in REGULAR_CATEGORIES else kind,
            "amount": round(rng.uniform(low, high), 2),
            "date": day,
            "category": category,
            "description": random_description(category, kind, int(day[5:7]), rng),
            "person": pick_person(people, rng),
            "created_at": make_created_at(day, rng),
        }
        if record["type"] == "RegularExpense":
            record["frequency"] = "monthly"
        transactions.append(record)

    return {"categories": categories, "transactions": transactions}


def main():
    parser = argparse.ArgumentParser(description="Генерація тестових даних для застосунку «Домашній бюджет»")
    parser.add_argument("output", help="вихідний JSON-файл")
    parser.add_argument("--count", type=int, default=10000, help="кількість транзакцій (за замовчуванням 10000)")
    parser.add_argument("--days", type=int, default=548, help="за скільки останніх днів (за замовчуванням 548)")
    parser.add_argument("--end", help="остання дата РРРР-ММ-ДД (за замовчуванням сьогодні)")
    parser.add_argument("--seed", type=int, default=42, help="зерно генератора випадкових чисел")
    args = parser.parse_args()

    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else None
    data = generate(args.count, args.days, end, args.seed)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Згенеровано {len(data['transactions'])} записів -> {args.output}")


if __name__ == "__main__":
    sys.exit(main())
