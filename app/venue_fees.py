"""Fee models for Polymarket and Kalshi, and the net economics of a basket.

Both venues price their taker fee on the same functional form, the variance
of a binary outcome:

    fee_usd = shares * rate * p * (1 - p)

so the fee peaks at p = 0.50 and vanishes toward 0 and 1. What differs is the
rate (Polymarket sets it per category, Kalshi uses one rate), the rounding
(Kalshi rounds the order fee up to the next cent, Polymarket does not), and who
pays (Polymarket charges takers only and pays makers a rebate; Kalshi charges
takers and, on selected markets, makers too).

Why this module exists: a cross-venue price gap is not an edge until it clears
both fees, both spreads, and the cost of capital tied up until resolution. The
thesis scanner looked at gross gaps in a period when Polymarket was still fee
free; since the 2026 fee rollout every gap has to clear a wider band. The
functions here make that band explicit and testable.

Rates as documented by the venues in July 2026 (see FEE_SOURCES). Rates change,
so every entry point takes an override.

Streamlit-free and network-free: callers pass prices and sizes, this module
does arithmetic only. No order path, no credentials.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

FEE_SOURCES = {
    "polymarket": "docs.polymarket.com/trading/fees (abgerufen 2026-07-30)",
    "kalshi": "help.kalshi.com Fees + kalshi.com/docs/kalshi-fee-schedule.pdf "
              "(abgerufen 2026-07-30)",
}

#: Polymarket taker rate per category: fee_usd = shares * rate * p * (1 - p).
POLYMARKET_TAKER_RATES: dict[str, float] = {
    "crypto": 0.07,
    "sports": 0.05,
    "economics": 0.05,
    "culture": 0.05,
    "weather": 0.05,
    "other": 0.05,
    "finance": 0.04,
    "politics": 0.04,
    "mentions": 0.04,
    "tech": 0.04,
    "geopolitics": 0.0,
}
POLYMARKET_DEFAULT_CATEGORY = "other"

#: Makers pay nothing on Polymarket and receive a share of collected taker
#: fees back as a daily rebate (documented range 15-25 percent by category).
POLYMARKET_MAKER_REBATE_SHARE = 0.15

#: Kalshi: one taker rate for standard markets, order fee rounded UP to the
#: next cent. Selected markets also charge makers at roughly a quarter rate.
KALSHI_TAKER_RATE = 0.07
KALSHI_MAKER_RATE = 0.0175

#: Snapshot of the fee rules this module encodes, for report footers.
FEE_MODEL_VERSION = "2026-07-30"


def polymarket_category_rate(category: str | None,
                             rates: dict[str, float] | None = None) -> float:
    """Taker rate for a Polymarket category, falling back to the general rate."""
    table = rates or POLYMARKET_TAKER_RATES
    key = str(category or "").strip().lower()
    if key in table:
        return table[key]
    return table.get(POLYMARKET_DEFAULT_CATEGORY, 0.05)


def _variance(price: float) -> float:
    """p * (1 - p), clamped so prices outside (0, 1) cannot produce a credit."""
    p = max(0.0, min(1.0, float(price)))
    return p * (1.0 - p)


def polymarket_taker_fee(shares: float, price: float, category: str | None = None,
                         rates: dict[str, float] | None = None) -> float:
    """Taker fee in USD: ``shares * rate * p * (1 - p)``, no rounding."""
    rate = polymarket_category_rate(category, rates)
    return max(0.0, float(shares)) * rate * _variance(price)


def polymarket_maker_fee(shares: float, price: float, category: str | None = None,
                         rates: dict[str, float] | None = None) -> float:
    """Makers are never charged on Polymarket. Kept for a symmetric interface."""
    del shares, price, category, rates
    return 0.0


def polymarket_maker_rebate(shares: float, price: float, category: str | None = None,
                            rebate_share: float = POLYMARKET_MAKER_REBATE_SHARE,
                            rates: dict[str, float] | None = None) -> float:
    """Expected maker rebate in USD.

    The venue pays out a share of the taker fees it collected, so the rebate a
    maker earns on a fill is bounded by the fee the crossing taker paid. This
    models it as that upper bound times ``rebate_share``; the realised payout is
    a daily pro-rata distribution and can be lower.
    """
    fee_pool = polymarket_taker_fee(shares, price, category, rates)
    return fee_pool * max(0.0, float(rebate_share))


def kalshi_taker_fee(contracts: float, price: float,
                     rate: float = KALSHI_TAKER_RATE) -> float:
    """Taker fee in USD, rounded UP to the next cent at order level.

    Kalshi rounds the whole order up, not each contract, so a one-contract
    order pays the same cent as a small block. That rounding is a real cost for
    the small clip sizes a cross-venue basket usually gets filled in.
    """
    raw = max(0.0, float(contracts)) * float(rate) * _variance(price)
    if raw <= 0.0:
        return 0.0
    # Ohne das Runden vor dem Aufrunden macht Float-Rest aus exakt 1.75 Dollar
    # (0.07 * 100 * 0.25) den Wert 1.7500000000000002 und damit 1.76.
    return math.ceil(round(raw * 100.0, 9)) / 100.0


def kalshi_maker_fee(contracts: float, price: float,
                     rate: float = KALSHI_MAKER_RATE) -> float:
    """Maker fee on the markets that charge one; same rounding as the taker fee."""
    return kalshi_taker_fee(contracts, price, rate=rate)


def taker_fee(venue: str, shares: float, price: float,
              category: str | None = None) -> float:
    """Dispatch by venue name so callers can stay venue-agnostic."""
    name = str(venue or "").strip().lower()
    if name.startswith("kalshi"):
        return kalshi_taker_fee(shares, price)
    return polymarket_taker_fee(shares, price, category)


def fee_cents_per_share(venue: str, price: float, category: str | None = None,
                        shares: float = 100.0) -> float:
    """Taker fee in cents per share at a given price.

    Quoted on a 100-share clip by default so Kalshi's cent rounding does not
    dominate the number; pass ``shares`` to see the small-clip effect.
    """
    shares = max(1e-9, float(shares))
    return 100.0 * taker_fee(venue, shares, price, category) / shares


@dataclass(frozen=True)
class BasketLeg:
    """One side of a cross-venue basket: buy ``outcome`` at ``price`` on ``venue``."""

    venue: str
    price: float
    depth_shares: float = float("inf")
    category: str | None = None
    is_taker: bool = True

    def fee_usd(self, shares: float) -> float:
        if not self.is_taker:
            name = str(self.venue or "").lower()
            return (kalshi_maker_fee(shares, self.price)
                    if name.startswith("kalshi") else 0.0)
        return taker_fee(self.venue, shares, self.price, self.category)


def basket_economics(leg_a: BasketLeg, leg_b: BasketLeg,
                     shares: float | None = None,
                     days_to_resolution: float | None = None) -> dict:
    """Net economics of buying both sides of the same event across two venues.

    The two legs must be complementary (YES on one venue, NO on the other), so
    exactly one pays out 1.00 per share at resolution. Gross edge is therefore
    ``1 - (price_a + price_b)``; net edge subtracts both fees.

    ``shares`` defaults to the shallower book, which is the honest size: a gap
    that only exists for 20 shares is not a 1000-share trade. With
    ``days_to_resolution`` the result also carries the annualised return on the
    capital the basket locks up, which is the number that killed the carry-style
    cases in the earlier scanner runs.
    """
    size = float(shares) if shares is not None else min(
        leg_a.depth_shares, leg_b.depth_shares)
    if not math.isfinite(size) or size <= 0:
        size = 0.0
    size = min(size, leg_a.depth_shares, leg_b.depth_shares)

    cost_per_share = float(leg_a.price) + float(leg_b.price)
    gross_edge = 1.0 - cost_per_share
    fee_a = leg_a.fee_usd(size)
    fee_b = leg_b.fee_usd(size)
    fee_total = fee_a + fee_b
    fee_per_share = fee_total / size if size > 0 else 0.0
    net_edge = gross_edge - fee_per_share

    capital = cost_per_share * size
    result = {
        "shares": round(size, 4),
        "cost_per_share": round(cost_per_share, 6),
        "gross_edge_per_share": round(gross_edge, 6),
        "fee_per_share": round(fee_per_share, 6),
        "net_edge_per_share": round(net_edge, 6),
        "gross_edge_cents": round(100.0 * gross_edge, 4),
        "net_edge_cents": round(100.0 * net_edge, 4),
        "fee_usd_total": round(fee_total, 6),
        "net_profit_usd": round(net_edge * size, 6),
        "capital_usd": round(capital, 4),
        "breakeven_gap_cents": round(100.0 * fee_per_share, 4),
        "is_arbitrage": bool(net_edge > 0 and size > 0),
        "return_on_capital": round(net_edge * size / capital, 6) if capital > 0 else None,
        "annualised_return": None,
        "days_to_resolution": days_to_resolution,
        "fee_model_version": FEE_MODEL_VERSION,
    }
    if days_to_resolution is not None and capital > 0:
        result["annualised_return"] = annualised_return(
            result["return_on_capital"], days_to_resolution)
    return result


def annualised_return(return_on_capital: float | None,
                      days_to_resolution: float) -> float | None:
    """Compound a holding-period return to a yearly rate.

    A basket that nets 0.4 percent but sits for four months is not a 0.4 percent
    trade, it is a roughly 1.2 percent annual carry, which is the comparison
    that matters against simply holding the collateral.
    """
    if return_on_capital is None:
        return None
    days = float(days_to_resolution)
    if days <= 0:
        return None
    base = 1.0 + float(return_on_capital)
    if base <= 0:
        return -1.0
    return round(base ** (365.0 / days) - 1.0, 6)


def no_arb_band_cents(price_a: float, price_b: float, venue_a: str = "polymarket",
                      venue_b: str = "kalshi", category_a: str | None = None,
                      category_b: str | None = None,
                      shares: float = 100.0) -> float:
    """Width of the dead zone in cents: how far below 1.00 the pair must trade.

    This is the single number a cross-venue scanner needs as its threshold. Any
    observed gap smaller than this is a quote difference, not an arbitrage.
    """
    fee_a = taker_fee(venue_a, shares, price_a, category_a)
    fee_b = taker_fee(venue_b, shares, price_b, category_b)
    return round(100.0 * (fee_a + fee_b) / max(1e-9, shares), 4)


def round_trip_cost_cents(venue: str, price: float, category: str | None = None,
                          half_spread_cents: float = 0.0,
                          shares: float = 100.0) -> float:
    """Cost in cents per share of entering and exiting as a taker.

    Two fees plus twice the half spread. This is the hurdle a directional
    microstructure signal has to clear before it is worth acting on, and it is
    why a signal can be right about direction and still lose money.
    """
    fee = fee_cents_per_share(venue, price, category, shares)
    return round(2.0 * fee + 2.0 * float(half_spread_cents), 4)
