"""Polymarket's liquidity reward program, as a scoring model.

Every PnL number in this repo so far treats a market maker's income as the
spread it earns minus what informed counterparties take back. On Polymarket
that is incomplete, and the missing term is not small: the venue pays a daily
pool to makers simply for resting two-sided orders close to the mid, whether or
not those orders ever fill.

Measured from the venue's own CLOB API on 2026-07-31: 9,562 markets carried a
reward pool, totalling 139,138 USD per day. Median pool 3.00 USD, mean 14.55,
largest 1,000. The modal market pays for quotes within 4.5 cents of the mid at
a minimum size of 20 shares, which is wider than a typical quoting engine would
post anyway. In other words the money is paid for presence, not for prediction.

The scoring rule (docs.polymarket.com/market-makers/liquidity-rewards):

    S(v, s) = ((v - s) / v)^2 * b

with v the maximum qualifying spread from the midpoint in cents, s the order's
own spread from the midpoint, and b an in-game multiplier. Per side the
size-weighted scores Q_one and Q_two are combined as

    midpoint in [0.10, 0.90]:  Q_min = max(min(Q1, Q2), max(Q1/c, Q2/c))
    otherwise:                 Q_min = min(Q1, Q2)

with c currently 3.0, so a single-sided quote still scores at a third of the
rate in the middle of the book but nothing at the wings. Scores are sampled
across the epoch and normalised against every other maker in the same market.

That normalisation is the honest limit of any model: a maker's payout depends
on what everyone else quoted, which is not observable from public data. So
nothing here predicts a payout. The functions compute our own score exactly as
documented and then take the competition as an explicit parameter, so results
are always reported as a sensitivity rather than a number.

Streamlit-free and network-free. No order path, no credentials.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Gemessen an der CLOB-API (sampling-markets) am 2026-07-31.
REWARD_SNAPSHOT_DATE = "2026-07-31"
MARKETS_WITH_POOL = 9562
TOTAL_DAILY_POOL_USD = 139138.0
POOL_MEDIAN_USD = 3.0
POOL_MEAN_USD = 14.55
POOL_MAX_USD = 1000.0

#: Modalwerte der Reward-Konfiguration aus derselben Abfrage.
MAX_SPREAD_CENTS_MODE = 4.5
MIN_SIZE_SHARES_MODE = 20.0

#: Zwei-Seiten-Bonus laut Doku, aktuell auf allen Maerkten 3.0.
TWO_SIDED_BOOST = 3.0
#: Ausserhalb dieses Mittelband ist beidseitiges Quoten Pflicht.
TWO_SIDED_REQUIRED_OUTSIDE = (0.10, 0.90)

#: Wie stark die uebrige Konkurrenz im Markt gewichtet wird, als Vielfaches
#: des eigenen Scores. Reine Annahme, deshalb immer als Spanne berichten.
COMPETITION_SCENARIOS = (1.0, 5.0, 20.0)


def order_score(spread_cents: float, max_spread_cents: float = MAX_SPREAD_CENTS_MODE,
                multiplier: float = 1.0) -> float:
    """S(v, s) for one order. Zero once the order sits at or beyond the cap.

    Quadratic, so being twice as close to the mid is worth four times as much.
    That convexity is why a reward-driven maker quotes far tighter than a
    spread-driven one would.
    """
    v = float(max_spread_cents)
    s = float(spread_cents)
    if v <= 0 or s < 0 or s >= v:
        return 0.0
    return ((v - s) / v) ** 2 * float(multiplier)


def qualifies(size_shares: float, min_size_shares: float = MIN_SIZE_SHARES_MODE) -> bool:
    """Orders below the market's minimum size score nothing at all."""
    return float(size_shares) >= float(min_size_shares)


def side_score(orders: list[tuple[float, float]],
               max_spread_cents: float = MAX_SPREAD_CENTS_MODE,
               min_size_shares: float = MIN_SIZE_SHARES_MODE,
               multiplier: float = 1.0) -> float:
    """Size-weighted score of one side: ``orders`` are (spread_cents, size)."""
    total = 0.0
    for spread_cents, size in orders:
        if not qualifies(size, min_size_shares):
            continue
        total += order_score(spread_cents, max_spread_cents, multiplier) * float(size)
    return total


def q_min(q_one: float, q_two: float, midpoint: float,
          boost: float = TWO_SIDED_BOOST) -> float:
    """Combine both sides under the documented two-sided rule."""
    low, high = TWO_SIDED_REQUIRED_OUTSIDE
    q_one = max(0.0, float(q_one))
    q_two = max(0.0, float(q_two))
    if low <= float(midpoint) <= high and boost > 0:
        return max(min(q_one, q_two), max(q_one / boost, q_two / boost))
    return min(q_one, q_two)


