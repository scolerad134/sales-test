"""Unit tests for the sales aggregation logic."""

import unittest

from main import aggregate_rows, normalize_status


class NormalizeStatusTests(unittest.TestCase):
    def test_status_variants_are_normalized(self):
        self.assertEqual(normalize_status(" Delivered ", 2), "delivered")
        self.assertEqual(normalize_status("CANCELLED", 3), "cancelled")
        self.assertEqual(normalize_status("canceled", 4), "cancelled")

    def test_unknown_status_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_status("pending", 2)


class AggregateRowsTests(unittest.TestCase):
    def test_duplicate_cancelled_and_delivered_rows(self):
        rows = [
            {
                "order_id": "101",
                "order_date": "2026-09-01",
                "sku": "SKU-1",
                "quantity": "2",
                "price": "100",
                "status": "delivered",
            },
            {
                "order_id": "101",
                "order_date": "2026-09-01",
                "sku": "SKU-1",
                "quantity": "2",
                "price": "100",
                "status": "delivered",
            },
            {
                "order_id": "102",
                "order_date": "2026-09-01",
                "sku": "SKU-1",
                "quantity": "",
                "price": "100",
                "status": "cancelled",
            },
        ]

        report, stats = aggregate_rows(rows)

        self.assertEqual(len(report), 1)
        self.assertEqual(report[0].sku, "SKU-1")
        self.assertEqual(report[0].order_date, "2026-09-01")
        self.assertEqual(report[0].orders, 2)
        self.assertEqual(report[0].revenue, 200)
        self.assertEqual(stats.duplicates_removed, 1)
        self.assertEqual(stats.total_orders, 2)
        self.assertEqual(stats.total_revenue, 200)

    def test_missing_quantity_for_delivered_is_rejected(self):
        rows = [
            {
                "order_id": "201",
                "order_date": "2026-09-01",
                "sku": "SKU-1",
                "quantity": "",
                "price": "100",
                "status": "delivered",
            }
        ]
        with self.assertRaises(ValueError):
            aggregate_rows(rows)

    def test_report_is_sorted_by_sku_then_date(self):
        rows = [
            {
                "order_id": "1",
                "order_date": "2026-09-02",
                "sku": "SKU-B",
                "quantity": "1",
                "price": "10",
                "status": "delivered",
            },
            {
                "order_id": "2",
                "order_date": "2026-09-02",
                "sku": "SKU-A",
                "quantity": "1",
                "price": "10",
                "status": "delivered",
            },
            {
                "order_id": "3",
                "order_date": "2026-09-01",
                "sku": "SKU-A",
                "quantity": "1",
                "price": "10",
                "status": "delivered",
            },
        ]

        report, _ = aggregate_rows(rows)
        self.assertEqual(
            [(row.sku, row.order_date) for row in report],
            [
                ("SKU-A", "2026-09-01"),
                ("SKU-A", "2026-09-02"),
                ("SKU-B", "2026-09-02"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
