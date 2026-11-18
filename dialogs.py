"""Модальні вікна: додавання/редагування транзакції та керування категоріями. Лише відображення та збір введення."""
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

from controller import BudgetController
from errors import BudgetError
from sample_data import description_hints
from theme import theme
from view_common import (TYPE_LABELS, KIND_BY_LABEL, TRANSACTION_TYPES, TRANSACTION_TYPE_BY_LABEL,
                         FREQUENCY_LABELS, FREQUENCY_BY_LABEL, category_kind, fmt_money, make_card,
                         style_tree_tags)
from widgets import DateEntry


# ======================================================================
#  Модальне вікно додавання / редагування транзакції
# ======================================================================
class TransactionDialog(tk.Toplevel):
    """Одне й те саме вікно для створення та редагування (якщо передано transaction)."""

    def __init__(self, parent, controller: BudgetController, on_submit, transaction=None):
        super().__init__(parent)
        self.controller = controller
        self.on_submit = on_submit
        editing = transaction is not None
        p = theme.p

        self.title("Редагування транзакції" if editing else "Нова транзакція")
        self.minsize(500, 1)          # висоту визначає вміст (коректно на будь-якому масштабі екрана)
        self.resizable(True, False)
        self.configure(bg=p["surface"])
        self.transient(parent)
        self.grab_set()
        theme.style_titlebar(self)

        body = ttk.Frame(self, style="Card.TFrame", padding=(28, 24, 28, 20))
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(body, text="Змініть дані транзакції" if editing else "Нова транзакція",
                  style="CardTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(body, text="Заповніть поля нижче та натисніть «Зберегти»",
                  style="CardMuted.TLabel").pack(anchor=tk.W, pady=(2, 14))

        form = ttk.Frame(body, style="Card.TFrame")
        form.pack(fill=tk.X)
        form.columnconfigure(1, weight=1)

        def label(text, row):
            lbl = ttk.Label(form, text=text, style="FieldLabel.TLabel")
            lbl.grid(row=row, column=0, sticky=tk.W, pady=8, padx=(0, 16))
            return lbl

        # Тип операції (клас моделі: Expense / RegularExpense / Income)
        label("Тип операції", 0)
        current_type = transaction.__class__.__name__ if editing else "Expense"
        self.type_var = tk.StringVar(value=TRANSACTION_TYPES[current_type])
        ttk.Combobox(form, textvariable=self.type_var, values=list(TRANSACTION_TYPES.values()),
                     state="readonly", width=24).grid(row=0, column=1, sticky=tk.EW, pady=8)

        # Категорія (залежить від типу)
        label("Категорія", 1)
        self.cb_cat = ttk.Combobox(form, width=24, state="readonly")
        self.cb_cat.grid(row=1, column=1, sticky=tk.EW, pady=8)

        # Опис (можна вибрати підказку для категорії або написати свій)
        label("Опис", 7)
        self.cb_desc = ttk.Combobox(form, width=24)
        self.cb_desc.grid(row=7, column=1, sticky=tk.EW, pady=8)

        # Періодичність (лише для регулярної витрати)
        self.lbl_freq = label("Періодичність", 8)
        self.cb_freq = ttk.Combobox(form, values=list(FREQUENCY_LABELS.values()), state="readonly", width=24)
        self.cb_freq.grid(row=8, column=1, sticky=tk.EW, pady=8)
        self.cb_freq.set(FREQUENCY_LABELS[transaction.frequency if editing and current_type == "RegularExpense"
                                          else "monthly"])

        def selected_type() -> str:
            return TRANSACTION_TYPE_BY_LABEL[self.type_var.get()]

        def update_hints(*_):
            self.cb_desc["values"] = description_hints(self.cb_cat.get(), category_kind(selected_type()))

        def update_type(*_):
            kind = category_kind(selected_type())
            cats = [c.name for c in self.controller.get_categories(kind)]
            self.cb_cat["values"] = cats
            if cats:
                self.cb_cat.current(0)
            else:
                self.cb_cat.set("")
            update_hints()
            for widget in (self.lbl_freq, self.cb_freq):   # поле періодичності видно лише для регулярної витрати
                if selected_type() == "RegularExpense":
                    widget.grid()
                else:
                    widget.grid_remove()

        update_type()
        if editing and transaction.category_name in self.cb_cat["values"]:
            self.cb_cat.set(transaction.category_name)
            update_hints()
        self.type_var.trace_add("write", update_type)
        self.cb_cat.bind("<<ComboboxSelected>>", update_hints)
        if editing:
            self.cb_desc.set(transaction.description)

        # Сума
        label("Сума (грн)", 2)
        self.ent_amount = ttk.Entry(form, width=24)
        self.ent_amount.insert(0, f"{transaction.amount:.2f}" if editing else "250.00")
        self.ent_amount.grid(row=2, column=1, sticky=tk.EW, pady=8)

        def add_sum(val):
            try:
                curr = float(self.ent_amount.get().replace(" ", "").replace(",", "."))
            except ValueError:
                curr = 0.0
            new_value = max(0.0, curr + val)  # сума не може стати від'ємною
            self.ent_amount.delete(0, tk.END)
            self.ent_amount.insert(0, f"{new_value:.2f}")

        # Швидкі кнопки: збільшення (ряд 3) та зменшення (ряд 4)
        for row, sign in ((3, 1), (4, -1)):
            chips = ttk.Frame(form, style="Card.TFrame")
            chips.grid(row=row, column=1, sticky=tk.EW, pady=(0, 4))
            for val in (100, 500, 1000):
                text = f"+{val}" if sign > 0 else f"−{val}"
                style_name = "Plus.Chip.TButton" if sign > 0 else "Minus.Chip.TButton"
                ttk.Button(chips, text=text, style=style_name,
                           command=lambda v=sign * val: add_sum(v)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        # Дата (з календарем)
        label("Дата", 5)
        self.ent_date = DateEntry(form, value=transaction.date_str if editing else datetime.now().strftime("%Y-%m-%d"))
        self.ent_date.grid(row=5, column=1, sticky=tk.EW, pady=8)

        # Користувач
        label("Користувач", 6)
        self.cb_person = ttk.Combobox(form, width=24, values=self.controller.get_persons())
        self.cb_person.grid(row=6, column=1, sticky=tk.EW, pady=8)
        if editing:
            self.cb_person.set(transaction.person)

        if editing:
            ttk.Label(body, text=f"Запис створено: {transaction.created_at or 'дата невідома'}",
                      style="CardMuted.TLabel").pack(anchor=tk.W, pady=(8, 0))

        # Кнопки дій
        buttons = ttk.Frame(body, style="Card.TFrame")
        buttons.pack(fill=tk.X, side=tk.BOTTOM, pady=(14, 0))
        ttk.Button(buttons, text="Зберегти", style="Accent.TButton", command=self._save).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Скасувати", command=self.destroy).pack(side=tk.RIGHT, padx=(0, 8))

        self.bind("<Escape>", lambda e: self.destroy())

    def _save(self):
        t_type = TRANSACTION_TYPE_BY_LABEL[self.type_var.get()]
        frequency = FREQUENCY_BY_LABEL[self.cb_freq.get()]
        try:
            self.on_submit(t_type, self.ent_amount.get(), self.ent_date.get(), self.cb_cat.get(),
                           self.cb_desc.get(), self.cb_person.get(), frequency)
        except BudgetError as e:   # помилка введення користувача; інші винятки обробляє BudgetApp
            messagebox.showerror("Помилка валідації", str(e), parent=self)
            return
        self.destroy()


# ======================================================================
#  Вікно керування категоріями та місячними лімітами
# ======================================================================
class CategoryManagerWindow(tk.Toplevel):
    """Додавання, редагування (назва, ліміт) та видалення категорій."""

    def __init__(self, parent, controller: BudgetController, on_change):
        super().__init__(parent)
        self.controller = controller
        self.on_change = on_change
        p = theme.p

        self.title("Категорії та місячні ліміти")
        self.geometry("760x700")
        self.minsize(720, 620)
        self.configure(bg=p["bg"])
        self.transient(parent)
        self.grab_set()
        theme.style_titlebar(self)
        self.bind("<Escape>", lambda e: self.destroy())

        ttk.Label(self, text="Категорії та ліміти", style="Heading.TLabel").pack(anchor=tk.W, padx=24, pady=(20, 2))
        ttk.Label(self, text="Додавайте, змінюйте та видаляйте категорії, задавайте місячні ліміти витрат",
                  style="Muted.TLabel").pack(anchor=tk.W, padx=24, pady=(0, 12))

        # Таблиця категорій
        table_border, table_inner = make_card(self)
        table_border.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 12))

        self.tree = ttk.Treeview(table_inner, columns=("name", "type", "limit"), show="headings",
                                 style="Treeview", selectmode="browse")
        self.tree.heading("name", text="КАТЕГОРІЯ", anchor=tk.W)
        self.tree.heading("type", text="ТИП", anchor=tk.CENTER)
        self.tree.heading("limit", text="МІСЯЧНИЙ ЛІМІТ", anchor=tk.E)
        self.tree.column("name", width=250, anchor=tk.W)
        self.tree.column("type", width=100, anchor=tk.CENTER)
        self.tree.column("limit", width=160, anchor=tk.E)
        scrollbar = ttk.Scrollbar(table_inner, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        style_tree_tags(self.tree)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Форма
        form_border, form_inner = make_card(self)
        form_border.pack(fill=tk.X, padx=24, pady=(0, 12))
        form = ttk.Frame(form_inner, style="Card.TFrame", padding=16)
        form.pack(fill=tk.X)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Назва", style="FieldLabel.TLabel").grid(row=0, column=0, sticky=tk.W, pady=6,
                                                                       padx=(0, 16))
        self.ent_name = ttk.Entry(form, width=30)
        self.ent_name.grid(row=0, column=1, sticky=tk.EW, pady=6)

        ttk.Label(form, text="Тип", style="FieldLabel.TLabel").grid(row=1, column=0, sticky=tk.W, pady=6,
                                                                     padx=(0, 16))
        self.type_var = tk.StringVar(value=TYPE_LABELS["Expense"])
        self.cb_type = ttk.Combobox(form, textvariable=self.type_var, values=list(TYPE_LABELS.values()),
                                    state="readonly", width=27)
        self.cb_type.grid(row=1, column=1, sticky=tk.EW, pady=6)

        ttk.Label(form, text="Ліміт (грн)", style="FieldLabel.TLabel").grid(row=2, column=0, sticky=tk.W, pady=6,
                                                                             padx=(0, 16))
        self.ent_limit = ttk.Entry(form, width=30)
        self.ent_limit.grid(row=2, column=1, sticky=tk.EW, pady=6)

        self.lbl_hint = ttk.Label(form_inner, text="", style="CardMuted.TLabel")
        self.lbl_hint.pack(anchor=tk.W, padx=16, pady=(0, 12))

        btns = ttk.Frame(self, style="TFrame")
        btns.pack(fill=tk.X, padx=24, pady=(0, 20))
        ttk.Button(btns, text="➕ Додати", style="Accent.TButton", command=self._add).pack(side=tk.LEFT)
        ttk.Button(btns, text="💾 Зберегти вибрану", command=self._update).pack(side=tk.LEFT, padx=8)
        ttk.Button(btns, text="🗑 Видалити", style="Danger.TButton", command=self._delete).pack(side=tk.LEFT)
        ttk.Button(btns, text="Закрити", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Очистити форму", command=self._clear_form).pack(side=tk.RIGHT, padx=8)

        self._clear_form()
        self._refresh()

    def _refresh(self):
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for i, cat in enumerate(self.controller.get_categories()):
            if cat.cat_type == "Income":
                limit_text = "—"
            else:
                limit_text = fmt_money(cat.monthly_limit) if cat.monthly_limit > 0 else "без ліміту"
            self.tree.insert("", tk.END, iid=cat.name, tags=("even" if i % 2 == 0 else "odd",),
                             values=(cat.name, TYPE_LABELS[cat.cat_type], limit_text))
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])

    def _clear_form(self):
        """Режим «нова категорія»: знімає виділення, дозволяє вибрати тип."""
        self.tree.selection_set(())
        self.ent_name.delete(0, tk.END)
        self.ent_limit.delete(0, tk.END)
        self.cb_type.config(state="readonly")
        self.lbl_hint.config(text="Нова категорія: введіть назву, тип і (для витрат) ліміт, потім натисніть «Додати».")

    def _on_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        cat = self.controller.get_category(selection[0])
        if cat is None:
            return
        self.ent_name.delete(0, tk.END)
        self.ent_name.insert(0, cat.name)
        self.type_var.set(TYPE_LABELS[cat.cat_type])
        self.cb_type.config(state="disabled")   # тип існуючої категорії змінювати не можна
        self.ent_limit.delete(0, tk.END)
        self.ent_limit.insert(0, f"{cat.monthly_limit:.2f}")
        self.lbl_hint.config(text="Змініть назву чи ліміт і натисніть «Зберегти вибрану». "
                                  "Тип категорії змінювати не можна.")

    def _selected_name(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Увага", "Спочатку виберіть категорію в таблиці.", parent=self)
            return None
        return selection[0]

    def _add(self):
        try:
            self.controller.add_category(self.ent_name.get(), KIND_BY_LABEL[self.type_var.get()],
                                         self.ent_limit.get())
        except BudgetError as e:
            messagebox.showerror("Помилка", str(e), parent=self)
            return
        self._refresh()
        self.on_change()
        new_name = self.ent_name.get().strip()
        if self.tree.exists(new_name):
            self.tree.selection_set(new_name)
            self.tree.see(new_name)

    def _update(self):
        name = self._selected_name()
        if name is None:
            return
        try:
            self.controller.update_category(name, self.ent_name.get(), self.ent_limit.get())
        except BudgetError as e:
            messagebox.showerror("Помилка", str(e), parent=self)
            return
        new_name = self.ent_name.get().strip()
        self._refresh()
        self.on_change()
        if self.tree.exists(new_name):
            self.tree.selection_set(new_name)

    def _delete(self):
        name = self._selected_name()
        if name is None:
            return
        if not messagebox.askyesno("Видалення категорії", f"Видалити категорію «{name}»?", parent=self):
            return
        try:
            self.controller.delete_category(name)
        except BudgetError as e:
            messagebox.showerror("Помилка", str(e), parent=self)
            return
        self._clear_form()
        self._refresh()
        self.on_change()
