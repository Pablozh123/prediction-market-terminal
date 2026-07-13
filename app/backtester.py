"""Copy-trade backtest engine: replay a wallet's Polymarket trades with fees/slippage.

Streamlit-free so it can be unit-tested and reused by scripts. Data fetching is
injectable; by default it uses ``src.prediction_markets``.

Model:
- Replays the source wallet's BUY/SELL trades chronologically inside the window.
- BUYs are copied with the configured stake sizing (fee + slippage priced in).
- SELLs are mirrored proportionally to the fraction the source sold.
- After the replay, remaining open positions are settled against market data:
  resolved markets pay out at the final token price (no fee on redemption),
  unresolved positions are marked-to-market at the current token price.
- Open positions are valued at entry cost until they close, so the equity curve
  steps on realized events; the final point includes mark-to-market.
- A flat-stake benchmark replays the same signals with a constant stake.
- Kelly sizing (``SIZING_KELLY``) reads ``stake_value`` as the assumed edge in
  probability points over the copied entry price and stakes
  ``kelly_fraction`` × full Kelly of current equity (quarter-Kelly by default):
  the estimate is uncertain and platform/resolution risk lives outside the
  model, and past f* expected log growth falls off a cliff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from app.quant import kelly_binary

SIZING_FIXED = "fixed"
SIZING_PERCENT = "percent"
SIZING_MIRROR = "mirror"
SIZING_PORTFOLIO = "portfolio_share"
SIZING_KELLY = "kelly"
SIZING_MODES = (SIZING_FIXED, SIZING_PERCENT, SIZING_MIRROR, SIZING_PORTFOLIO, SIZING_KELLY)

STRATEGY_COPY = "copy"
STRATEGY_FADE = "fade"
STRATEGIES = (STRATEGY_COPY, STRATEGY_FADE)

MIN_STAKE = 1.0

LEDGER_COLUMNS = [
    "time",
    "action",
    "status",
    "title",
    "outcome",
    "source_notional",
    "stake",
    "exec_price",
    "shares",
    "fee",
    "realized_pnl",
    "equity_after",
    "note",
    "asset",
    "market_key",
]

POSITION_COLUMNS = [
    "asset",
    "market_key",
    "title",
    "outcome",
    "shares",
    "cost_basis",
    "avg_price",
    "current_price",
    "value",
    "unrealized_pnl",
    "market_status",
]


@dataclass(frozen=True)
class BacktestConfig:
    wallet: str
    days: int = 90
    bankroll: float = 1000.0
    sizing_mode: str = SIZING_FIXED
    stake_value: float = 25.0
    max_stake: float = 250.0
    fee_bps: float = 20.0
    slippage_bps: float = 50.0
    flat_stake: float = 25.0
    strategy: str = STRATEGY_COPY
    max_exposure_pct: float = 100.0
    trader_portfolio_value: float = 0.0
    # Fraction of full Kelly applied in SIZING_KELLY mode. Quarter-Kelly by
    # default: the assumed edge is an estimate, and overbetting past the
    # optimum destroys growth asymmetrically.
    kelly_fraction: float = 0.25


@dataclass(frozen=True)
class BacktestResult:
    wallet: str
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    ledger: pd.DataFrame
    open_positions: pd.DataFrame
    equity: pd.DataFrame
    stats: dict[str, Any]
    benchmark_stats: dict[str, Any] = field(default_factory=dict)


def _empty_ledger() -> pd.DataFrame:
    return pd.DataFrame(columns=LEDGER_COLUMNS)


def _empty_positions() -> pd.DataFrame:
    return pd.DataFrame(columns=POSITION_COLUMNS)


def _stake_for(config: BacktestConfig, equity_now: float, source_notional: float, entry_price: float | None = None) -> float:
    if config.sizing_mode == SIZING_PERCENT:
        stake = equity_now * (config.stake_value / 100.0)
    elif config.sizing_mode == SIZING_MIRROR:
        stake = source_notional * (config.stake_value / 100.0)
    elif config.sizing_mode == SIZING_KELLY:
        # stake_value = assumed edge in probability points over the entry price
        # (e.g. 5.0 means "the bought side is worth entry + 5pt"). Sized on the
        # pre-slippage entry price of the side we actually buy (fade-aware).
        if entry_price is None or not (0.0 < entry_price < 1.0):
            stake = 0.0
        else:
            prob = min(0.999, entry_price + max(0.0, config.stake_value) / 100.0)
            fraction = kelly_binary(entry_price, prob) * max(0.0, config.kelly_fraction)
            stake = equity_now * fraction
    elif config.sizing_mode == SIZING_PORTFOLIO:
        # Bet the same share of MY bankroll as the trader bet of THEIR portfolio
        # (stake_value acts as a multiplier: 1.0 = same share, 2.0 = double).
        if config.trader_portfolio_value > 0:
            share = source_notional / config.trader_portfolio_value
            stake = equity_now * share * (config.stake_value or 1.0)
        else:
            stake = 0.0
    else:
        stake = config.stake_value
    return max(0.0, min(stake, config.max_stake))


def replay(
    trades: pd.DataFrame,
    config: BacktestConfig,
    token_values: dict[str, dict[str, Any]] | None = None,
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    """Replay source trades chronologically. Returns (ledger, open positions by asset).

    When ``token_values`` is provided, positions in markets that resolved DURING
    the window are settled at their resolution time inside the replay — the
    payout flows back into cash and frees exposure-cap room, exactly like in
    reality. Without it (legacy behavior), everything settles at the end.
    """

    cash = float(config.bankroll)
    realized_net = 0.0
    fee_rate = max(0.0, config.fee_bps) / 10_000.0
    slip_rate = max(0.0, config.slippage_bps) / 10_000.0
    fade = config.strategy == STRATEGY_FADE
    open_cost = 0.0
    max_open = float(config.bankroll) * max(0.0, min(float(config.max_exposure_pct), 100.0)) / 100.0
    positions: dict[str, dict[str, Any]] = {}
    source_shares: dict[str, float] = {}
    rows: list[dict[str, Any]] = []

    def equity_now() -> float:
        return float(config.bankroll) + realized_net

    def log(time: Any, action: str, status: str, trade: dict[str, Any], **extra: Any) -> None:
        rows.append(
            {
                "time": time,
                "action": action,
                "status": status,
                "title": trade.get("title", ""),
                "outcome": trade.get("outcome", ""),
                "source_notional": float(trade.get("notional", 0.0) or 0.0),
                "stake": extra.get("stake", 0.0),
                "exec_price": extra.get("exec_price", float("nan")),
                "shares": extra.get("shares", 0.0),
                "fee": extra.get("fee", 0.0),
                "realized_pnl": extra.get("realized_pnl", 0.0),
                "equity_after": equity_now(),
                "note": extra.get("note", ""),
                "asset": str(trade.get("asset", "") or ""),
                "market_key": str(trade.get("market_key", "") or ""),
            }
        )

    if trades is None or trades.empty:
        return _empty_ledger(), positions

    pending_resolutions: list[tuple[pd.Timestamp, str]] = []

    def schedule_resolution(position_key: str, opened_at: Any) -> None:
        if not token_values or any(key == position_key for _, key in pending_resolutions):
            return
        position = positions.get(position_key)
        if not position:
            return
        info = token_values.get(str(position.get("lookup_asset", "") or ""), {})
        if not info.get("closed") or info.get("price") is None:
            return
        end_time = info.get("end_time")
        if not isinstance(end_time, pd.Timestamp) or pd.isna(end_time):
            return
        opened_ts = pd.to_datetime(opened_at, utc=True, errors="coerce")
        resolve_time = end_time if pd.isna(opened_ts) or end_time >= opened_ts else opened_ts
        pending_resolutions.append((resolve_time, position_key))
        pending_resolutions.sort(key=lambda item: item[0])

    def settle_due(now_value: Any) -> None:
        nonlocal cash, realized_net, open_cost
        now_ts = pd.to_datetime(now_value, utc=True, errors="coerce")
        if pd.isna(now_ts):
            return
        while pending_resolutions and pending_resolutions[0][0] <= now_ts:
            resolve_time, key = pending_resolutions.pop(0)
            position = positions.pop(key, None)
            if not position or float(position.get("shares", 0.0) or 0.0) <= 0.0:
                continue
            info = token_values.get(str(position.get("lookup_asset", "") or ""), {}) if token_values else {}
            raw_price = info.get("price")
            if raw_price is None:
                positions[key] = position
                continue
            payout_price = (1.0 - float(raw_price)) if position.get("fade") else float(raw_price)
            shares = float(position["shares"])
            cost = float(position["cost_basis"])
            payout = shares * payout_price
            realized = payout - cost
            cash += payout
            open_cost = max(0.0, open_cost - cost)
            realized_net += realized
            rows.append(
                {
                    "time": resolve_time,
                    "action": "RESOLVE",
                    "status": "settled",
                    "title": position.get("title", ""),
                    "outcome": position.get("outcome", ""),
                    "source_notional": 0.0,
                    "stake": cost,
                    "exec_price": payout_price,
                    "shares": shares,
                    "fee": 0.0,
                    "realized_pnl": realized,
                    "equity_after": float(config.bankroll) + realized_net,
                    "note": "market resolved",
                    "asset": str(position.get("lookup_asset", "") or ""),
                    "market_key": str(position.get("market_key", "") or ""),
                }
            )

    frame = trades.sort_values("time", ascending=True)
    for _, trade in frame.iterrows():
        settle_due(trade.get("time"))
        side = str(trade.get("side", "") or "").upper()
        asset = str(trade.get("asset", "") or "")
        price = float(trade.get("price", 0.0) or 0.0)
        size = float(trade.get("size", 0.0) or 0.0)
        record = trade.to_dict()
        if not asset or price <= 0.0 or price >= 1.0 or size <= 0.0:
            log(trade.get("time"), side or "?", "skipped", record, note="bad trade data")
            continue

        position_key = f"fade:{asset}" if fade else asset
        display_outcome = f"FADE {record.get('outcome', '')}".strip() if fade else record.get("outcome", "")
        record["outcome"] = display_outcome
        if side == "BUY":
            source_shares[asset] = source_shares.get(asset, 0.0) + size
            base_price = (1.0 - price) if fade else price
            stake = _stake_for(config, equity_now(), float(trade.get("notional", 0.0) or 0.0), base_price)
            exposure_room = max_open - open_cost
            if stake > exposure_room:
                stake = max(0.0, exposure_room)
                if stake < MIN_STAKE:
                    log(trade.get("time"), "BUY", "skipped", record, note=f"exposure cap reached ({config.max_exposure_pct:.0f}% of bankroll in open copies)")
                    continue
            fee = stake * fee_rate
            if stake + fee > cash:
                stake = max(0.0, cash / (1.0 + fee_rate))
                fee = stake * fee_rate
            if stake < MIN_STAKE:
                log(trade.get("time"), "BUY", "skipped", record, note="stake below minimum / out of cash")
                continue
            exec_price = min(0.999, base_price * (1.0 + slip_rate))
            shares = stake / exec_price
            position = positions.setdefault(
                position_key,
                {
                    "shares": 0.0,
                    "cost_basis": 0.0,
                    "title": record.get("title", ""),
                    "outcome": display_outcome,
                    "market_key": str(record.get("market_key", "") or ""),
                    "lookup_asset": asset,
                    "fade": fade,
                },
            )
            position["shares"] += shares
            position["cost_basis"] += stake
            open_cost += stake
            cash -= stake + fee
            realized_net -= fee
            schedule_resolution(position_key, trade.get("time"))
            log(
                trade.get("time"),
                "BUY",
                "copied",
                record,
                stake=stake,
                exec_price=exec_price,
                shares=shares,
                fee=fee,
                note="took the opposite side" if fade else "",
            )
        elif side == "SELL":
            held = positions.get(position_key)
            src_before = source_shares.get(asset, 0.0)
            source_shares[asset] = max(0.0, src_before - size)
            if not held or held["shares"] <= 0.0:
                log(trade.get("time"), "SELL", "skipped", record, note="no copied position")
                continue
            fraction = 1.0 if src_before <= 0.0 else min(1.0, size / src_before)
            sell_shares = held["shares"] * fraction
            base_price = (1.0 - price) if fade else price
            exec_price = max(0.001, base_price * (1.0 - slip_rate))
            proceeds = sell_shares * exec_price
            fee = proceeds * fee_rate
            cost_released = held["cost_basis"] * (sell_shares / held["shares"])
            realized = proceeds - fee - cost_released
            held["shares"] -= sell_shares
            held["cost_basis"] -= cost_released
            open_cost = max(0.0, open_cost - cost_released)
            cash += proceeds - fee
            realized_net += realized
            if held["shares"] <= 1e-9:
                positions.pop(position_key, None)
            log(
                trade.get("time"),
                "SELL",
                "copied",
                record,
                stake=cost_released,
                exec_price=exec_price,
                shares=sell_shares,
                fee=fee,
                realized_pnl=realized,
                note=f"mirrored {fraction:.0%} of position",
            )
        else:
            log(trade.get("time"), side or "?", "skipped", record, note="unsupported side")

    ledger = pd.DataFrame(rows, columns=LEDGER_COLUMNS)
    return ledger, positions


def settle(
    positions: dict[str, dict[str, Any]],
    token_values: dict[str, dict[str, Any]],
    asof: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Settle open positions: resolved markets realize PnL, open ones mark-to-market.

    Returns (settlement ledger rows, remaining open positions frame).
    """

    rows: list[dict[str, Any]] = []
    open_rows: list[dict[str, Any]] = []
    for asset, position in positions.items():
        shares = float(position.get("shares", 0.0) or 0.0)
        cost = float(position.get("cost_basis", 0.0) or 0.0)
        if shares <= 0.0:
            continue
        lookup_asset = str(position.get("lookup_asset", asset) or asset)
        info = token_values.get(lookup_asset, {})
        raw_price = info.get("price")
        if raw_price is None:
            price = None
        else:
            price = (1.0 - float(raw_price)) if position.get("fade") else float(raw_price)
        closed = bool(info.get("closed"))
        end_time = info.get("end_time")
        base = {
            "title": position.get("title", ""),
            "outcome": position.get("outcome", ""),
            "asset": asset,
            "market_key": position.get("market_key", ""),
            "notional": 0.0,
        }
        if closed and price is not None:
            payout = shares * float(price)
            realized = payout - cost
            event_time = end_time if isinstance(end_time, pd.Timestamp) and pd.notna(end_time) else asof
            if event_time > asof:
                event_time = asof
            rows.append(
                {
                    "time": event_time,
                    "action": "RESOLVE",
                    "status": "settled",
                    "title": base["title"],
                    "outcome": base["outcome"],
                    "source_notional": 0.0,
                    "stake": cost,
                    "exec_price": float(price),
                    "shares": shares,
                    "fee": 0.0,
                    "realized_pnl": realized,
                    "equity_after": float("nan"),
                    "note": "market resolved",
                    "asset": asset,
                    "market_key": base["market_key"],
                }
            )
        else:
            current = float(price) if price is not None else (cost / shares if shares else 0.0)
            value = shares * current
            open_rows.append(
                {
                    "asset": asset,
                    "market_key": base["market_key"],
                    "title": base["title"],
                    "outcome": base["outcome"],
                    "shares": shares,
                    "cost_basis": cost,
                    "avg_price": cost / shares if shares else 0.0,
                    "current_price": current,
                    "value": value,
                    "unrealized_pnl": value - cost,
                    "market_status": "open" if price is not None else "unknown",
                }
            )
    settlement = pd.DataFrame(rows, columns=LEDGER_COLUMNS) if rows else _empty_ledger()
    open_positions = pd.DataFrame(open_rows, columns=POSITION_COLUMNS) if open_rows else _empty_positions()
    return settlement, open_positions


