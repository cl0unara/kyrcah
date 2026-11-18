"""
Вікно місячного звіту. Розрахунок виконується у фоновому потоці (п. 4.4 завдання):
контролер запускає threading.Thread, потік кладе прогрес і результат у queue.Queue,
а вікно опитує чергу через after() та оновлює ttk.Progressbar.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from controller import BudgetController
from errors import BudgetError
from theme import theme
from view_common import fmt_money, make_card, make_stat_card, poll_until_done, style_tree_tags
from widgets import month_label


class ReportWindow(tk.Toplevel):

    def __init__(self, parent, controller: BudgetController, month: str):
        super().__init__(parent)
        self.parent = parent
        self.controller = controller
        self.report = None
        self._month_map = {month_label(key): key for key in controller.get_months()}
        p = theme.p

        self.title("Місячний звіт")
        self.geometry("820x680")
        self.minsize(760, 600)
        self.configure(bg=p["bg"])
        self.transient(parent)
        self.grab_set()
        theme.style_titlebar(self)
        self.bind("<Escape>", lambda e: self.destroy())

        ttk.Label(self, text="Місячний звіт", style="Heading.TLabel").pack(anchor=tk.W, padx=24, pady=(20, 2))
        ttk.Label(self, text="Підсумки за місяць і перевірка місячних лімітів категорій",
                  style="Muted.TLabel").pack(anchor=tk.W, padx=24, pady=(0, 12))

        # Вибір місяця
        top = ttk.Frame(self, style="TFrame")
        top.pack(fill=tk.X, padx=24, pady=(0, 8))
        ttk.Label(top, text="Місяць:", style="Muted.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        self.cb_month = ttk.Combobox(top, state="readonly", width=22, values=list(self._month_map))
        self.cb_month.set(month_label(month))
        self.cb_month.pack(side=tk.LEFT)
        self.cb_month.bind("<<ComboboxSelected>>", lambda e: self._start())
        self.lbl_status = ttk.Label(top, text="", style="Muted.TLabel")
        self.lbl_status.pack(side=tk.RIGHT)

        # Індикатор виконання
        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X, padx=24, pady=(0, 12))

        # Картки-підсумки
        dash = ttk.Frame(self, style="TFrame")
        dash.pack(fill=tk.X, padx=24, pady=(0, 12))
        for col in range(3):
            dash.columnconfigure(col, weight=1, uniform="stat")
        self.lbl_inc = make_stat_card(dash, 0, "ДОХІД", "Income")
        self.lbl_exp = make_stat_card(dash, 1, "ВИТРАТИ", "Expense")
        self.lbl_bal = make_stat_card(dash, 2, "БАЛАНС", "Balance")

        # Таблиця витрат за категоріями
        border, inner = make_card(self)
        border.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 12))
        columns = ("category", "spent", "limit", "status")
        self.tree = ttk.Treeview(inner, columns=columns, show="headings", style="Treeview", selectmode="browse")
        heads = {"category": ("КАТЕГОРІЯ", tk.W, 230), "spent": ("ВИТРАЧЕНО", tk.E, 130),
                 "limit": ("ЛІМІТ", tk.E, 130), "status": ("СТАН", tk.W, 220)}
        for col, (title, anchor, width) in heads.items():
            self.tree.heading(col, text=title, anchor=anchor)
            self.tree.column(col, width=width, anchor=anchor)
        scrollbar = ttk.Scrollbar(inner, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        style_tree_tags(self.tree)
        self.tree.tag_configure("over", foreground=p["expense"])

        # Кнопки
        buttons = ttk.Frame(self, style="TFrame")
        buttons.pack(fill=tk.X, padx=24, pady=(0, 20))
        self.btn_xml = ttk.Button(buttons, text="📊 Експорт у XML", style="Accent.TButton", command=self._export_xml)
        self.btn_xml.pack(side=tk.LEFT)
        ttk.Button(buttons, text="Закрити", command=self.destroy).pack(side=tk.RIGHT)

        self._start()

    # ---------- Запуск фонового розрахунку ----------
    def _start(self):
        month = self._month_map[self.cb_month.get()]
        try:
            self.controller.start_report(month)
        except BudgetError as e:
            messagebox.showerror("Помилка", str(e), parent=self)
            return
        self.report = None
        self.btn_xml.state(["disabled"])
        self.cb_month.state(["disabled"])
        self.lbl_status.config(text="Розрахунок…")
        self.progress.config(value=0)
        # цикл after() веде головне вікно: він не зупиниться, навіть якщо закрити це вікно
        poll_until_done(self.parent, self.controller, self._on_event)

    def _on_event(self, kind: str, payload):
        if not self.winfo_exists():   # вікно закрили, поки йшов розрахунок
            return
        if kind == "progress":
            self.progress.config(value=payload * 100)
        elif kind == "report_ok":
            self.progress.config(value=100)
            self.cb_month.state(["!disabled"])
            self._show(payload)
        elif kind == "report_error":
            self.cb_month.state(["!disabled"])
            self.lbl_status.config(text="Помилка розрахунку")
            messagebox.showerror("Помилка", f"Не вдалося розрахувати звіт: {payload}", parent=self)

    # ---------- Відображення результату ----------
    def _show(self, report: dict):
        self.report = report
        self.lbl_inc.config(text=fmt_money(report["total_income"]))
        self.lbl_exp.config(text=fmt_money(report["total_expense"]))
        self.lbl_bal.config(text=fmt_money(report["balance"]),
                            style="Balance.Value.TLabel" if report["balance"] >= 0 else "BalanceNeg.Value.TLabel")

        self.tree.delete(*self.tree.get_children())
        for i, (name, spent) in enumerate(report["spent_by_category"].items()):
            limit = report["limits"].get(name, 0.0)
            over = report["overlimit_categories"].get(name)
            if over:
                status = f"⚠ Перевищено на {fmt_money(over['exceeded_by'])}"
            elif limit > 0:
                status = f"У межах ліміту ({spent / limit * 100:.0f}%)"
            else:
                status = "Без ліміту"
            tags = ("over",) if over else ("even" if i % 2 == 0 else "odd",)
            self.tree.insert("", tk.END, tags=tags,
                             values=(name, fmt_money(spent), fmt_money(limit) if limit > 0 else "—", status))

        count = len(report["overlimit_categories"])
        self.lbl_status.config(text=f"Записів: {report['transaction_count']} · перевищень лімітів: {count}")
        self.btn_xml.state(["!disabled"])

    def _export_xml(self):
        if self.report is None:
            return
        file_path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".xml", filetypes=[("XML Files", "*.xml")],
            initialfile=f"report_{self.report['month']}.xml")
        if not file_path:
            return
        try:
            self.controller.export_xml(file_path, self.report)
        except BudgetError as e:
            messagebox.showerror("Помилка", str(e), parent=self)
            return
        messagebox.showinfo("Успіх", f"XML-звіт за {month_label(self.report['month'])} збережено!", parent=self)
