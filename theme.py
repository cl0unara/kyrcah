"""
Сучасна тема оформлення (світла / темна) на стандартному ttk (тема "clam").
Містить лише налаштування зовнішнього вигляду — жодної бізнес-логіки (частина View у MVC).
"""
import tkinter as tk
from tkinter import ttk

FONT = "Segoe UI"

PALETTES = {
    "dark": {
        "bg": "#0b1020", "surface": "#121a30", "surface2": "#1a2442", "border": "#27335a",
        "hover": "#222e54", "text": "#e8ecf8", "muted": "#8d98bb",
        "primary": "#6366f1", "primary_hover": "#7a7df7", "primary_press": "#4f52d8", "on_primary": "#ffffff",
        "income": "#34d399", "expense": "#f87171", "balance": "#60a5fa",
        "danger": "#f87171", "danger_press": "#dc2626", "warn": "#fbbf24",
        "row_alt": "#0f1730", "select": "#2b3a78", "select_text": "#ffffff",
    },
    "light": {
        "bg": "#f3f4f8", "surface": "#ffffff", "surface2": "#f1f5f9", "border": "#e2e8f0",
        "hover": "#e2e8f0", "text": "#0f172a", "muted": "#64748b",
        "primary": "#4f46e5", "primary_hover": "#4338ca", "primary_press": "#3730a3", "on_primary": "#ffffff",
        "income": "#059669", "expense": "#dc2626", "balance": "#2563eb",
        "danger": "#dc2626", "danger_press": "#b91c1c", "warn": "#d97706",
        "row_alt": "#f8fafc", "select": "#e0e7ff", "select_text": "#1e1b4b",
    },
}

# Кольори секторів діаграми (однакові для обох тем)
CHART_COLORS = ["#6366f1", "#22d3ee", "#f59e0b", "#f472b6", "#34d399", "#a78bfa",
                "#fb7185", "#38bdf8", "#facc15", "#4ade80", "#fb923c", "#2dd4bf"]