def equity_curve(
    ledger: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    bankroll: float,
    final_unrealized: float = 0.0,
) -> pd.DataFrame:
    """Daily equity series: bankroll + cumulative net realized; MTM lands on the last day."""

    days = pd.date_range(window_start.normalize(), window_end.normalize(), freq="D", tz="UTC")
    if days.empty:
        days = pd.DatetimeIndex([window_end.normalize()], tz="UTC")
    curve = pd.DataFrame({"time": days, "equity": float(bankroll)})
    if ledger is not None and not ledger.empty:
        events = ledger[ledger["status"].isin(["copied", "settled"])].copy()
        if not events.empty:
            events["time"] = pd.to_datetime(events["time"], utc=True, errors="coerce")
            events = events.dropna(subset=["time"])
            events["net"] = events["realized_pnl"].fillna(0.0) - events["fee"].fillna(0.0).where(
                events["action"].eq("BUY"), 0.0
            )
            daily = events.set_index("time")["net"].sort_index().cumsum().resample("D").last().ffill()
            daily.index = daily.index.normalize()
            curve = curve.set_index("time")
            curve["realized"] = daily.reindex(curve.index).ffill().fillna(0.0)
            curve["equity"] = float(bankroll) + curve["realized"]
            curve = curve.drop(columns=["realized"]).reset_index()
    if final_unrealized:
        curve.loc[curve.index[-1], "equity"] += float(final_unrealized)
    peak = curve["equity"].cummax()
    curve["drawdown"] = (curve["equity"] - peak) / peak.where(peak > 0, other=1.0)
    return curve


