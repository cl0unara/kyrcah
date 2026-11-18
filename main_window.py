import logging
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from analytics_window import AnalyticsWindow
from controller import BudgetController
from dialogs import TransactionDialog, CategoryManagerWindow
from errors import BudgetError
from report_window import ReportWindow
from theme import theme, FONT
from view_common import fmt_money, make_card, make_stat_card, poll_until_done, style_tree_tags
from widgets import month_label

APP_TITLE = "ПЗ для складання домашнього бюджету"
SEARCH_DELAY_MS = 250
ALL_MONTHS = "Усі місяці"
ALL_CATEGORIES = "Усі категорії"

# ---------- Таблиця транзакцій: колонки та сортування ----------
COLUMNS = ("id", "type", "amount", "date", "category", "person", "description", "created")
HEADINGS = {"id": "ID", "type": "ТИП", "amount": "СУМА", "date": "ДАТА", "category": "КАТЕГОРІЯ",
            "person": "КОРИСТУВАЧ", "description": "ОПИС", "created": "СТВОРЕНО"}
# (ширина, розтягується, вирівнювання)
COLUMN_LAYOUT = {
    "id": (60, False, tk.CENTER), "type": (150, False, tk.CENTER), "amount": (140, False, tk.E),
    "date": (100, False, tk.CENTER), "category": (160, False, tk.W), "person": (170, False, tk.W),
    "description": (240, True, tk.W), "created": (140, False, tk.CENTER),
}
# Напрямок за першого кліку по колонці: True — від більшого/новішого до меншого
FIRST_CLICK_DESC = {"id": False, "type": False, "amount": True, "date": True, "category": False,
                    "person": False, "description": False, "created": True}