def quote_score(bid_spread_cents: float | None, ask_spread_cents: float | None,
                size_shares: float, midpoint: float,
                max_spread_cents: float = MAX_SPREAD_CENTS_MODE,
                min_size_shares: float = MIN_SIZE_SHARES_MODE,
                multiplier: float = 1.0) -> float:
    """Score of one two-sided quote. A missing side counts as zero on that side."""
    q_one = side_score([(bid_spread_cents, size_shares)] if bid_spread_cents is not None
                       else [], max_spread_cents, min_size_shares, multiplier)
    q_two = side_score([(ask_spread_cents, size_shares)] if ask_spread_cents is not None
                       else [], max_spread_cents, min_size_shares, multiplier)
    return q_min(q_one, q_two, midpoint)


def reward_share(our_score: float, competition_multiple: float) -> float:
    """Our slice of the pool if the rest of the market scores a multiple of us."""
    our_score = max(0.0, float(our_score))
    if our_score <= 0:
        return 0.0
    others = our_score * max(0.0, float(competition_multiple))
    return our_score / (our_score + others)


def daily_reward_usd(our_score: float, competition_multiple: float,
                     pool_usd: float = POOL_MEDIAN_USD) -> float:
    """Expected daily payout in USD under one competition assumption."""
    return reward_share(our_score, competition_multiple) * max(0.0, float(pool_usd))


@dataclass(frozen=True)
class RewardEstimate:
    """What a quoting run would have earned in rewards, as a range."""

    hours_quoted: float
    mean_score: float
    qualifying_share: float
    pool_usd_per_day: float
    markets: int

    def usd(self, competition_multiple: float) -> float:
        """Reward for the observed window, pro rata to a full day.

        The score is already a time-weighted average over the window, so the
        only scaling left is the window length against 24 hours, times the
        number of markets quoted in parallel.
        """
        if self.mean_score <= 0 or self.hours_quoted <= 0:
            return 0.0
        per_market_day = daily_reward_usd(self.mean_score, competition_multiple,
                                          self.pool_usd_per_day)
        return per_market_day * (self.hours_quoted / 24.0) * max(1, self.markets)

    def sensitivity(self, scenarios: tuple[float, ...] = COMPETITION_SCENARIOS
                    ) -> list[dict]:
        return [
            {
                "competition_multiple": multiple,
                "our_share": round(reward_share(self.mean_score, multiple), 6),
                "reward_usd": round(self.usd(multiple), 4),
            }
            for multiple in scenarios
        ]

    def as_dict(self) -> dict:
        return {
            "hours_quoted": round(self.hours_quoted, 3),
            "mean_score": round(self.mean_score, 6),
            "qualifying_share": round(self.qualifying_share, 4),
            "pool_usd_per_day": self.pool_usd_per_day,
            "markets": self.markets,
            "snapshot_date": REWARD_SNAPSHOT_DATE,
            "sensitivity": self.sensitivity(),
        }


def estimate_from_quotes(samples: list[tuple[float, float, float | None, float | None, float]],
                         quote_usd: float,
                         pool_usd: float = POOL_MEDIAN_USD,
                         markets: int = 1,
                         max_spread_cents: float = MAX_SPREAD_CENTS_MODE,
                         min_size_shares: float = MIN_SIZE_SHARES_MODE) -> RewardEstimate:
    """Time-weighted reward score over a quoting run.

    ``samples`` are ``(duration_s, midpoint, bid_price, ask_price, mid)`` where
    the prices are our own quotes, or None for a side we were not showing. The
    program samples the book on a fixed cadence, so weighting each observed
    quote by how long it stood is the faithful analogue of that.
    """
    total_time = 0.0
    weighted = 0.0
    qualifying_time = 0.0
    for duration_s, midpoint, bid, ask, mid in samples:
        duration_s = max(0.0, float(duration_s))
        if duration_s <= 0:
            continue
        total_time += duration_s
        size = quote_usd / mid if mid and mid > 0 else 0.0
        bid_spread = (mid - bid) * 100.0 if bid is not None and mid else None
        ask_spread = (ask - mid) * 100.0 if ask is not None and mid else None
        score = quote_score(bid_spread, ask_spread, size, midpoint,
                            max_spread_cents, min_size_shares)
        weighted += score * duration_s
        if score > 0:
            qualifying_time += duration_s
    if total_time <= 0:
        return RewardEstimate(0.0, 0.0, 0.0, pool_usd, markets)
    return RewardEstimate(
        hours_quoted=total_time / 3600.0,
        mean_score=weighted / total_time,
        qualifying_share=qualifying_time / total_time,
        pool_usd_per_day=pool_usd,
        markets=markets,
    )
