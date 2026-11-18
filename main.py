"""Точка входу застосунку «ПЗ для складання домашнього бюджету»:  python main.py"""
from app_logging import setup_logging


def main():
    setup_logging()   # журнал budget.log — до створення решти об'єктів
    from controller import BudgetController
    from main_window import BudgetApp

    BudgetApp(BudgetController()).mainloop()


if __name__ == "__main__":
    main()