class BudgetApp(tk.Tk):
    """Головне вікно застосунку (View). Містить лише відображення; уся логіка — у BudgetController."""

    def __init__(self, controller: BudgetController):
        super().__init__()
        self.controller = controller
        self._silent_import = False
        self._search_job = None
        self._month_key = None                 # обраний місяць РРРР-ММ або None (усі місяці)
        self._month_map = {ALL_MONTHS: None}   # підпис у списку -> ключ місяця
        self._category_key = None              # обрана категорія або None (усі категорії)
        self._sort_col, self._sort_desc = "date", True

        self.title(APP_TITLE)
        self.geometry("1260x780")
        self.minsize(1140, 640)

        theme.set_mode(self, controller.get_setting("theme", "dark"))
        self._create_widgets()
        theme.subscribe(self._on_theme_changed)
        self._on_theme_changed()
        self.refresh_table()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<Control-s>", lambda e: self.save_changes())
        self.bind("<Control-t>", lambda e: self.toggle_theme())

        # Підхоплюємо збережений стан із budget.json (у фоновому потоці)
        if self.controller.has_saved_file():
            self.start_import(self.controller.data_file, silent=True)

    def report_callback_exception(self, exc, val, tb):
        """Помилки в обробниках подій: помилку введення показуємо користувачу, непередбачену — пишемо в журнал."""
        if isinstance(val, BudgetError):
            messagebox.showerror("Помилка", str(val))
            return
        logging.error("Непередбачена помилка інтерфейсу", exc_info=(exc, val, tb))
        messagebox.showerror("Внутрішня помилка", "Сталася непередбачена помилка. Подробиці записано в budget.log.")

    # ---------- Віджети ----------
    def _create_widgets(self):
        """Створення та компонування блоків інтерфейсу."""
        # ----- Шапка -----
        header = ttk.Frame(self, style="TFrame")
        header.pack(fill=tk.X, padx=24, pady=(22, 14))

        title_box = ttk.Frame(header, style="TFrame")
        title_box.pack(side=tk.LEFT)
        ttk.Label(title_box, text="💰 Домашній бюджет", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(title_box, text="Облік доходів, витрат і місячних лімітів", style="Muted.TLabel").pack(
            anchor=tk.W, pady=(2, 0))

        btn_frame = ttk.Frame(header, style="TFrame")
        btn_frame.pack(side=tk.RIGHT)
        self.btn_theme = ttk.Button(btn_frame, text="🌙", style="Ghost.TButton", command=self.toggle_theme)
        self.btn_import = ttk.Button(btn_frame, text="📁 Імпорт JSON", command=self.import_json_async)
        self.btn_export = ttk.Button(btn_frame, text="📤 Експорт JSON", command=self.export_json)
        self.btn_report = ttk.Button(btn_frame, text="📋 Місячний звіт", command=self.open_report)
        self.btn_save = ttk.Button(btn_frame, text="💾 Зберегти зміни", command=self.save_changes)
        self.btn_add = ttk.Button(btn_frame, text="➕ Додати транзакцію", style="Accent.TButton",
                                  command=self.open_add_dialog)
        self.btn_theme.pack(side=tk.LEFT, padx=(0, 8))
        for btn in (self.btn_import, self.btn_export, self.btn_report, self.btn_save):
            btn.pack(side=tk.LEFT, padx=4)
        self.btn_add.pack(side=tk.LEFT, padx=(8, 0))

        # ----- Панель фільтрів (місяць, категорія) -----
        period = ttk.Frame(self, style="TFrame")
        period.pack(fill=tk.X, padx=24, pady=(0, 10))
        ttk.Label(period, text="Місяць:", style="Muted.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        self.btn_prev = ttk.Button(period, text="‹", style="Ghost.TButton", width=2,
                                   command=lambda: self._shift_month(1))
        self.cb_month = ttk.Combobox(period, state="readonly", width=20)
        self.btn_next = ttk.Button(period, text="›", style="Ghost.TButton", width=2,
                                   command=lambda: self._shift_month(-1))
        self.btn_prev.pack(side=tk.LEFT)
        self.cb_month.pack(side=tk.LEFT, padx=4)
        self.btn_next.pack(side=tk.LEFT)
        self.cb_month.bind("<<ComboboxSelected>>", self._on_month_selected)

        ttk.Label(period, text="Категорія:", style="Muted.TLabel").pack(side=tk.LEFT, padx=(24, 8))
        self.cb_category = ttk.Combobox(period, state="readonly", width=24)
        self.cb_category.pack(side=tk.LEFT)
        self.cb_category.bind("<<ComboboxSelected>>", self._on_category_selected)

        self.lbl_count = ttk.Label(period, text="", style="Muted.TLabel")
        self.lbl_count.pack(side=tk.RIGHT)

        # ----- Картки-підсумки (за обраний місяць) -----
        dash = ttk.Frame(self, style="TFrame")
        dash.pack(fill=tk.X, padx=24, pady=(0, 14))
        for col in range(3):
            dash.columnconfigure(col, weight=1, uniform="stat")
        self.lbl_inc_val = make_stat_card(dash, 0, "ДОХІД", "Income")
        self.lbl_exp_val = make_stat_card(dash, 1, "ВИТРАТИ", "Expense")
        self.lbl_bal_val = make_stat_card(dash, 2, "БАЛАНС", "Balance")

        # ----- Пошук та дії над таблицею -----
        tool_border, tool_inner = make_card(self)
        tool_border.pack(fill=tk.X, padx=24, pady=(0, 10))
        tool_bar = ttk.Frame(tool_inner, style="Card.TFrame", padding=10)
        tool_bar.pack(fill=tk.X)

        ttk.Label(tool_bar, text="🔍", style="Card.TLabel", font=(FONT, 11)).pack(side=tk.LEFT, padx=(4, 8))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._schedule_refresh())
        ttk.Entry(tool_bar, textvariable=self.search_var, width=36).pack(side=tk.LEFT)

        tools = ttk.Frame(tool_bar, style="Card.TFrame")
        tools.pack(side=tk.RIGHT)
        self.btn_analytics = ttk.Button(tools, text="📈 Аналітика", command=self.open_analytics)
        self.btn_categories = ttk.Button(tools, text="🗂 Категорії", command=self.open_categories)
        self.btn_edit = ttk.Button(tools, text="✏️ Редагувати", command=self.edit_selected)
        self.btn_delete = ttk.Button(tools, text="🗑 Видалити", style="Danger.TButton", command=self.delete_selected)
        for btn in (self.btn_analytics, self.btn_categories, self.btn_edit, self.btn_delete):
            btn.pack(side=tk.LEFT, padx=3)

        # Кнопки, які блокуються під час фонового імпорту
        self._action_buttons = [self.btn_import, self.btn_export, self.btn_report, self.btn_save, self.btn_add,
                                self.btn_analytics, self.btn_categories, self.btn_prev, self.btn_next]

        # ----- Індикатор виконання (видно лише під час імпорту) -----
        self.progress_holder = ttk.Frame(self, style="TFrame", height=4)
        self.progress_holder.pack(fill=tk.X, padx=24, pady=(0, 6))
        self.progress_holder.pack_propagate(False)
        self.progress = ttk.Progressbar(self.progress_holder, mode="determinate", maximum=100)

        # ----- Таблиця -----
        table_border, table_inner = make_card(self)
        table_border.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 24))

        self.tree = ttk.Treeview(table_inner, columns=COLUMNS, show="headings", style="Treeview",
                                 selectmode="browse")
        for col in COLUMNS:
            width, stretch, anchor = COLUMN_LAYOUT[col]
            # Клік по заголовку — сортування за цією колонкою
            self.tree.heading(col, text=HEADINGS[col], anchor=anchor, command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=width, minwidth=50, stretch=stretch, anchor=anchor)
        self._update_headings()

        scrollbar = ttk.Scrollbar(table_inner, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.lbl_empty = ttk.Label(table_inner, text="", style="Empty.TLabel", justify=tk.CENTER)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Delete>", lambda e: self.delete_selected())

        self._on_select()

    # ---------- Тема ----------
    def toggle_theme(self):
        theme.toggle(self)
        self.controller.set_setting("theme", theme.mode)

    def _on_theme_changed(self):
        style_tree_tags(self.tree)
        self.btn_theme.config(text="☀" if theme.mode == "dark" else "🌙")
        theme.style_titlebar(self)

    # ---------- Сортування ----------
    def _sort_by(self, col: str):
        if col == self._sort_col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col
            self._sort_desc = FIRST_CLICK_DESC[col]
        self._update_headings()
        self.refresh_table()

    def _update_headings(self):
        for col in COLUMNS:
            title = HEADINGS[col]
            if col == self._sort_col:
                title += " ▼" if self._sort_desc else " ▲"
            self.tree.heading(col, text=title)

    # ---------- Фільтри: місяць і категорія ----------
    def _sync_month_combo(self):
        months = self.controller.get_months()  # від нових до старих
        self._month_map = {ALL_MONTHS: None}
        for key in months:
            self._month_map[month_label(key)] = key
        self.cb_month["values"] = list(self._month_map)
        if self._month_key not in months:
            self._month_key = None
        self.cb_month.set(ALL_MONTHS if self._month_key is None else month_label(self._month_key))

    def _sync_category_combo(self):
        names = [c.name for c in self.controller.get_categories()]
        self.cb_category["values"] = [ALL_CATEGORIES] + names
        if self._category_key not in names:
            self._category_key = None
        self.cb_category.set(ALL_CATEGORIES if self._category_key is None else self._category_key)

    def _on_month_selected(self, _event=None):
        self._month_key = self._month_map.get(self.cb_month.get())
        self.refresh_table()

    def _on_category_selected(self, _event=None):
        value = self.cb_category.get()
        self._category_key = None if value == ALL_CATEGORIES else value
        self.refresh_table()

    def _shift_month(self, direction: int):
        """direction=+1 — до попереднього (старішого) місяця, -1 — до наступного (новішого)."""
        months = self.controller.get_months()
        if not months:
            return
        if self._month_key not in months:
            self._month_key = months[0]
        else:
            index = min(max(months.index(self._month_key) + direction, 0), len(months) - 1)
            self._month_key = months[index]
        self.refresh_table()

    # ---------- Оновлення відображення ----------
    def _update_title(self):
        self.title(APP_TITLE + (" *" if self.controller.dirty else ""))

    def _schedule_refresh(self):
        """Пошук із затримкою: таблиця перебудовується, коли користувач зробив паузу в наборі."""
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(SEARCH_DELAY_MS, self._run_scheduled_refresh)

    def _run_scheduled_refresh(self):
        self._search_job = None
        self.refresh_table()

    def refresh_table(self):
        """Оновлення дашборду та списку транзакцій (фільтри + пошук + сортування виконує контролер)."""
        selected = self.tree.selection()
        self._sync_month_combo()
        self._sync_category_combo()
        query = self.search_var.get().strip()

        rows, period_count = self.controller.find_transactions(
            self._month_key, self._category_key, query, self._sort_col, self._sort_desc)

        self.tree.delete(*self.tree.get_children())
        for i, t in enumerate(rows):
            is_income = t.kind == "Income"
            self.tree.insert(
                "",
                tk.END,
                iid=str(t.trans_id),
                values=(t.trans_id,
                        f"{'▲' if is_income else '▼'} {t.type_label}",
                        f"{'+' if is_income else '−'}{fmt_money(t.amount)}",
                        t.date_str, t.category_name, t.person or "—", t.description,
                        t.created_at[:16] or "—"),
                tags=("even" if i % 2 == 0 else "odd",)
            )

        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])

        # Порожній стан таблиці
        if not rows:
            has_data = self.controller.has_transactions()
            self.lbl_empty.config(text="Нічого не знайдено за вашим запитом" if has_data else
                                  "Транзакцій поки немає\nНатисніть «Додати транзакцію», щоб почати")
            self.lbl_empty.place(in_=self.tree, relx=0.5, rely=0.4, anchor=tk.CENTER)
        else:
            self.lbl_empty.place_forget()

        count_text = f"Записів: {len(rows)}"
        if query:
            count_text += f" із {period_count}"
        self.lbl_count.config(text=count_text)

        # Підсумки за обраний місяць
        summary = self.controller.get_summary(self._month_key)
        self.lbl_inc_val.config(text=fmt_money(summary["total_income"]))
        self.lbl_exp_val.config(text=fmt_money(summary["total_expense"]))
        bal_val = summary["balance"]
        self.lbl_bal_val.config(text=fmt_money(bal_val),
                                style="Balance.Value.TLabel" if bal_val >= 0 else "BalanceNeg.Value.TLabel")

        self._on_select()
        self._update_title()

    def _after_change(self):
        self.refresh_table()

    def _reveal(self, transaction):
        """Після додавання/редагування: показати місяць і категорію запису, виділити його в таблиці."""
        if transaction is None:
            return
        if self._month_key is not None:
            self._month_key = transaction.date_str[:7]
        if self._category_key is not None:
            self._category_key = transaction.category_name
        self.refresh_table()
        iid = str(transaction.trans_id)
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.see(iid)

    def _selected_id(self):
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    def _on_select(self, _event=None):
        enabled = bool(self.tree.selection()) and not self.controller.is_busy
        state = ["!disabled"] if enabled else ["disabled"]
        self.btn_edit.state(state)
        self.btn_delete.state(state)

    def _on_double_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell":
            self.edit_selected()

    def _set_busy(self, busy: bool):
        for btn in self._action_buttons:
            btn.state(["disabled"] if busy else ["!disabled"])
        self._on_select()

    # ---------- Асинхронний імпорт: потік -> Queue -> after() -> Progressbar ----------
    def import_json_async(self):
        file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if file_path:
            self.start_import(file_path)

    def start_import(self, file_path: str, silent: bool = False):
        if self.controller.is_busy:
            return
        self._silent_import = silent
        self._set_busy(True)
        self.progress.config(value=0)
        self.progress.pack(fill=tk.X)
        try:
            self.controller.start_import(file_path)
        except BudgetError as e:
            self._finish_loading_ui()
            messagebox.showerror("Помилка", str(e))
            return
        # UI оновлюється лише в головному потоці — через after()
        poll_until_done(self, self.controller, self._on_import_event)

    def _finish_loading_ui(self):
        self.progress.pack_forget()
        self._set_busy(False)

    def _on_import_event(self, kind: str, payload):
        if kind == "progress":
            self.progress.config(value=payload * 100)
        elif kind == "import_ok":
            self._finish_loading_ui()
            # Після завантаження великого файлу показуємо найновіший місяць (швидко й зручно)
            months = self.controller.get_months()
            self._month_key = months[0] if months else None
            self._category_key = None
            self.refresh_table()
            if not self._silent_import:
                messagebox.showinfo("Успіх", "Дані успішно імпортовано з фонового потоку!")
        elif kind == "import_error":
            self._finish_loading_ui()
            messagebox.showerror("Помилка", f"Не вдалося завантажити дані: {payload}")

    # ---------- Експорт / збереження ----------
    def export_json(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json")],
                                                 initialfile="budget_export.json")
        if not file_path:
            return
        try:
            self.controller.export_json(file_path)
        except BudgetError as e:
            messagebox.showerror("Помилка", str(e))
            return
        messagebox.showinfo("Успіх", f"Набір даних експортовано у файл:\n{file_path}")

    def save_changes(self) -> bool:
        """Кнопка «Зберегти зміни»: перезаписує budget.json поточним станом."""
        if self.controller.is_busy:
            return False
        try:
            path = self.controller.save()
        except BudgetError as e:
            messagebox.showerror("Помилка збереження", str(e))
            return False
        self._update_title()
        messagebox.showinfo("Збережено", f"Поточний стан записано у файл:\n{path}")
        return True

    def on_close(self):
        if self.controller.dirty and not self.controller.is_busy:
            answer = messagebox.askyesnocancel("Незбережені зміни", "Зберегти зміни перед виходом?")
            if answer is None:
                return
            if answer and not self.save_changes():
                return
        self.destroy()

    # ---------- Транзакції: додавання / редагування / видалення ----------
    def open_add_dialog(self):
        TransactionDialog(self, self.controller, on_submit=self._submit_add)

    def _submit_add(self, *data):
        self._reveal(self.controller.add_transaction(*data))

    def edit_selected(self):
        trans_id = self._selected_id()
        if trans_id is None or self.controller.is_busy:
            return
        transaction = self.controller.get_transaction(trans_id)
        if transaction is None:
            return
        TransactionDialog(self, self.controller,
                          on_submit=lambda *data: self._submit_edit(trans_id, *data),
                          transaction=transaction)

    def _submit_edit(self, trans_id, *data):
        self._reveal(self.controller.update_transaction(trans_id, *data))

    def delete_selected(self):
        trans_id = self._selected_id()
        if trans_id is None or self.controller.is_busy:
            return
        transaction = self.controller.get_transaction(trans_id)
        if transaction is None:
            return
        if not messagebox.askyesno(
                "Видалення транзакції",
                f"Видалити транзакцію #{trans_id}?\n\n{transaction.category_name}: {fmt_money(transaction.amount)} "
                f"({transaction.date_str})"):
            return
        self.controller.delete_transaction(trans_id)
        self._after_change()

    # ---------- Додаткові вікна ----------
    def open_categories(self):
        CategoryManagerWindow(self, self.controller, on_change=self._after_change)

    def open_analytics(self):
        AnalyticsWindow(self, self.controller, initial_month=self._month_key)

    def open_report(self):
        months = self.controller.get_months()
        if not months:
            messagebox.showinfo("Місячний звіт", "Немає даних для звіту. Додайте транзакції або імпортуйте файл.")
            return
        ReportWindow(self, self.controller, self._month_key or months[0])
