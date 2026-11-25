"""Задание 4. Реактивные ячейки: цена, кол-во, скидка → сумма → налог → итог.

Граф зависимостей содержит «ромб»: ``итог`` зависит от ``суммы`` напрямую
и через ``налог``. При изменении любой исходной ячейки каждая вычисляемая
пересчитывается не более одного раза, а подписчики видят только
согласованные значения.
"""

from __future__ import annotations

from rx_mini import Cell, transaction

TAX_RATE = 0.12


def subtotal(price: float, qty: int, discount: float) -> float:
    """Сумма со скидкой (чистая функция)."""
    return round(price * qty * (1 - discount), 2)


def tax(amount: float) -> float:
    """Налог (НДС 12 %)."""
    return round(amount * TAX_RATE, 2)


def total(amount: float, tax_value: float) -> float:
    """Итог = сумма + налог."""
    return round(amount + tax_value, 2)


def build_sheet() -> dict[str, Cell]:
    """Собрать «таблицу» ячеек."""
    price = Cell(1500.0, name="цена")
    qty = Cell(2, name="кол-во")
    discount = Cell(0.0, name="скидка")
    amount = Cell.formula(subtotal, price, qty, discount, name="сумма")
    tax_c = Cell.formula(tax, amount, name="налог")
    total_c = Cell.formula(total, amount, tax_c, name="итог")
    return {
        "price": price,
        "qty": qty,
        "discount": discount,
        "amount": amount,
        "tax": tax_c,
        "total": total_c,
    }


if __name__ == "__main__":
    sheet = build_sheet()
    log: list[str] = []
    sheet["total"].subscribe(lambda v: log.append(f"итог → {v}"))
    sheet["total"].subscribe(
        lambda v: log.append(
            f"  проверка согласованности: "
            f"{sheet['amount'].value} + "
            f"{sheet['tax'].value} = {v}"
        )
    )

    def show(title: str) -> None:
        """Напечатать состояние всех ячеек."""
        cells = ", ".join(f"{c.name}={c.value}" for c in sheet.values())
        print(f"{title:<26} {cells}")

    show("начало")
    sheet["qty"].set(3)
    show("кол-во = 3")
    sheet["discount"].set(0.1)
    show("скидка = 10 %")
    sheet["qty"].set(3)
    show("кол-во = 3 (без изменений)")
    transaction((sheet["price"], 2000.0), (sheet["qty"], 1))
    show("транзакция цена+кол-во")
    print("\n".join(log))
    print(
        "пересчётов:",
        {n: c.recompute_count for n, c in sheet.items() if not c.is_source},
    )
