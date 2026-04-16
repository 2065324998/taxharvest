"""Tests for wash sale detection — basic scenarios.

These tests cover simple wash sale cases where the replacement
purchase occurs AFTER the sale (the most common scenario).
"""

import pytest
from datetime import date
from taxharvest.portfolio import Portfolio
from taxharvest.washsale import detect_wash_sales


class TestBasicWashSale:
    def test_no_wash_sale_without_replacement(self):
        """Selling at a loss with no repurchase is not a wash sale."""
        p = Portfolio()
        p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        p.sell("AAPL", 100, 120.0, date(2024, 2, 15))
        detect_wash_sales(p)
        assert p.sales[0].is_wash_sale is False
        assert p.sales[0].gain_loss == -3000.0

    def test_no_wash_sale_on_gain(self):
        """Selling at a gain is never a wash sale."""
        p = Portfolio()
        p.buy("AAPL", 100, 100.0, date(2024, 1, 10))
        p.sell("AAPL", 100, 120.0, date(2024, 2, 15))
        p.buy("AAPL", 100, 115.0, date(2024, 2, 20))
        detect_wash_sales(p)
        assert p.sales[0].is_wash_sale is False

    def test_wash_sale_with_post_sale_purchase(self):
        """Buying replacement shares within 30 days AFTER sale."""
        p = Portfolio()
        p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        p.sell("AAPL", 100, 120.0, date(2024, 2, 15))
        p.buy("AAPL", 100, 125.0, date(2024, 3, 1))
        detect_wash_sales(p)
        sale = p.sales[0]
        assert sale.is_wash_sale is True
        assert sale.disallowed_loss == 3000.0
        assert sale.adjusted_gain_loss == 0.0

    def test_wash_sale_adjusts_replacement_basis(self):
        """Disallowed loss increases the replacement lot's cost basis."""
        p = Portfolio()
        p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        p.sell("AAPL", 100, 120.0, date(2024, 2, 15))
        p.buy("AAPL", 100, 125.0, date(2024, 3, 1))
        detect_wash_sales(p)
        replacement = p.get_lots("AAPL")[0]
        # Original basis: $12,500. Plus $3,000 disallowed = $15,500.
        assert replacement.cost_basis == 15500.0

    def test_no_wash_sale_outside_window(self):
        """Replacement purchased more than 30 days after sale."""
        p = Portfolio()
        p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        p.sell("AAPL", 100, 120.0, date(2024, 2, 15))
        p.buy("AAPL", 100, 125.0, date(2024, 3, 20))  # 33 days after
        detect_wash_sales(p)
        assert p.sales[0].is_wash_sale is False

    def test_different_symbol_not_wash_sale(self):
        """Buying a different security is not substantially identical."""
        p = Portfolio()
        p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        p.sell("AAPL", 100, 120.0, date(2024, 2, 15))
        p.buy("GOOG", 100, 125.0, date(2024, 2, 20))
        detect_wash_sales(p)
        assert p.sales[0].is_wash_sale is False

    def test_partial_wash_sale(self):
        """Only the replaced portion of the loss is disallowed."""
        p = Portfolio()
        p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        p.sell("AAPL", 100, 120.0, date(2024, 2, 15))
        p.buy("AAPL", 60, 125.0, date(2024, 3, 1))
        detect_wash_sales(p)
        sale = p.sales[0]
        assert sale.is_wash_sale is True
        assert sale.disallowed_loss == 1800.0  # 60% of $3,000
        assert sale.adjusted_gain_loss == -1200.0  # -$3,000 + $1,800

    def test_holding_period_transfers(self):
        """The replacement lot inherits the original holding period."""
        p = Portfolio()
        p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        p.sell("AAPL", 100, 120.0, date(2024, 2, 15))
        p.buy("AAPL", 100, 125.0, date(2024, 3, 1))
        detect_wash_sales(p)
        replacement = p.get_lots("AAPL")[0]
        assert replacement.holding_period_start == date(2024, 1, 10)