class Theme:
    """Керує палітрою та стилями ttk. Підписники (вікна) отримують сповіщення при зміні теми."""

    def __init__(self, mode: str = "dark"):
        self.mode = mode if mode in PALETTES else "dark"
        self._listeners = []

    @property
    def p(self) -> dict:
        return PALETTES[self.mode]

    # ---------- Підписка ----------
    def subscribe(self, callback):
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unsubscribe(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    # ---------- Керування режимом ----------
    def set_mode(self, root, mode: str):
        self.mode = mode if mode in PALETTES else "dark"
        self.apply(root)

    def toggle(self, root):
        self.set_mode(root, "light" if self.mode == "dark" else "dark")

    # ---------- Заголовок вікна (Windows 10/11) ----------
    def style_titlebar(self, window):
        """Темний/світлий рядок заголовка вікна. Поза Windows (або при помилці) нічого не робить."""

        def _apply():
            try:
                import ctypes
                window.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
                value = ctypes.c_int(1 if self.mode == "dark" else 0)
                for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (нові / старі збірки Windows)
                    if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                            hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                        break
            except Exception:
                pass

        window.after(20, _apply)

    # ---------- Застосування стилів ----------
    def apply(self, root):
        p = self.p
        f = FONT
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        root.configure(bg=p["bg"])

        # Загальні налаштування
        style.configure(".", background=p["bg"], foreground=p["text"], bordercolor=p["border"],
                        lightcolor=p["border"], darkcolor=p["border"], troughcolor=p["surface2"],
                        focuscolor=p["bg"], font=(f, 10))

        # ----- Контейнери -----
        style.configure("TFrame", background=p["bg"])
        style.configure("Card.TFrame", background=p["surface"])
        style.configure("Border.TFrame", background=p["border"])
        style.configure("Income.Stripe.TFrame", background=p["income"])
        style.configure("Expense.Stripe.TFrame", background=p["expense"])
        style.configure("Balance.Stripe.TFrame", background=p["balance"])

        # ----- Текст -----
        style.configure("TLabel", background=p["bg"], foreground=p["text"], font=(f, 10))
        style.configure("Card.TLabel", background=p["surface"], foreground=p["text"], font=(f, 10))
        style.configure("Muted.TLabel", background=p["bg"], foreground=p["muted"], font=(f, 9))
        style.configure("CardMuted.TLabel", background=p["surface"], foreground=p["muted"], font=(f, 9))
        style.configure("Title.TLabel", background=p["bg"], foreground=p["text"], font=(f, 19, "bold"))
        style.configure("Heading.TLabel", background=p["bg"], foreground=p["text"], font=(f, 15, "bold"))
        style.configure("CardTitle.TLabel", background=p["surface"], foreground=p["text"], font=(f, 15, "bold"))
        style.configure("FieldLabel.TLabel", background=p["surface"], foreground=p["muted"], font=(f, 9, "bold"))
        style.configure("Empty.TLabel", background=p["surface"], foreground=p["muted"], font=(f, 11))
        style.configure("Income.Value.TLabel", background=p["surface"], foreground=p["income"], font=(f, 18, "bold"))
        style.configure("Expense.Value.TLabel", background=p["surface"], foreground=p["expense"], font=(f, 18, "bold"))
        style.configure("Balance.Value.TLabel", background=p["surface"], foreground=p["balance"],
                        font=(f, 18, "bold"))
        style.configure("BalanceNeg.Value.TLabel", background=p["surface"], foreground=p["expense"],
                        font=(f, 18, "bold"))

        # ----- Кнопки -----
        style.configure("TButton", font=(f, 9, "bold"), padding=(12, 7), relief="flat", borderwidth=1,
                        background=p["surface2"], foreground=p["text"], bordercolor=p["border"],
                        lightcolor=p["surface2"], darkcolor=p["surface2"], focuscolor=p["surface2"])
        style.map("TButton",
                  background=[("disabled", p["surface"]), ("pressed", p["border"]), ("active", p["hover"])],
                  foreground=[("disabled", p["muted"])],
                  bordercolor=[("disabled", p["border"]), ("active", p["primary"])],
                  lightcolor=[("pressed", p["border"]), ("active", p["hover"])],
                  darkcolor=[("pressed", p["border"]), ("active", p["hover"])],
                  relief=[("pressed", "flat")])

        style.configure("Accent.TButton", font=(f, 10, "bold"), padding=(14, 8),
                        background=p["primary"], foreground=p["on_primary"], bordercolor=p["primary"],
                        lightcolor=p["primary"], darkcolor=p["primary"], focuscolor=p["primary"])
        style.map("Accent.TButton",
                  background=[("disabled", p["surface2"]), ("pressed", p["primary_press"]),
                              ("active", p["primary_hover"])],
                  foreground=[("disabled", p["muted"])],
                  bordercolor=[("disabled", p["border"]), ("pressed", p["primary_press"]),
                               ("active", p["primary_hover"])],
                  lightcolor=[("disabled", p["surface2"]), ("pressed", p["primary_press"]),
                              ("active", p["primary_hover"])],
                  darkcolor=[("disabled", p["surface2"]), ("pressed", p["primary_press"]),
                             ("active", p["primary_hover"])])

        style.configure("Danger.TButton", foreground=p["danger"])
        style.map("Danger.TButton",
                  background=[("disabled", p["surface"]), ("pressed", p["danger_press"]), ("active", p["danger"])],
                  foreground=[("disabled", p["muted"]), ("pressed", "#ffffff"), ("active", "#ffffff")],
                  bordercolor=[("disabled", p["border"]), ("active", p["danger"])],
                  lightcolor=[("pressed", p["danger_press"]), ("active", p["danger"])],
                  darkcolor=[("pressed", p["danger_press"]), ("active", p["danger"])])

        style.configure("Ghost.TButton", font=(f, 12), padding=(10, 5), background=p["bg"],
                        bordercolor=p["bg"], lightcolor=p["bg"], darkcolor=p["bg"], focuscolor=p["bg"])
        style.map("Ghost.TButton",
                  background=[("pressed", p["border"]), ("active", p["surface2"])],
                  bordercolor=[("active", p["surface2"])],
                  lightcolor=[("active", p["surface2"])], darkcolor=[("active", p["surface2"])])

        style.configure("Chip.TButton", padding=(6, 6))
        style.configure("Plus.Chip.TButton", foreground=p["income"])
        style.configure("Minus.Chip.TButton", foreground=p["expense"])

        # ----- Календар -----
        flat_surface = dict(background=p["surface"], foreground=p["text"], bordercolor=p["surface"],
                            lightcolor=p["surface"], darkcolor=p["surface"], focuscolor=p["surface"])
        style.configure("Nav.TButton", font=(f, 11, "bold"), padding=(6, 4), **flat_surface)
        style.configure("Day.TButton", font=(f, 9), padding=(0, 7), **flat_surface)
        for name in ("Nav.TButton", "Day.TButton"):
            style.map(name,
                      background=[("pressed", p["border"]), ("active", p["surface2"])],
                      bordercolor=[("active", p["surface2"])],
                      lightcolor=[("active", p["surface2"])], darkcolor=[("active", p["surface2"])])
        style.configure("Muted.Day.TButton", foreground=p["muted"])
        style.configure("Today.Day.TButton", foreground=p["primary_hover"], bordercolor=p["primary"])
        style.configure("Selected.Day.TButton", background=p["primary"], foreground=p["on_primary"],
                        bordercolor=p["primary"], lightcolor=p["primary"], darkcolor=p["primary"])
        style.map("Selected.Day.TButton",
                  background=[("pressed", p["primary_press"]), ("active", p["primary_hover"])],
                  bordercolor=[("active", p["primary_hover"])],
                  lightcolor=[("active", p["primary_hover"])], darkcolor=[("active", p["primary_hover"])])

        # ----- Поля введення -----
        style.configure("TEntry", fieldbackground=p["surface2"], foreground=p["text"], insertcolor=p["text"],
                        bordercolor=p["border"], lightcolor=p["border"], darkcolor=p["border"], padding=7)
        style.map("TEntry",
                  bordercolor=[("focus", p["primary"])],
                  lightcolor=[("focus", p["primary"])],
                  darkcolor=[("focus", p["primary"])])

        style.configure("TCombobox", fieldbackground=p["surface2"], background=p["surface2"],
                        foreground=p["text"], arrowcolor=p["muted"], bordercolor=p["border"],
                        lightcolor=p["border"], darkcolor=p["border"], selectbackground=p["surface2"],
                        selectforeground=p["text"], insertcolor=p["text"], padding=6, arrowsize=14)
        style.map("TCombobox",
                  fieldbackground=[("readonly", p["surface2"]), ("disabled", p["surface"])],
                  background=[("active", p["hover"]), ("readonly", p["surface2"])],
                  foreground=[("disabled", p["muted"])],
                  selectbackground=[("readonly", p["surface2"])],
                  selectforeground=[("readonly", p["text"])],
                  arrowcolor=[("active", p["text"])],
                  bordercolor=[("focus", p["primary"])],
                  lightcolor=[("focus", p["primary"])],
                  darkcolor=[("focus", p["primary"])])

        # Випадаючий список комбобоксів (звичайний tk.Listbox)
        root.option_add("*TCombobox*Listbox.background", p["surface2"])
        root.option_add("*TCombobox*Listbox.foreground", p["text"])
        root.option_add("*TCombobox*Listbox.selectBackground", p["primary"])
        root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        root.option_add("*TCombobox*Listbox.font", (f, 10))
        root.option_add("*TCombobox*Listbox.borderWidth", 0)
        root.option_add("*TCombobox*Listbox.highlightThickness", 0)

        # ----- Таблиця -----
        style.configure("Treeview", font=(f, 10), rowheight=36, background=p["surface"],
                        fieldbackground=p["surface"], foreground=p["text"], borderwidth=0,
                        bordercolor=p["surface"], lightcolor=p["surface"], darkcolor=p["surface"])
        style.configure("Treeview.Heading", font=(f, 9, "bold"), background=p["surface2"],
                        foreground=p["muted"], padding=(8, 9), relief="flat", borderwidth=0,
                        bordercolor=p["surface2"], lightcolor=p["surface2"], darkcolor=p["surface2"])
        style.map("Treeview.Heading", background=[("active", p["hover"])], foreground=[("active", p["text"])])
        style.map("Treeview",
                  background=[("selected", p["select"])],
                  foreground=[("selected", p["select_text"])])

        # ----- Прокрутка та прогрес -----
        style.configure("Vertical.TScrollbar", background=p["border"], troughcolor=p["surface"],
                        bordercolor=p["surface"], lightcolor=p["border"], darkcolor=p["border"],
                        arrowcolor=p["muted"], arrowsize=14, gripcount=0, relief="flat")
        style.map("Vertical.TScrollbar", background=[("active", p["muted"])])
        style.configure("Horizontal.TProgressbar", background=p["primary"], troughcolor=p["surface2"],
                        bordercolor=p["bg"], lightcolor=p["primary"], darkcolor=p["primary"], thickness=4)

        # Створені раніше випадаючі списки комбобоксів потрібно перестворити з новими кольорами
        self._reset_popdowns(root)

        for callback in list(self._listeners):
            callback()

    def _reset_popdowns(self, widget):
        try:
            if widget.winfo_class() == "TCombobox":
                widget.tk.call("destroy", f"{widget}.popdown")
            for child in widget.winfo_children():
                self._reset_popdowns(child)
        except tk.TclError:
            pass


theme = Theme()
