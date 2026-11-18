"""
Власні віджети на стандартному Tkinter/ttk (сторонні бібліотеки на кшталт tkcalendar не потрібні):
  * DateEntry      — поле дати з кнопкою «📅»;
  * CalendarPopup  — випадаючий календар з навігацією по місяцях і роках.
Також тут лежать допоміжні функції для роботи з назвами місяців.
"""
import tkinter as tk
from tkinter import ttk
from datetime import date, datetime, timedelta

from theme import theme, FONT

MONTH_NAMES = ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
               "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"]
MONTH_SHORT = ["Січ", "Лют", "Бер", "Кві", "Тра", "Чер", "Лип", "Сер", "Вер", "Жов", "Лис", "Гру"]
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]


def month_label(key: str) -> str:
    """'2026-10' -> 'Жовтень 2026'."""
    year, month = key.split("-")
    return f"{MONTH_NAMES[int(month) - 1]} {year}"


def shift_month(key: str, delta: int) -> str:
    """Зсув місяця РРРР-ММ на delta місяців (від'ємне — назад)."""
    year, month = (int(x) for x in key.split("-"))
    index = year * 12 + (month - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


class CalendarPopup(tk.Toplevel):
    """Календар для вибору дати. Після вибору викликає on_pick('РРРР-ММ-ДД') і закривається."""

    MIN_YEAR, MAX_YEAR = 1900, 2100

    def __init__(self, anchor, initial: str, on_pick):
        super().__init__(anchor)
        p = theme.p
        self.anchor = anchor
        self.on_pick = on_pick
        self._day_buttons = []

        self.title("Оберіть дату")
        self.configure(bg=p["surface"])
        self.resizable(False, False)
        self.transient(anchor.winfo_toplevel())
        theme.style_titlebar(self)

        try:
            self.selected = datetime.strptime(initial.strip(), "%Y-%m-%d").date()
        except ValueError:
            self.selected = date.today()
        self.view_year, self.view_month = self.selected.year, self.selected.month

        body = ttk.Frame(self, style="Card.TFrame", padding=14)
        body.pack()

        # Навігація: « ‹ Місяць Рік › »
        nav = ttk.Frame(body, style="Card.TFrame")
        nav.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(nav, text="«", style="Nav.TButton", width=2, command=lambda: self._shift(-12)).pack(side=tk.LEFT)
        ttk.Button(nav, text="‹", style="Nav.TButton", width=2, command=lambda: self._shift(-1)).pack(side=tk.LEFT)
        self.lbl_title = ttk.Label(nav, text="", style="Card.TLabel", anchor=tk.CENTER, font=(FONT, 11, "bold"))
        self.lbl_title.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(nav, text="›", style="Nav.TButton", width=2, command=lambda: self._shift(1)).pack(side=tk.LEFT)
        ttk.Button(nav, text="»", style="Nav.TButton", width=2, command=lambda: self._shift(12)).pack(side=tk.LEFT)

        # Сітка днів
        self.grid_frame = ttk.Frame(body, style="Card.TFrame")
        self.grid_frame.pack()
        for col, name in enumerate(WEEKDAYS):
            ttk.Label(self.grid_frame, text=name, style="CardMuted.TLabel", anchor=tk.CENTER, width=4).grid(
                row=0, column=col, pady=(0, 4))

        footer = ttk.Frame(body, style="Card.TFrame")
        footer.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(footer, text="Сьогодні", command=lambda: self._pick(date.today())).pack(side=tk.LEFT)
        ttk.Button(footer, text="Закрити", command=self._close).pack(side=tk.RIGHT)

        self._render()
        self._place()
        self.bind("<Escape>", lambda e: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.grab_set()
        self.focus_set()

    # ---------- Логіка ----------
    def _shift(self, months: int):
        index = self.view_year * 12 + (self.view_month - 1) + months
        year = index // 12
        if not self.MIN_YEAR <= year <= self.MAX_YEAR:
            return
        self.view_year, self.view_month = year, index % 12 + 1
        self._render()

    def _render(self):
        for btn in self._day_buttons:
            btn.destroy()
        self._day_buttons = []
        self.lbl_title.config(text=f"{MONTH_NAMES[self.view_month - 1]} {self.view_year}")

        first = date(self.view_year, self.view_month, 1)
        start = first - timedelta(days=first.weekday())  # тиждень починається з понеділка
        today = date.today()
        for i in range(42):  # завжди 6 рядків — вікно не «стрибає»
            d = start + timedelta(days=i)
            if d == self.selected:
                style_name = "Selected.Day.TButton"
            elif d == today:
                style_name = "Today.Day.TButton"
            elif d.month != self.view_month:
                style_name = "Muted.Day.TButton"
            else:
                style_name = "Day.TButton"
            btn = ttk.Button(self.grid_frame, text=str(d.day), width=4, style=style_name,
                             command=lambda day=d: self._pick(day))
            btn.grid(row=1 + i // 7, column=i % 7, padx=1, pady=1)
            self._day_buttons.append(btn)

    def _pick(self, chosen: date):
        self.on_pick(chosen.strftime("%Y-%m-%d"))
        self._close()

    def _close(self):
        top = self.anchor.winfo_toplevel()
        self.destroy()
        try:
            top.grab_set()  # повертаємо модальність батьківському вікну (grab зникає разом із календарем)
        except tk.TclError:
            pass

    def _place(self):
        """Показує календар під полем дати (або над ним, якщо внизу немає місця)."""
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = self.anchor.winfo_rootx()
        y = self.anchor.winfo_rooty() + self.anchor.winfo_height() + 4
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        if x + w > screen_w - 10:
            x = screen_w - w - 10
        if y + h > screen_h - 60:
            y = max(10, self.anchor.winfo_rooty() - h - 4)
        self.geometry(f"+{max(0, int(x))}+{int(y)}")


class DateEntry(ttk.Frame):
    """Поле дати формату РРРР-ММ-ДД з кнопкою відкриття календаря."""

    def __init__(self, parent, value: str = ""):
        super().__init__(parent, style="Card.TFrame")
        self.entry = ttk.Entry(self, width=18)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.insert(0, value)
        self.button = ttk.Button(self, text="📅", style="Chip.TButton", width=3, command=self.open_calendar)
        self.button.pack(side=tk.LEFT, padx=(6, 0))

    def get(self) -> str:
        return self.entry.get()

    def set(self, value: str):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, value)

    def open_calendar(self):
        CalendarPopup(self.entry, self.get(), self.set)
