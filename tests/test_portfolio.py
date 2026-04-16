"""Tests for portfolio and tax lot management."""

import pytest
from datetime import date
from taxharvest.portfolio import Portfolio, TaxLot, SaleRecord


class TestTaxLot:
    def test_cost_per_share(self):
        lot = TaxLot("AAPL", 100, 15000.0, date(2024, 1, 10), "L0001")
        assert lot.cost_per_share == 150.0

    def test_holding_period_defaults_to_acquired(self):
        lot = TaxLot("AAPL", 100, 15000.0, date(2024, 1, 10), "L0001")
        assert lot.holding_period_start == date(2024, 1, 10)


class TestPortfolioBuy:
    def test_buy_creates_lot(self):
        p = Portfolio()
        lot = p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        assert lot.symbol == "AAPL"
        assert lot.quantity == 100
        assert lot.cost_basis == 15000.0

    def test_buy_assigns_unique_lot_ids(self):
        p = Portfolio()
        lot1 = p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        lot2 = p.buy("AAPL", 50, 140.0, date(2024, 1, 15))
        assert lot1.lot_id != lot2.lot_id

    def test_get_holdings(self):
        p = Portfolio()
        p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        p.buy("GOOG", 50, 140.0, date(2024, 1, 15))
        holdings = p.get_holdings()
        assert holdings["AAPL"] == 100
        assert holdings["GOOG"] == 50


class TestPortfolioSell:
    def test_sell_fifo(self):
        p = Portfolio()
        p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        p.buy("AAPL", 100, 130.0, date(2024, 2, 1))
        records = p.sell("AAPL", 100, 120.0, date(2024, 2, 15))
        assert len(records) == 1
        # Should sell the Jan 10 lot first (FIFO)
        assert records[0].acquired_date == date(2024, 1, 10)
        assert records[0].cost_basis == 15000.0

    def test_sell_partial_lot(self):
        p = Portfolio()
        p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        records = p.sell("AAPL", 60, 120.0, date(2024, 2, 15))
        assert records[0].quantity == 60
        lots = p.get_lots("AAPL")
        assert len(lots) == 1
        assert lots[0].quantity == 40
        assert lots[0].cost_basis == 6000.0  # 40 * $150

    def test_sell_across_lots(self):
        p = Portfolio()
        p.buy("AAPL", 60, 150.0, date(2024, 1, 10))
        p.buy("AAPL", 60, 130.0, date(2024, 2, 1))
        records = p.sell("AAPL", 80, 120.0, date(2024, 2, 15))
        assert len(records) == 2
        assert records[0].quantity == 60  # First lot fully consumed
        assert records[1].quantity == 20  # Partial from second lot

    def test_gain_loss_calculation(self):
        p = Portfolio()
        p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        records = p.sell("AAPL", 100, 120.0, date(2024, 2, 15))
        assert records[0].gain_loss == -3000.0  # $12,000 - $15,000

    def test_total_basis(self):
        p = Portfolio()
        p.buy("AAPL", 100, 150.0, date(2024, 1, 10))
        p.buy("AAPL", 50, 130.0, date(2024, 2, 1))
        assert p.get_total_basis("AAPL") == 21500.0
