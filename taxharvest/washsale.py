"""Wash sale detection and cost basis adjustment.

IRS Publication 550 defines wash sale rules for securities:

A wash sale occurs when you sell stock or securities at a loss and,
within 30 days before or after the sale, you:

    1. Buy substantially identical stock or securities,
    2. Acquire substantially identical stock or securities in a
       fully taxable trade, or
    3. Acquire a contract or option to buy substantially identical
       stock or securities.

The 61-day window (30 days before + sale day + 30 days after) is the
wash sale period.  When a wash sale is triggered:

    - The loss on the sale is DISALLOWED for tax purposes.
    - The disallowed loss is ADDED to the cost basis of the
      replacement shares (the shares that triggered the wash sale).
    - The holding period of the ORIGINAL shares carries over to the
      replacement shares.

Partial wash sales apply when only some of the sold shares are
"replaced."  For example, selling 100 shares at a loss and buying
back 70 within the window means 70 shares' worth of the loss is
disallowed and 30 shares' worth is allowed.

Substantially identical securities
----------------------------------
For this implementation, two securities are substantially identical
if and only if they share the same ticker symbol.  (In practice the
IRS definition is broader, but symbol matching is the standard
automated approach.)

Replacement share matching
--------------------------
When a wash sale is detected, replacement shares are matched to the
sale using FIFO ordering of purchases within the 61-day window.  If
multiple purchases fall in the window, the earliest purchase is
matched first.  The disallowed loss is allocated proportionally
across matched replacement lots based on the number of shares each
lot contributes.

Cascading adjustments
---------------------
When a lot's cost basis is increased by a wash sale adjustment,
any subsequent sale of that lot must use the UPDATED basis to
determine whether it too produces a loss.  A sale that appeared
to be a gain at face value may become a loss after the basis
adjustment, potentially triggering another wash sale.  Sales
must therefore be evaluated in chronological order with lot
bases updated between evaluations.
"""

from datetime import date, timedelta
from taxharvest.portfolio import Portfolio, SaleRecord, TaxLot


def detect_wash_sales(portfolio: Portfolio) -> None:
    """Scan all sales in the portfolio and apply wash sale rules.

    For each sale at a loss, checks whether substantially identical
    securities were purchased within the 61-day wash sale window
    (30 days before through 30 days after the sale date).

    When a wash sale is detected:
        1. The loss (or portion thereof) is disallowed.
        2. The disallowed amount is added to the cost basis of
           the replacement lot(s).
        3. The holding period start of the replacement lot(s) is
           set to the original lot's holding period start.

    This function modifies SaleRecord and TaxLot objects in place.
    """
    for sale in portfolio.sales:
        if sale.gain_loss >= 0:
            continue  # No loss — not a wash sale candidate

        loss_amount = abs(sale.gain_loss)
        sale_date = sale.sale_date

        # Find replacement purchases within the wash sale window
        window_start = sale_date
        window_end = sale_date + timedelta(days=30)

        replacements = _find_replacements(
            portfolio, sale.symbol, window_start, window_end,
            sale.quantity,
        )

        if not replacements:
            continue

        # Calculate how many shares are "replaced"
        replaced_qty = sum(qty for _, qty in replacements)
        replaced_qty = min(replaced_qty, sale.quantity)

        # Proportion of loss that is disallowed
        disallowed_ratio = replaced_qty / sale.quantity
        disallowed_loss = round(loss_amount * disallowed_ratio, 2)

        sale.is_wash_sale = True
        sale.disallowed_loss = disallowed_loss
        sale.adjusted_gain_loss = round(
            sale.gain_loss + disallowed_loss, 2
        )

        # Adjust cost basis of replacement lots
        _adjust_replacement_basis(
            replacements, disallowed_loss, replaced_qty,
            sale.acquired_date,
        )
        if replacements:
            sale.replacement_lot_id = replacements[0][0].lot_id


def _find_replacements(
    portfolio: Portfolio,
    symbol: str,
    window_start: date,
    window_end: date,
    sold_quantity: float,
) -> list[tuple[TaxLot, float]]:
    """Find replacement lots within the wash sale window.

    Returns a list of (lot, matched_quantity) tuples in FIFO order.
    Only lots that were acquired within [window_start, window_end]
    and still have shares are considered.
    """
    candidates = []
    for lot in portfolio.lots:
        if lot.symbol != symbol or lot.quantity <= 0:
            continue
        if lot.acquired_date < window_start or lot.acquired_date > window_end:
            continue
        candidates.append(lot)

    # FIFO: earliest acquisition first
    candidates.sort(key=lambda lt: lt.acquired_date)

    matched = []
    remaining = sold_quantity
    for lot in candidates:
        if remaining <= 0:
            break
        qty = min(lot.quantity, remaining)
        matched.append((lot, qty))
        remaining = round(remaining - qty, 6)

    return matched


def _adjust_replacement_basis(
    replacements: list[tuple[TaxLot, float]],
    disallowed_loss: float,
    total_replaced: float,
    original_acquired: date,
) -> None:
    """Add disallowed loss to the cost basis of replacement lots.

    The disallowed loss is distributed across replacement lots
    proportionally based on the number of matched shares.  Each
    lot's holding_period_start is also updated to carry over
    from the original shares.
    """
    for lot, qty in replacements:
        share = qty / total_replaced
        basis_adjustment = round(disallowed_loss * share, 2)
        lot.cost_basis = round(lot.cost_basis + basis_adjustment, 2)
        lot.holding_period_start = original_acquired
