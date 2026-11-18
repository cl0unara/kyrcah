"""
Спільні для всіх вікон (View) константи та допоміжні функції відображення.
Бізнес-логіки тут немає: форматування чисел, підписи типів, «картки» та опитування черги через after().
"""
import math
import tkinter as tk
from tkinter import ttk

from controller import FINAL_EVENTS
from theme import theme

POLL_INTERVAL_MS = 100   # як часто головне вікно опитує queue.Queue

# Типи категорій: користувач бачить українські назви, а контролер/модель працюють із "Expense"/"Income"
TYPE_LABELS = {"Expense": "Витрата", "Income": "Дохід"}
KIND_BY_LABEL = {label: kind for kind, label in TYPE_LABELS.items()}

# Типи транзакцій (ключ = ім'я класу моделі)
TRANSACTION_TYPES = {"Expense": "Витрата", "RegularExpense": "Регулярна витрата", "Income": "Дохід"}
TRANSACTION_TYPE_BY_LABEL = {label: key for key, label in TRANSACTION_TYPES.items()}

# Періодичність регулярної витрати
FREQUENCY_LABELS = {"weekly": "Щотижня", "monthly": "Щомісяця", "yearly": "Щороку"}
FREQUENCY_BY_LABEL = {label: key for key, label in FREQUENCY_LABELS.items()}


def category_kind(t_type: str) -> str:
    """До якого типу категорій належить тип транзакції (регулярна витрата — це витрата)."""
    return "Income" if t_type == "Income" else "Expense"


def fmt_money(value: float) -> str:
    return f"{value:,.2f} грн".replace(",", " ")


def fmt_compact(value: float) -> str:
    """Короткий запис для осі графіка: 12.5k, 1.2M."""
    a = abs(value)
    if a >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if a >= 1_000:
        return f"{value / 1_000:.1f}k".replace(".0k", "k")
    return f"{value:.0f}"


def nice_ticks(max_value: float, count: int = 4):
    """Гарний крок осі: повертає (крок, кількість поділок), крок*кількість >= max_value."""
    raw = max_value / count
    magnitude = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * magnitude:
            return m * magnitude, count
    return 10 * magnitude, count


def make_card(parent):
    """Картка з тонкою рамкою: зовнішній Border.TFrame + внутрішній Card.TFrame. Повертає (рамка, вміст)."""
    border = ttk.Frame(parent, style="Border.TFrame", padding=1)
    inner = ttk.Frame(border, style="Card.TFrame")
    inner.pack(fill=tk.BOTH, expand=True)
    return border, inner


def make_stat_card(parent, column: int, title: str, kind: str):
    """Картка-підсумок із кольоровою смужкою зліва (kind: Income / Expense / Balance). Повертає мітку зі значенням."""
    border = ttk.Frame(parent, style="Border.TFrame", padding=1)
    border.grid(row=0, column=column, sticky="nsew",
                padx=(0 if column == 0 else 8, 0 if column == 2 else 8))
    inner = ttk.Frame(border, style="Card.TFrame")
    inner.pack(fill=tk.BOTH, expand=True)

    ttk.Frame(inner, style=f"{kind}.Stripe.TFrame", width=4).pack(side=tk.LEFT, fill=tk.Y)
    body = ttk.Frame(inner, style="Card.TFrame", padding=(18, 16))
    body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    ttk.Label(body, text=title, style="CardMuted.TLabel").pack(anchor=tk.W)
    value = ttk.Label(body, text="0.00 грн", style=f"{kind}.Value.TLabel")
    value.pack(anchor=tk.W, pady=(6, 0))
    return value


def style_tree_tags(tree: ttk.Treeview):
    """Кольори рядків-«зебри» (залежать від поточної теми)."""
    p = theme.p
    tree.tag_configure("even", background=p["surface"])
    tree.tag_configure("odd", background=p["row_alt"])


def poll_until_done(scheduler, controller, on_event):
    """
    Опитування черги через after() у головному потоці (п. 4.4 завдання): кожні POLL_INTERVAL_MS забирає
    повідомлення фонового потоку, передає їх у on_event(вид, дані) і зупиняється після завершального повідомлення.
    scheduler — вікно, яке живе, доки триває задача (головне вікно), тож закриття діалогу цикл не зупиняє.
    """

    def tick():
        finished = False
        for kind, payload in controller.poll():
            on_event(kind, payload)
            finished = finished or kind in FINAL_EVENTS
        if not finished:
            scheduler.after(POLL_INTERVAL_MS, tick)

    scheduler.after(POLL_INTERVAL_MS, tick)
