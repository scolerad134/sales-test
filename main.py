"""Build a daily sales report grouped by SKU and order date."""

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "sales.csv"
OUTPUT_FILE = BASE_DIR / "daily_by_sku.csv"
REQUIRED_COLUMNS = {
    "order_id",
    "order_date",
    "sku",
    "quantity",
    "price",
    "status",
}


@dataclass(frozen=True)
class SalesRow:
    """A validated and normalized source row."""

    order_id: str
    order_date: str
    sku: str
    quantity: int | None
    price: int
    status: str


@dataclass(frozen=True)
class ReportRow:
    """An aggregated row for one SKU and one date."""

    sku: str
    order_date: str
    orders: int
    revenue: int


@dataclass(frozen=True)
class ProcessingStats:
    """Counts useful for validating and explaining the processing."""

    input_rows: int
    unique_rows: int
    duplicates_removed: int
    report_rows: int
    total_orders: int
    total_revenue: int
    delivered_rows: int
    cancelled_rows: int


def normalize_status(value: str | None, line_number: int) -> str:
    """Normalize known status variants and reject unknown statuses."""
    status = (value or "").strip().lower()
    if status == "canceled":
        status = "cancelled"

    if status not in {"delivered", "cancelled"}:
        raise ValueError(
            f"Строка {line_number}: неизвестный или пустой статус {value!r}"
        )
    return status


def parse_row(raw_row: dict[str, str | None], line_number: int) -> SalesRow:
    """Validate values and convert a DictReader row into a typed row."""
    order_id = (raw_row.get("order_id") or "").strip()
    order_date = (raw_row.get("order_date") or "").strip()
    sku = (raw_row.get("sku") or "").strip()
    quantity_text = (raw_row.get("quantity") or "").strip()
    price_text = (raw_row.get("price") or "").strip()
    status = normalize_status(raw_row.get("status"), line_number)

    if not order_id or not order_date or not sku or not price_text:
        raise ValueError(
            f"Строка {line_number}: пустое обязательное поле "
            "order_id, order_date, sku или price"
        )

    try:
        # The source format specifies YYYY-MM-DD dates.
        parsed_date = date.fromisoformat(order_date)
        order_date = parsed_date.isoformat()
        quantity = int(quantity_text) if quantity_text else None
        price = int(price_text)
    except ValueError as error:
        raise ValueError(
            f"Строка {line_number}: некорректная дата или числовое значение: {error}"
        ) from error

    if status == "delivered" and quantity is None:
        raise ValueError(
            f"Строка {line_number}: у выкупленного заказа отсутствует quantity"
        )

    return SalesRow(
        order_id=order_id,
        order_date=order_date,
        sku=sku,
        quantity=quantity,
        price=price,
        status=status,
    )


def aggregate_rows(
    rows: Iterable[dict[str, str | None]],
) -> tuple[list[ReportRow], ProcessingStats]:
    """Deduplicate and aggregate source rows by (sku, order_date)."""
    groups: dict[tuple[str, str], dict[str, object]] = defaultdict(
        lambda: {"order_ids": set(), "revenue": 0}
    )
    seen_rows: set[SalesRow] = set()

    input_rows = 0
    duplicates_removed = 0
    delivered_rows = 0
    cancelled_rows = 0

    for line_number, raw_row in enumerate(rows, start=2):
        input_rows += 1
        row = parse_row(raw_row, line_number)

        # Normalize first, then compare the complete row. This also treats
        # capitalization/whitespace-only status differences as duplicates.
        if row in seen_rows:
            duplicates_removed += 1
            continue
        seen_rows.add(row)

        group = groups[(row.sku, row.order_date)]
        order_ids = group["order_ids"]
        assert isinstance(order_ids, set)
        order_ids.add(row.order_id)

        if row.status == "delivered":
            delivered_rows += 1
            # parse_row guarantees quantity exists for delivered rows.
            assert row.quantity is not None
            group["revenue"] = int(group["revenue"]) + row.quantity * row.price
        else:
            cancelled_rows += 1

    report = [
        ReportRow(
            sku=sku,
            order_date=order_date,
            orders=len(data["order_ids"]),
            revenue=int(data["revenue"]),
        )
        for (sku, order_date), data in sorted(groups.items())
    ]

    stats = ProcessingStats(
        input_rows=input_rows,
        unique_rows=len(seen_rows),
        duplicates_removed=duplicates_removed,
        report_rows=len(report),
        total_orders=sum(item.orders for item in report),
        total_revenue=sum(item.revenue for item in report),
        delivered_rows=delivered_rows,
        cancelled_rows=cancelled_rows,
    )
    return report, stats


def read_source(path: Path) -> list[dict[str, str | None]]:
    """Read the source CSV and verify that required columns are present."""
    with path.open("r", encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)
        if reader.fieldnames is None:
            raise ValueError("Исходный CSV пустой или не содержит заголовка")

        missing_columns = REQUIRED_COLUMNS.difference(reader.fieldnames)
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"В CSV отсутствуют обязательные колонки: {missing}")

        return list(reader)


def write_report(path: Path, report: list[ReportRow]) -> None:
    """Save the aggregated report in the required CSV format."""
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(["sku", "order_date", "orders", "revenue"])
        for row in report:
            writer.writerow([row.sku, row.order_date, row.orders, row.revenue])


def main() -> None:
    """Run the full processing pipeline using files next to this script."""
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Не найден файл {INPUT_FILE.name}. "
            "Положите sales.csv рядом с main.py."
        )

    source_rows = read_source(INPUT_FILE)
    report, stats = aggregate_rows(source_rows)
    write_report(OUTPUT_FILE, report)

    print("Обработка завершена.")
    print(f"Исходных строк: {stats.input_rows}")
    print(f"Удалено полных дублей: {stats.duplicates_removed}")
    print(f"Уникальных строк после очистки: {stats.unique_rows}")
    print(f"Выкупленных строк: {stats.delivered_rows}")
    print(f"Отменённых строк: {stats.cancelled_rows}")
    print(f"Строк в отчёте (SKU-день): {stats.report_rows}")
    print(f"Сумма orders: {stats.total_orders}")
    print(f"Общая выручка: {stats.total_revenue:,} руб.".replace(",", " "))
    print(f"Результат сохранён: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
