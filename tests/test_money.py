"""Tests for the money helpers."""

from __future__ import annotations

import unittest
from decimal import Decimal

from finance_tracker.money import format_amount, from_cents, to_cents


class ToCentsTests(unittest.TestCase):
    def test_integer(self):
        self.assertEqual(to_cents(5), 500)

    def test_decimal_two_places(self):
        self.assertEqual(to_cents(Decimal("12.34")), 1234)

    def test_string_two_places(self):
        self.assertEqual(to_cents("12.34"), 1234)

    def test_negative(self):
        self.assertEqual(to_cents(Decimal("-7.50")), -750)

    def test_rounds_half_up(self):
        # 0.005 should round up to 0.01 = 1 cent
        self.assertEqual(to_cents(Decimal("0.005")), 1)

    def test_float_does_not_explode(self):
        # 0.1 + 0.2 == 0.30000000000000004 in float; routing through str
        # should keep us at 30 cents.
        self.assertEqual(to_cents(0.1 + 0.2), 30)

    def test_invalid_input_raises(self):
        with self.assertRaises(ValueError):
            to_cents("not a number")


class FromCentsTests(unittest.TestCase):
    def test_round_trip(self):
        for value in ["0.00", "1.23", "100.99", "-5.00"]:
            with self.subTest(value=value):
                cents = to_cents(value)
                self.assertEqual(from_cents(cents), Decimal(value))

    def test_rejects_non_int(self):
        with self.assertRaises(TypeError):
            from_cents("100")  # type: ignore[arg-type]


class FormatAmountTests(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(format_amount(1234), "USD 12.34")

    def test_negative(self):
        self.assertEqual(format_amount(-1234), "-USD 12.34")

    def test_thousands_separator(self):
        self.assertEqual(format_amount(123456), "USD 1,234.56")


if __name__ == "__main__":
    unittest.main()
