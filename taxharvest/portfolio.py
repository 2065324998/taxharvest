"""Portfolio and tax lot data structures.

A portfolio tracks individual tax lots — each purchase of shares is a
separate lot with its own cost basis, acquisition date, and quantity.
When shares are sold, lots are matched using FIFO (first-in, first-out)
ordering by acquisition date.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class TaxLot:
    """A single tax lot representing a purchase of shares.

    Attributes:
        symbol: Ticker symbol.
        quantity: Number of shares (positive).
        cost_basis: Total cost basis for this lot.
        acquired_date: Date the shares were acquired.
        lot_id: Unique identifier for tracking.
        holding_period_start: The effective start date for holding
            period calculation.  Usually same as acquired_date, but
            may differ when a wash sale transfers the holding period
            from the original lot.
    """
    symbol: str
    quantity: float
    cost_basis: float
    acquired_date: date
    lot_id: str
    holding_period_start: Optional[date] = None

    def __post_init__(self):
        if self.holding_period_start is None:
            self.holding_period_start = self.acquired_date

    @property
    def cost_per_share(self) -> float:
        if self.quantity == 0:
            return 0.0
        return self.cost_basis / self.quantity


@dataclass
class SaleRecord:
    """Record of a completed sale for tax reporting.

    Attributes:
        symbol: Ticker symbol sold.
        quantity: Number of shares sold.
        sale_date: Date of the sale.
        proceeds: Total sale proceeds.
        cost_basis: Cost basis of the shares sold.
        acquired_date: Original acquisition date of the lot.
        gain_loss: Realized gain or loss (proceeds - cost_basis).
        is_wash_sale: Whether this sale triggered a wash sale.
        disallowed_loss: Portion of loss disallowed under wash sale rules.
        adjusted_gain_loss: gain_loss + disallowed_loss (the reportable amount).
        replacement_lot_id: Lot ID that received the basis adjustment, if any.
    """
    symbol: str
    quantity: float
    sale_date: date
    proceeds: float
    cost_basis: float
    acquired_date: date
    gain_loss: float
    source_lot_id: Optional[str] = None
    is_wash_sale: bool = False
    disallowed_loss: float = 0.0
    adjusted_gain_loss: float = 0.0
    replacement_lot_id: Optional[str] = None

    def __post_init__(self):
        if self.adjusted_gain_loss == 0.0 and not self.is_wash_sale:
            self.adjusted_gain_loss = self.gain_loss


@dataclass
class Portfolio:
    """Collection of tax lots for multiple securities.

    Provides methods to add lots, sell shares (FIFO), and query
    current holdings.
    """
    lots: list[TaxLot] = field(default_factory=list)
    sales: list[SaleRecord] = field(default_factory=list)
    _next_lot_id: int = field(default=1, repr=False)

    def _generate_lot_id(self) -> str:
        lot_id = f"L{self._next_lot_id:04d}"
        self._next_lot_id += 1
        return lot_id

    def buy(self, symbol: str, quantity: float, price_per_share: float,
            trade_date: date) -> TaxLot:
        """Record a purchase, creating a new tax lot."""
        lot = TaxLot(
            symbol=symbol,
            quantity=quantity,
            cost_basis=round(quantity * price_per_share, 2),
            acquired_date=trade_date,
            lot_id=self._generate_lot_id(),
        )
        self.lots.append(lot)
        return lot

    def sell(self, symbol: str, quantity: float, price_per_share: float,
             trade_date: date) -> list[SaleRecord]:
        """Sell shares using FIFO lot matching.

        Returns a list of SaleRecord objects, one per lot consumed.
        Partial lot sales are supported — the remaining shares stay
        in the lot with proportionally reduced cost basis.
        """
        available = sorted(
            [lt for lt in self.lots
             if lt.symbol == symbol and lt.quantity > 0],
            key=lambda lt: lt.acquired_date,
        )
        remaining = quantity
        records = []

        for lot in available:
            if remaining <= 0:
                break
            sold_qty = min(lot.quantity, remaining)
            sold_basis = round(lot.cost_per_share * sold_qty, 2)
            proceeds = round(sold_qty * price_per_share, 2)
            gain_loss = round(proceeds - sold_basis, 2)

            record = SaleRecord(
                symbol=symbol,
                quantity=sold_qty,
                sale_date=trade_date,
                proceeds=proceeds,
                cost_basis=sold_basis,
                acquired_date=lot.acquired_date,
                gain_loss=gain_loss,
                source_lot_id=lot.lot_id,
                adjusted_gain_loss=gain_loss,
            )
            records.append(record)

            # Update the lot
            lot.cost_basis = round(lot.cost_basis - sold_basis, 2)
            lot.quantity = round(lot.quantity - sold_qty, 6)
            remaining = round(remaining - sold_qty, 6)

        self.sales.extend(records)
        return records

    def get_lots(self, symbol: str) -> list[TaxLot]:
        """Get all active lots for a symbol, sorted by acquisition date."""
        return sorted(
            [lt for lt in self.lots
             if lt.symbol == symbol and lt.quantity > 0],
            key=lambda lt: lt.acquired_date,
        )

    def get_holdings(self) -> dict[str, float]:
        """Get total shares held per symbol."""
        holdings: dict[str, float] = {}
        for lot in self.lots:
            if lot.quantity > 0:
                holdings[lot.symbol] = holdings.get(lot.symbol, 0) + lot.quantity
        return holdings

    def get_total_basis(self, symbol: str) -> float:
        """Get total cost basis for all active lots of a symbol."""
        return sum(lt.cost_basis for lt in self.lots
                   if lt.symbol == symbol and lt.quantity > 0)