def compute_stats(ledger: pd.DataFrame, open_positions: pd.DataFrame, curve: pd.DataFrame, bankroll: float) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "bankroll": float(bankroll),
        "copied_trades": 0,
        "skipped_trades": 0,
        "closed_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": None,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "total_pnl": 0.0,
        "roi": 0.0,
        "final_equity": float(bankroll),
        "max_drawdown": 0.0,
        "fees_paid": 0.0,
        "volume_copied": 0.0,
        "profit_factor": None,
        "best_trade": 0.0,
        "worst_trade": 0.0,
        "open_positions": 0,
        "open_value": 0.0,
    }
    if ledger is not None and not ledger.empty:
        copied = ledger[ledger["status"].isin(["copied", "settled"])]
        skipped = ledger[ledger["status"].eq("skipped")]
        stats["copied_trades"] = int((copied["action"].isin(["BUY", "SELL"])).sum())
        stats["skipped_trades"] = int(len(skipped))
        stats["fees_paid"] = float(copied["fee"].fillna(0.0).sum())
        stats["volume_copied"] = float(copied.loc[copied["action"].eq("BUY"), "stake"].fillna(0.0).sum())
        closers = copied[copied["action"].isin(["SELL", "RESOLVE"])]
        pnl = closers["realized_pnl"].fillna(0.0)
        stats["closed_trades"] = int(len(closers))
        stats["wins"] = int((pnl > 0).sum())
        stats["losses"] = int((pnl < 0).sum())
        if stats["closed_trades"]:
            stats["win_rate"] = stats["wins"] / stats["closed_trades"]
        gross_win = float(pnl[pnl > 0].sum())
        gross_loss = float(-pnl[pnl < 0].sum())
        if gross_loss > 0:
            stats["profit_factor"] = gross_win / gross_loss
        elif gross_win > 0:
            stats["profit_factor"] = float("inf")
        stats["best_trade"] = float(pnl.max()) if len(pnl) else 0.0
        stats["worst_trade"] = float(pnl.min()) if len(pnl) else 0.0
        buy_fees = float(copied.loc[copied["action"].eq("BUY"), "fee"].fillna(0.0).sum())
        stats["realized_pnl"] = float(pnl.sum()) - buy_fees
    if open_positions is not None and not open_positions.empty:
        stats["unrealized_pnl"] = float(open_positions["unrealized_pnl"].fillna(0.0).sum())
        stats["open_positions"] = int(len(open_positions))
        stats["open_value"] = float(open_positions["value"].fillna(0.0).sum())
    stats["total_pnl"] = stats["realized_pnl"] + stats["unrealized_pnl"]
    stats["roi"] = stats["total_pnl"] / bankroll if bankroll else 0.0
    stats["final_equity"] = float(bankroll) + stats["total_pnl"]
    if curve is not None and not curve.empty and "drawdown" in curve:
        stats["max_drawdown"] = float(curve["drawdown"].min())
    return stats


