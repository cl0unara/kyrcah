"""
Порівняння розрахунку звіту в одному потоці та частинами в ThreadPoolExecutor (п. 6 завдання).

    python benchmark.py test_10000.json
    python benchmark.py test_10000.json --scale 100 --workers 1 2 4 8 --repeat 7

Прискорення S = T1 / Tn (формула 5.1 методичних вказівок), ефективність E = S / n (формула 5.2).
--scale N багаторазово повторює набір (10 000 x N записів): так видно, як змінюється результат зі зростанням обсягу.
"""
import argparse
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from data_manager import DataManager
from models import Budget


def split(items: list, parts: int) -> list[list]:
    """Ділить список на parts майже рівних частин."""
    size, extra = divmod(len(items), parts)
    result, start = [], 0
    for i in range(parts):
        end = start + size + (1 if i < extra else 0)
        result.append(items[start:end])
        start = end
    return result


def run_single(budget: Budget, transactions: list) -> dict:
    """T1: увесь список обробляє один потік (без пулу)."""
    return budget.build_report(Budget.merge_parts([Budget.summarize_chunk(transactions)]), None, len(transactions))


def run_pool(budget: Budget, transactions: list, workers: int) -> dict:
    """Tn: список ділиться на workers частин, кожну рахує окремий потік пулу, результати об'єднуються."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        parts = list(pool.map(Budget.summarize_chunk, split(transactions, workers)))
    return budget.build_report(Budget.merge_parts(parts), None, len(transactions))


def measure(func, repeat: int) -> float:
    """Медіана часу виконання, мс (перший прогін відкидається як «розігрівний»)."""
    func()
    times = []
    for _ in range(repeat):
        start = time.perf_counter()
        func()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", nargs="?", default="test_10000.json", help="JSON-файл із набором даних")
    parser.add_argument("--workers", type=int, nargs="+", default=[2, 4, 8], help="кількості потоків")
    parser.add_argument("--repeat", type=int, default=7, help="кількість вимірювань (береться медіана)")
    parser.add_argument("--scale", type=int, default=1, help="у скільки разів збільшити набір")
    args = parser.parse_args()

    budget = DataManager.load_from_json(args.file)
    transactions = budget.snapshot() * args.scale
    gil = "увімкнено" if getattr(sys, "_is_gil_enabled", lambda: True)() else "вимкнено (free-threaded збірка)"

    print(f"Python {sys.version.split()[0]}, GIL {gil}, логічних ядер: {os.cpu_count()}")
    print(f"Записів: {len(transactions)}, вимірювань: {args.repeat} (медіана)\n")

    expected = run_single(budget, transactions)
    t1 = measure(lambda: run_single(budget, transactions), args.repeat)
    print(f"{'Потоків n':>10} {'Tn, мс':>10} {'S = T1/Tn':>11} {'E = S/n':>9}")
    print(f"{1:>10} {t1:>10.2f} {1.0:>11.2f} {1.0:>9.2f}   (один потік, без пулу)")
    for n in args.workers:
        report = run_pool(budget, transactions, n)
        # суми з плаваючою комою залежать від порядку додавання, тому порівнюємо з точністю до копійки
        assert abs(report["balance"] - expected["balance"]) < 0.5 and report["spent_by_category"].keys() == \
               expected["spent_by_category"].keys(), "результат пулу не збігається з однопотоковим"
        tn = measure(lambda n=n: run_pool(budget, transactions, n), args.repeat)
        speedup = t1 / tn
        print(f"{n:>10} {tn:>10.2f} {speedup:>11.2f} {speedup / n:>9.2f}")


if __name__ == "__main__":
    main()
