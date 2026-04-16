"""Tax-loss harvesting engine.

Identifies opportunities to realize losses for tax purposes while
maintaining portfolio exposure, and processes a sequence of trades
with wash sale detection applied at the end.
"""

from datetime import date
from taxharvest.portfolio import Portfolio, SaleRecord
from taxharvest.washsale import detect_wash_sales


def process_trades(portfolio: Portfolio, trades: list[dict]) -> Portfolio:
    """Execute a list of trades against a portfolio.

    Each trade dict has keys:
        action: "buy" or "sell"
        symbol: ticker symbol
        quantity: number of shares
        price: price per share
        date: trade date (date object or "YYYY-MM-DD" string)

    After all trades are processed, wash sale detection runs
    to flag disallowed losses and adjust cost bases.

    Returns the updated portfolio.
    """
    for trade in trades:
        trade_date = trade["date"]
        if isinstance(trade_date, str):
            trade_date = date.fromisoformat(trade_date)

        if trade["action"] == "buy":
            portfolio.buy(
                symbol=trade["symbol"],
                quantity=trade["quantity"],
                price_per_share=trade["price"],
                trade_date=trade_date,
            )
        elif trade["action"] == "sell":
            portfolio.sell(
                symbol=trade["symbol"],
                quantity=trade["quantity"],
                price_per_share=trade["price"],
                trade_date=trade_date,
            )

    detect_wash_sales(portfolio)
    return portfolio


def find_harvest_candidates(
    portfolio: Portfolio,
    current_prices: dict[str, float],
    as_of: date,
    min_loss: float = 100.0,
) -> list[dict]:
    """Identify lots with unrealized losses suitable for harvesting.

    Returns a list of dicts describing each candidate lot:
        lot_id, symbol, quantity, cost_basis, current_value,
        unrealized_loss, acquired_date, holding_days
    """
    candidates = []
    for lot in portfolio.lots:
        if lot.quantity <= 0:
            continue
        price = current_prices.get(lot.symbol)
        if price is None:
            continue
        current_value = round(lot.quantity * price, 2)
        unrealized = round(current_value - lot.cost_basis, 2)
        if unrealized >= 0:
            continue
        if abs(unrealized) < min_loss:
            continue

        holding_days = (as_of - lot.holding_period_start).days
        candidates.append({
            "lot_id": lot.lot_id,
            "symbol": lot.symbol,
            "quantity": lot.quantity,
            "cost_basis": lot.cost_basis,
            "current_value": current_value,
            "unrealized_loss": unrealized,
            "acquired_date": lot.acquired_date,
            "holding_days": holding_days,
        })

    candidates.sort(key=lambda c: c["unrealized_loss"])
    return candidates


def generate_tax_summary(portfolio: Portfolio) -> dict:
    """Generate a summary of realized gains/losses for tax reporting.

    Returns a dict with:
        total_proceeds: sum of all sale proceeds
        total_cost_basis: sum of all cost bases for sold shares
        total_gain_loss: sum of raw gains/losses
        total_disallowed: sum of disallowed wash sale losses
        net_reportable: total gains/losses after wash sale adjustments
        wash_sale_count: number of wash sale events
        sales: list of all SaleRecord dicts
    """
    total_proceeds = 0.0
    total_basis = 0.0
    total_gl = 0.0
    total_disallowed = 0.0
    wash_count = 0

    for sale in portfolio.sales:
        total_proceeds += sale.proceeds
        total_basis += sale.cost_basis
        total_gl += sale.gain_loss
        if sale.is_wash_sale:
            total_disallowed += sale.disallowed_loss
            wash_count += 1

    net_reportable = round(total_gl + total_disallowed, 2)

    return {
        "total_proceeds": round(total_proceeds, 2),
        "total_cost_basis": round(total_basis, 2),
        "total_gain_loss": round(total_gl, 2),
        "total_disallowed": round(total_disallowed, 2),
        "net_reportable": net_reportable,
        "wash_sale_count": wash_count,
        "sales": [
            {
                "symbol": s.symbol,
                "quantity": s.quantity,
                "sale_date": s.sale_date.isoformat(),
                "proceeds": s.proceeds,
                "cost_basis": s.cost_basis,
                "gain_loss": s.gain_loss,
                "is_wash_sale": s.is_wash_sale,
                "disallowed_loss": s.disallowed_loss,
                "adjusted_gain_loss": s.adjusted_gain_loss,
            }
            for s in portfolio.sales
        ],
    }
