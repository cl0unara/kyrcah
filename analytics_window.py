"""Вікно аналітики: за категоріями (кільцева діаграма) та по місяцях (стовпчики + таблиця). Лише відображення."""
import tkinter as tk
from tkinter import ttk

from controller import BudgetController
from theme import theme, CHART_COLORS, FONT
from view_common import fmt_money, fmt_compact, nice_ticks, make_card, style_tree_tags
from widgets import MONTH_SHORT, month_label, shift_month


class AnalyticsWindow(tk.Toplevel):
    ALL_PERIODS = "Усі періоди"
    LAST_12 = "Останні 12 місяців"
    ROW_H = 62

    def __init__(self, parent, controller: BudgetController, initial_month=None):
        super().__init__(parent)
        self.controller = controller
        self.mode = "categories"
        self._initial_month = initial_month
        self._period_map = {self.ALL_PERIODS: None}
        self._cat_width = 0
        self._month_size = (0, 0)
        self._month_geom = None
        p = theme.p

        self.title("Аналітика")
        self.geometry("1000x720")
        self.minsize(880, 580)
        self.configure(bg=p["bg"])
        theme.style_titlebar(self)
        self.bind("<Escape>", lambda e: self.destroy())

        # ----- Заголовок та перемикач режимів -----
        top = ttk.Frame(self, style="TFrame")
        top.pack(fill=tk.X, padx=24, pady=(20, 8))
        title_box = ttk.Frame(top, style="TFrame")
        title_box.pack(side=tk.LEFT)
        ttk.Label(title_box, text="Аналітика", style="Heading.TLabel").pack(anchor=tk.W)
        self.lbl_sub = ttk.Label(title_box, text="", style="Muted.TLabel")
        self.lbl_sub.pack(anchor=tk.W)

        seg = ttk.Frame(top, style="TFrame")
        seg.pack(side=tk.RIGHT)
        self.btn_cat = ttk.Button(seg, text="🍩 За категоріями", command=lambda: self._set_mode("categories"))
        self.btn_month = ttk.Button(seg, text="📊 По місяцях", command=lambda: self._set_mode("months"))
        self.btn_cat.pack(side=tk.LEFT, padx=3)
        self.btn_month.pack(side=tk.LEFT, padx=3)

        # ----- Фільтри -----
        filters = ttk.Frame(self, style="TFrame")
        filters.pack(fill=tk.X, padx=24, pady=(0, 10))
        self.lbl_filter = ttk.Label(filters, text="Період:", style="Muted.TLabel")
        self.lbl_filter.pack(side=tk.LEFT)
        self.cb_period = ttk.Combobox(filters, state="readonly", width=22)
        self.cb_year = ttk.Combobox(filters, state="readonly", width=22)
        self.cb_period.bind("<<ComboboxSelected>>", lambda e: self._draw())
        self.cb_year.bind("<<ComboboxSelected>>", lambda e: self._draw())

        # ----- Вміст -----
        border, inner = make_card(self)
        border.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 24))

        # Сторінка «За категоріями»
        self.page_cat = ttk.Frame(inner, style="Card.TFrame")
        self.cat_canvas = tk.Canvas(self.page_cat, bg=p["surface"], highlightthickness=0)
        cat_scroll = ttk.Scrollbar(self.page_cat, orient=tk.VERTICAL, command=self.cat_canvas.yview)
        self.cat_canvas.configure(yscrollcommand=cat_scroll.set)
        self.cat_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cat_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.cat_canvas.bind("<Configure>", self._on_cat_resize)
        self.cat_canvas.bind("<MouseWheel>", lambda e: self.cat_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))

        # Сторінка «По місяцях»: графік зверху, таблиця знизу
        self.page_month = ttk.Frame(inner, style="Card.TFrame")
        self.month_canvas = tk.Canvas(self.page_month, bg=p["surface"], highlightthickness=0, height=290)
        self.month_canvas.pack(fill=tk.X)
        self.month_canvas.bind("<Configure>", self._on_month_resize)
        self.month_canvas.bind("<Motion>", self._on_month_motion)
        self.month_canvas.bind("<Leave>", lambda e: self.month_canvas.delete("hover"))

        table_frame = ttk.Frame(self.page_month, style="Card.TFrame")
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("month", "income", "expense", "balance", "count", "people")
        self.month_tree = ttk.Treeview(table_frame, columns=columns, show="headings", style="Treeview",
                                       selectmode="browse")
        heads = {"month": ("МІСЯЦЬ", tk.W, 170), "income": ("ДОХОДИ", tk.E, 150), "expense": ("ВИТРАТИ", tk.E, 150),
                 "balance": ("БАЛАНС", tk.E, 150), "count": ("ЗАПИСІВ", tk.E, 100),
                 "people": ("КОРИСТУВАЧІВ", tk.E, 120)}
        for col, (title, anchor, width) in heads.items():
            self.month_tree.heading(col, text=title, anchor=anchor)
            self.month_tree.column(col, width=width, anchor=anchor)
        month_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.month_tree.yview)
        self.month_tree.configure(yscroll=month_scroll.set)
        self.month_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        month_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        style_tree_tags(self.month_tree)
        self.month_tree.bind("<Double-1>", self._on_month_double_click)

        self._refresh_filters()
        theme.subscribe(self._on_theme_changed)
        self.bind("<Destroy>", self._on_destroy)
        self._set_mode("categories")

    # ---------- Службові події ----------
    def _on_destroy(self, event):
        if event.widget is self:
            theme.unsubscribe(self._on_theme_changed)

    def _on_theme_changed(self):
        self.configure(bg=theme.p["bg"])
        self.cat_canvas.configure(bg=theme.p["surface"])
        self.month_canvas.configure(bg=theme.p["surface"])
        style_tree_tags(self.month_tree)
        theme.style_titlebar(self)
        self._draw()

    def _on_cat_resize(self, event):
        if event.width != self._cat_width:
            self._cat_width = event.width
            if self.mode == "categories":
                self._draw_categories()

    def _on_month_resize(self, event):
        if (event.width, event.height) != self._month_size:
            self._month_size = (event.width, event.height)
            if self.mode == "months":
                self._draw_months()

    # ---------- Фільтри та режими ----------
    def _refresh_filters(self):
        months = self.controller.get_months()  # від нових до старих
        self._period_map = {self.ALL_PERIODS: None}
        for key in months:
            self._period_map[month_label(key)] = key
        self.cb_period["values"] = list(self._period_map)
        label = month_label(self._initial_month) if self._initial_month else None
        self.cb_period.set(label if label in self._period_map else self.ALL_PERIODS)

        years = sorted({key[:4] for key in months}, reverse=True)
        self.cb_year["values"] = [self.LAST_12] + years
        self.cb_year.set(self.LAST_12)

    def _set_mode(self, mode: str):
        self.mode = mode
        self.btn_cat.config(style="Accent.TButton" if mode == "categories" else "TButton")
        self.btn_month.config(style="Accent.TButton" if mode == "months" else "TButton")
        if mode == "categories":
            self.page_month.pack_forget()
            self.page_cat.pack(fill=tk.BOTH, expand=True)
            self.cb_year.pack_forget()
            self.lbl_filter.config(text="Період:")
            self.cb_period.pack(side=tk.LEFT, padx=8)
            self.lbl_sub.config(text="Розподіл витрат за категоріями та використання місячних лімітів")
        else:
            self.page_cat.pack_forget()
            self.page_month.pack(fill=tk.BOTH, expand=True)
            self.cb_period.pack_forget()
            self.lbl_filter.config(text="Рік:")
            self.cb_year.pack(side=tk.LEFT, padx=8)
            self.lbl_sub.config(text="Доходи та витрати по місяцях · подвійний клік по місяцю відкриє його категорії")
        self._draw()

    def _draw(self):
        if self.mode == "categories":
            self._draw_categories()
        else:
            self._draw_months()
            self._fill_month_table()

    # ---------- Режим «За категоріями» ----------
    def _draw_categories(self):
        c = self.cat_canvas
        p = theme.p
        c.delete("all")

        month = self._period_map.get(self.cb_period.get())
        data = self.controller.get_analytics(month)
        spent, limits, total = data["spent"], data["limits"], data["total"]

        width = max(c.winfo_width(), 700)
        view_h = max(c.winfo_height(), 300)

        if not spent or total <= 0:
            c.create_text(width / 2, view_h / 2 - 10, text="Немає витрат за обраний період",
                          font=(FONT, 13, "bold"), fill=p["text"])
            c.create_text(width / 2, view_h / 2 + 16, text="Додайте витрати або виберіть інший місяць",
                          font=(FONT, 10), fill=p["muted"])
            c.configure(scrollregion=(0, 0, width, view_h))
            return

        # --- Кільцева діаграма ---
        cx, cy, r, hole = 160, 200, 120, 74
        box = (cx - r, cy - r, cx + r, cy + r)
        start = 90.0
        for i, (name, amount) in enumerate(spent.items()):
            color = CHART_COLORS[i % len(CHART_COLORS)]
            if len(spent) == 1:
                c.create_oval(*box, fill=color, outline=p["surface"], width=3)
            else:
                extent = amount / total * 360.0
                c.create_arc(*box, start=start, extent=-extent, fill=color, outline=p["surface"], width=3)
                start -= extent
        c.create_oval(cx - hole, cy - hole, cx + hole, cy + hole, fill=p["surface"], outline=p["surface"])
        c.create_text(cx, cy - 10, text=f"{total:,.2f}".replace(",", " "), font=(FONT, 15, "bold"),
                      fill=p["text"])
        c.create_text(cx, cy + 14, text="грн витрат", font=(FONT, 9), fill=p["muted"])

        # --- Легенда з індикаторами ---
        lx, rx = 340, width - 40
        c.create_text(lx, 24, anchor="w", text="КАТЕГОРІЇ ВИТРАТ", font=(FONT, 9, "bold"), fill=p["muted"])
        bar_x1, bar_x2 = lx + 20 + 4, rx - 4
        bar_len = bar_x2 - bar_x1

        y = 58
        for i, (name, amount) in enumerate(spent.items()):
            color = CHART_COLORS[i % len(CHART_COLORS)]
            limit = limits.get(name, 0.0)
            use_limit = data["check_limits"] and limit > 0
            over = use_limit and amount > limit

            c.create_oval(lx, y - 5, lx + 10, y + 5, fill=color, outline="")
            c.create_text(lx + 20, y, anchor="w", text=name, font=(FONT, 10, "bold"), fill=p["text"])
            c.create_text(rx, y, anchor="e", text=fmt_money(amount), font=(FONT, 10, "bold"),
                          fill=p["expense"] if over else p["text"])

            # Смуга: використання ліміту або частка від усіх витрат
            fraction = min(amount / limit, 1.0) if use_limit else amount / total
            bar_color = p["expense"] if over else (p["warn"] if use_limit and amount / limit > 0.8 else color)
            c.create_line(bar_x1, y + 22, bar_x2, y + 22, width=6, capstyle=tk.ROUND, fill=p["border"])
            if fraction * bar_len >= 1:
                c.create_line(bar_x1, y + 22, bar_x1 + fraction * bar_len, y + 22, width=6,
                              capstyle=tk.ROUND, fill=bar_color)

            if use_limit:
                if over:
                    caption = f"⚠ Перевищено ліміт {fmt_money(limit)} на {fmt_money(amount - limit)}"
                else:
                    caption = f"{amount / limit * 100:.0f}% від ліміту {fmt_money(limit)}"
            else:
                caption = f"{amount / total * 100:.1f}% від усіх витрат"
            c.create_text(lx + 20, y + 38, anchor="w", text=caption, font=(FONT, 8),
                          fill=p["expense"] if over else p["muted"])
            y += self.ROW_H

        if not data["check_limits"]:
            c.create_text(lx, y + 6, anchor="w", font=(FONT, 9), fill=p["muted"],
                          text="Оберіть конкретний місяць, щоб порівняти витрати з місячними лімітами.")
            y += 30

        c.configure(scrollregion=(0, 0, width, max(view_h, y + 20)))

    # ---------- Режим «По місяцях» ----------
    def _month_rows(self) -> list[dict]:
        """Рядки для обраного року (або останніх 12 місяців); порожні місяці — з нулями."""
        summary = {row["month"]: row for row in self.controller.get_monthly_summary()}
        if not summary:
            return []
        choice = self.cb_year.get()
        if choice.isdigit():
            keys = [f"{int(choice):04d}-{m:02d}" for m in range(1, 13)]
        else:
            last = max(summary)
            keys = [shift_month(last, -i) for i in range(11, -1, -1)]
        empty = {"income": 0.0, "expense": 0.0, "balance": 0.0, "count": 0, "people": 0}
        return [summary.get(k) or {**empty, "month": k} for k in keys]

    def _draw_months(self):
        c = self.month_canvas
        p = theme.p
        c.delete("all")
        self._month_geom = None

        rows = self._month_rows()
        w = max(c.winfo_width(), 700)
        h = max(c.winfo_height(), 240)

        if not rows or all(r["income"] == 0 and r["expense"] == 0 for r in rows):
            c.create_text(w / 2, h / 2, text="Немає даних за обраний період", font=(FONT, 12, "bold"),
                          fill=p["muted"])
            return

        pad_l, pad_r, pad_t, pad_b = 70, 24, 44, 46
        plot_w = w - pad_l - pad_r
        plot_h = h - pad_t - pad_b
        base = pad_t + plot_h

        max_value = max(max(r["income"], r["expense"]) for r in rows)
        step, n = nice_ticks(max_value)
        top_value = step * n

        # Сітка та підписи осі Y
        for k in range(n + 1):
            y = base - plot_h * k / n
            options = {"dash": (2, 4)} if k else {}
            c.create_line(pad_l, y, w - pad_r, y, fill=p["border"], **options)
            c.create_text(pad_l - 10, y, anchor="e", text=fmt_compact(step * k), font=(FONT, 8), fill=p["muted"])

        # Стовпчики: дохід (зелений) та витрати (червоний)
        slot = plot_w / len(rows)
        bar_w = max(4, min(26, slot * 0.30))
        for i, r in enumerate(rows):
            cx = pad_l + slot * (i + 0.5)
            for x0, x1, value, color in ((-bar_w - 1, -1, r["income"], p["income"]),
                                         (1, bar_w + 1, r["expense"], p["expense"])):
                bar_h = plot_h * value / top_value
                if bar_h >= 1:
                    c.create_rectangle(cx + x0, base - bar_h, cx + x1, base, fill=color, outline="")
            month_number = int(r["month"][5:7])
            c.create_text(cx, base + 14, text=MONTH_SHORT[month_number - 1], font=(FONT, 9), fill=p["text"])
            if month_number == 1 or i == 0:
                c.create_text(cx, base + 30, text=r["month"][:4], font=(FONT, 8), fill=p["muted"])

        # Легенда
        c.create_rectangle(pad_l, 15, pad_l + 10, 25, fill=p["income"], outline="")
        c.create_text(pad_l + 16, 20, anchor="w", text="Доходи", font=(FONT, 9), fill=p["muted"])
        c.create_rectangle(pad_l + 80, 15, pad_l + 90, 25, fill=p["expense"], outline="")
        c.create_text(pad_l + 96, 20, anchor="w", text="Витрати", font=(FONT, 9), fill=p["muted"])

        self._month_geom = (pad_l, slot, rows, pad_t, base, w, pad_r)

    def _on_month_motion(self, event):
        c = self.month_canvas
        c.delete("hover")
        geom = self._month_geom
        if not geom:
            return
        pad_l, slot, rows, pad_t, base, w, pad_r = geom
        if not (pad_l <= event.x <= w - pad_r and pad_t <= event.y <= base):
            return
        i = int((event.x - pad_l) // slot)
        if not 0 <= i < len(rows):
            return
        r = rows[i]
        p = theme.p
        c.create_rectangle(pad_l + slot * i, pad_t, pad_l + slot * (i + 1), base, fill=p["surface2"], outline="",
                           tags="hover")
        c.tag_lower("hover")
        text = (f"{month_label(r['month'])} · доходи {fmt_money(r['income'])} · "
                f"витрати {fmt_money(r['expense'])} · баланс {fmt_money(r['balance'])}")
        c.create_text(w - pad_r, 20, anchor="e", text=text, font=(FONT, 9, "bold"), fill=p["text"], tags="hover")

    def _fill_month_table(self):
        tree = self.month_tree
        tree.delete(*tree.get_children())
        rows = [r for r in reversed(self._month_rows()) if r["count"] > 0]  # від нових до старих
        for i, r in enumerate(rows):
            balance = r["balance"]
            tree.insert("", tk.END, iid=r["month"], tags=("even" if i % 2 == 0 else "odd",),
                        values=(month_label(r["month"]), fmt_money(r["income"]), fmt_money(r["expense"]),
                                f"{'+' if balance >= 0 else '−'}{fmt_money(abs(balance))}",
                                r["count"], r["people"]))

    def _on_month_double_click(self, event):
        """Подвійний клік по місяцю в таблиці — відкрити розбивку цього місяця за категоріями."""
        selection = self.month_tree.selection()
        if not selection:
            return
        label = month_label(selection[0])
        if label in self._period_map:
            self.cb_period.set(label)
            self._set_mode("categories")
