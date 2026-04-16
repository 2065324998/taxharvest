"""Tests for the tax-loss harvesting engine."""

import pytest
from datetime import date
from taxharvest.portfolio import Portfolio
from taxharvest.harvester import (
    process_trades,
    find_harvest_candidates,
    generate_tax_summary,
)


class TestProcessTrades:
    def test_process_buys_and_sells(self):
        p = Portfolio()
        trades = [
            {"action": "buy", "symbol": "AAPL", "quantity": 100,
             "price": 150.0, "date": "2024-01-10"},
            {"action": "sell", "symbol": "AAPL", "quantity": 50,
             "price": 160.0, "date": "2024-02-15"},
        ]
        result = process_trades(p, trades)
        assert result.get_holdings()["AAPL"] == 50
        assert len(result.sales) == 1

    def test_process_date_objects(self):
        p = Portfolio()
        trades = [
            {"action": "buy", "symbol": "AAPL", "quantity": 100,
             "price": 150.0, "date": date(2024, 1, 10)},
        ]
        result = process_trades(p, trades)
        assert result.get_holdings()["AAPL"] == 100


class TestFindCandidates:
    def test_finds_unrealized_losses(self):
        p = Portfolio()
        p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        candidates = find_harvest_candidates(
            p, {"AAPL": 120.0}, date(2024, 6, 1),
        )
        assert len(candidates) == 1
        assert candidates[0]["unrealized_loss"] == -3000.0

    def test_ignores_gains(self):
        p = Portfolio()
        p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        candidates = find_harvest_candidates(
            p, {"AAPL": 160.0}, date(2024, 6, 1),
        )
        assert len(candidates) == 0


class TestTaxSummary:
    def test_summary_no_wash_sales(self):
        p = Portfolio()
        p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        p.sell("AAPL", 100, 160.0, date(2024, 6, 1))
        summary = generate_tax_summary(p)
        assert summary["total_proceeds"] == 16000.0
        assert summary["total_cost_basis"] == 15000.0
        assert summary["total_gain_loss"] == 1000.0
        assert summary["wash_sale_count"] == 0