def fetch_window_trades(
    wallet: str,
    window_start: pd.Timestamp,
    fetch_activity: Callable[..., pd.DataFrame],
    page_size: int = 500,
    max_rows: int = 3000,
) -> pd.DataFrame:
    """Page the wallet's activity feed back until the window start (TRADE rows only).

    The public data API rejects deep pagination (offset+limit beyond ~3500), so the
    scan is capped; for hyper-active wallets the window covers the most recent
    ``max_rows`` activity rows. Errors on follow-up pages keep the rows already
    fetched instead of failing the whole backtest.
    """

    frames: list[pd.DataFrame] = []
    offset = 0
    truncated = False
    window_covered = False
    while offset < max_rows:
        try:
            page = fetch_activity(wallet, limit=page_size, offset=offset)
        except Exception:
            if frames:
                truncated = True
                break
            raise
        if page is None or page.empty:
            window_covered = True
            break
        frames.append(page)
        oldest = pd.to_datetime(page["time"], utc=True, errors="coerce").min()
        if pd.isna(oldest) or oldest < window_start:
            window_covered = True
            break
        if len(page) < page_size:
            window_covered = True
            break
        offset += page_size
    if frames and not window_covered and not truncated:
        truncated = True
    if not frames:
        return pd.DataFrame(), False
    activity = pd.concat(frames, ignore_index=True)
    activity["time"] = pd.to_datetime(activity["time"], utc=True, errors="coerce")
    mask = activity["time"].notna() & (activity["time"] >= window_start)
    if "type" in activity.columns:
        mask &= activity["type"].astype(str).str.upper().eq("TRADE")
    trades = activity[mask].copy()
    if "transactionHash" in trades.columns:
        trades = trades.drop_duplicates(subset=["transactionHash", "asset", "side", "size"], keep="first")
    return trades.sort_values("time", ascending=True).reset_index(drop=True), truncated


