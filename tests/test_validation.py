"""Tests for the validation module."""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from finance_tracker.exceptions import ValidationError
from finance_tracker.validation import (
    validate_account_name,
    validate_amount,
    validate_category_name,
    validate_currency,
    validate_date,
    validate_date_range,
    validate_description,
    validate_notes,
)


class AccountNameTests(unittest.TestCase):
    def test_strips_whitespace(self):
        self.assertEqual(validate_account_name("  Main  "), "Main")

    def test_rejects_empty(self):
        for v in [None, "", "   "]:
            with self.subTest(value=v):
                with self.assertRaises(ValidationError):
                    validate_account_name(v)  # type: ignore[arg-type]

    def test_rejects_too_long(self):
        with self.assertRaises(ValidationError):
            validate_account_name("x" * 101)

    def test_allows_typical_punctuation(self):
        self.assertEqual(validate_account_name("Joint - Chase (Sara&Me)"), "Joint - Chase (Sara&Me)")


class CategoryNameTests(unittest.TestCase):
    def test_dot_rejected(self):
        with self.assertRaises(ValidationError):
            validate_category_name("Food.Groceries")

    def test_strips(self):
        self.assertEqual(validate_category_name("  Food  "), "Food")


class CurrencyTests(unittest.TestCase):
    def test_uppercases(self):
        self.assertEqual(validate_currency("usd"), "USD")

    def test_rejects_non_iso(self):
        for v in ["US", "USDX", "12A", ""]:
            with self.subTest(value=v):
                with self.assertRaises(ValidationError):
                    validate_currency(v)


class AmountTests(unittest.TestCase):
    def test_accepts_string(self):
        self.assertEqual(validate_amount("12.34"), 1234)

    def test_accepts_decimal(self):
        self.assertEqual(validate_amount(Decimal("-7.5")), -750)

    def test_rejects_zero_by_default(self):
        with self.assertRaises(ValidationError):
            validate_amount("0")

    def test_allows_zero_when_explicit(self):
        self.assertEqual(validate_amount("0", allow_zero=True), 0)

    def test_rejects_garbage(self):
        with self.assertRaises(ValidationError):
            validate_amount("abc")

    def test_rejects_empty(self):
        with self.assertRaises(ValidationError):
            validate_amount("")


class DateTests(unittest.TestCase):
    def test_iso_string(self):
        self.assertEqual(validate_date("2026-03-04"), date(2026, 3, 4))

    def test_passthrough_date(self):
        d = date(2026, 1, 1)
        self.assertIs(validate_date(d), d)

    def test_rejects_garbage(self):
        with self.assertRaises(ValidationError):
            validate_date("not a date")

    def test_rejects_none(self):
        with self.assertRaises(ValidationError):
            validate_date(None)


class DescriptionAndNotesTests(unittest.TestCase):
    def test_description_default(self):
        self.assertEqual(validate_description(None), "")

    def test_notes_empty_becomes_none(self):
        self.assertIsNone(validate_notes("   "))

    def test_notes_too_long(self):
        with self.assertRaises(ValidationError):
            validate_notes("x" * 1001)


class DateRangeTests(unittest.TestCase):
    def test_inverted_range_rejected(self):
        with self.assertRaises(ValidationError):
            validate_date_range(date(2026, 5, 1), date(2026, 1, 1))

    def test_either_side_optional(self):
        self.assertEqual(
            validate_date_range(None, date(2026, 1, 1)),
            (None, date(2026, 1, 1)),
        )


if __name__ == "__main__":
    unittest.main()