def run_backtest(
    config: BacktestConfig,
    *,
    fetch_activity: Callable[..., pd.DataFrame] | None = None,
    fetch_markets_by_ids: Callable[[list[str]], list[dict[str, Any]]] | None = None,
    token_values: dict[str, dict[str, Any]] | None = None,
    now: pd.Timestamp | None = None,
) -> BacktestResult:
    """Full backtest: fetch window trades, replay with sizing + flat benchmark, settle, score."""

    if fetch_activity is None or fetch_markets_by_ids is None:
        from src import prediction_markets as md

        fetch_activity = fetch_activity or md.get_polymarket_activity
        fetch_markets_by_ids = fetch_markets_by_ids or md.get_polymarket_markets_by_condition_ids
        token_value_builder = md.polymarket_token_value_map
    else:
        from src import prediction_markets as md

        token_value_builder = md.polymarket_token_value_map

    window_end = now if now is not None else pd.Timestamp.now(tz="UTC")
    window_start = window_end - pd.Timedelta(days=int(config.days))
    trades, window_truncated = fetch_window_trades(config.wallet, window_start, fetch_activity)

    if token_values is None:
        trade_keys = (
            sorted({str(key) for key in trades.get("market_key", pd.Series(dtype=str)).dropna().astype(str) if key})
            if trades is not None and not trades.empty
            else []
        )
        markets = fetch_markets_by_ids(trade_keys) if trade_keys else []
        token_values = token_value_builder(markets)

    ledger, positions = replay(trades, config, token_values)
    flat_config = BacktestConfig(
        wallet=config.wallet,
        days=config.days,
        bankroll=config.bankroll,
        sizing_mode=SIZING_FIXED,
        stake_value=config.flat_stake,
        max_stake=config.flat_stake,
        fee_bps=config.fee_bps,
        slippage_bps=config.slippage_bps,
        flat_stake=config.flat_stake,
        strategy=config.strategy,
    )
    flat_ledger, flat_positions = replay(trades, flat_config, token_values)

    settlement, open_positions = settle(positions, token_values, asof=window_end)
    flat_settlement, flat_open = settle(flat_positions, token_values, asof=window_end)

    full_ledger = pd.concat([ledger, settlement], ignore_index=True) if not settlement.empty else ledger
    flat_full = pd.concat([flat_ledger, flat_settlement], ignore_index=True) if not flat_settlement.empty else flat_ledger

    unrealized = float(open_positions["unrealized_pnl"].sum()) if not open_positions.empty else 0.0
    flat_unrealized = float(flat_open["unrealized_pnl"].sum()) if not flat_open.empty else 0.0
    curve = equity_curve(full_ledger, window_start, window_end, config.bankroll, unrealized)
    flat_curve = equity_curve(flat_full, window_start, window_end, config.bankroll, flat_unrealized)
    curve["benchmark"] = flat_curve["equity"].to_numpy()

    stats = compute_stats(full_ledger, open_positions, curve, config.bankroll)
    flat_stats = compute_stats(flat_full, flat_open, flat_curve, config.bankroll)
    stats["window_truncated"] = bool(window_truncated)
    effective_start = trades["time"].min() if trades is not None and not trades.empty else window_start
    stats["effective_start"] = effective_start if pd.notna(effective_start) else window_start

    if not full_ledger.empty:
        full_ledger = full_ledger.sort_values("time", ascending=False).reset_index(drop=True)
    return BacktestResult(
        wallet=config.wallet,
        window_start=window_start,
        window_end=window_end,
        ledger=full_ledger,
        open_positions=open_positions,
        equity=curve,
        stats=stats,
        benchmark_stats=flat_stats,
    )


def default_strategy_variants(config: BacktestConfig) -> list[tuple[str, str, float]]:
    """(label, sizing_mode, stake_value) grid for the what-would-have-been-best simulation."""

    variants: list[tuple[str, str, float]] = [
        ("Fixed $10", SIZING_FIXED, 10.0),
        ("Fixed $25", SIZING_FIXED, 25.0),
        ("Fixed $50", SIZING_FIXED, 50.0),
        ("1% of bankroll", SIZING_PERCENT, 1.0),
        ("2% of bankroll", SIZING_PERCENT, 2.0),
        ("5% of bankroll", SIZING_PERCENT, 5.0),
        ("Kelly 1/4 (+5pt edge)", SIZING_KELLY, 5.0),
        ("Kelly 1/4 (+10pt edge)", SIZING_KELLY, 10.0),
    ]
    if config.trader_portfolio_value > 0:
        variants.append(("Match trader share ×1", SIZING_PORTFOLIO, 1.0))
        variants.append(("Match trader share ×2", SIZING_PORTFOLIO, 2.0))
    return variants


def strategy_comparison(
    config: BacktestConfig,
    variants: list[tuple[str, str, float]] | None = None,
    *,
    fetch_activity: Callable[..., pd.DataFrame] | None = None,
    fetch_markets_by_ids: Callable[[list[str]], list[dict[str, Any]]] | None = None,
    token_values: dict[str, dict[str, Any]] | None = None,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Replay the same window once per sizing variant and rank the outcomes.

    Fetches the wallet's trades and market resolutions a single time, then runs
    the full replay/settle/score pipeline for every variant. Fee, slippage,
    exposure cap, strategy (copy/fade) and trader portfolio value come from
    ``config``; only the sizing changes per row. Sorted by final equity.
    """

    from src import prediction_markets as md

    fetch_activity = fetch_activity or md.get_polymarket_activity
    fetch_markets_by_ids = fetch_markets_by_ids or md.get_polymarket_markets_by_condition_ids
    window_end = now if now is not None else pd.Timestamp.now(tz="UTC")
    window_start = window_end - pd.Timedelta(days=int(config.days))
    trades, _truncated = fetch_window_trades(config.wallet, window_start, fetch_activity)
    if variants is None:
        variants = default_strategy_variants(config)
    rows: list[dict[str, Any]] = []
    resolved_token_values = token_values
    if resolved_token_values is None:
        trade_keys = (
            sorted({str(key) for key in trades.get("market_key", pd.Series(dtype=str)).dropna().astype(str) if key})
            if trades is not None and not trades.empty
            else []
        )
        markets = fetch_markets_by_ids(trade_keys) if trade_keys else []
        resolved_token_values = md.polymarket_token_value_map(markets)
    for label, sizing_mode, stake_value in variants:
        variant_config = BacktestConfig(
            wallet=config.wallet,
            days=config.days,
            bankroll=config.bankroll,
            sizing_mode=sizing_mode,
            stake_value=stake_value,
            max_stake=config.max_stake,
            fee_bps=config.fee_bps,
            slippage_bps=config.slippage_bps,
            flat_stake=config.flat_stake,
            strategy=config.strategy,
            max_exposure_pct=config.max_exposure_pct,
            trader_portfolio_value=config.trader_portfolio_value,
        )
        ledger, positions = replay(trades, variant_config, resolved_token_values)
        settlement, open_positions = settle(positions, resolved_token_values, asof=window_end)
        full_ledger = pd.concat([ledger, settlement], ignore_index=True) if not settlement.empty else ledger
        unrealized = float(open_positions["unrealized_pnl"].sum()) if not open_positions.empty else 0.0
        curve = equity_curve(full_ledger, window_start, window_end, config.bankroll, unrealized)
        stats = compute_stats(full_ledger, open_positions, curve, config.bankroll)
        rows.append(
            {
                "strategy": label,
                "sizing_mode": sizing_mode,
                "stake_value": stake_value,
                "final_equity": stats["final_equity"],
                "roi": stats["roi"],
                "total_pnl": stats["total_pnl"],
                "max_drawdown": stats["max_drawdown"],
                "win_rate": stats["win_rate"],
                "copied_trades": stats["copied_trades"],
                "skipped_trades": stats["skipped_trades"],
                "volume_copied": stats["volume_copied"],
            }
        )
    comparison = pd.DataFrame(rows)
    if comparison.empty:
        return comparison
    return comparison.sort_values("final_equity", ascending=False).reset_index(drop=True)
