"""Copy-trade backtest engine: replay a wallet's Polymarket trades with fees/slippage.

Streamlit-free so it can be unit-tested and reused by scripts. Data fetching is
injectable; by default it uses ``src.prediction_markets``.

Model:
- Replays the source wallet's BUY/SELL trades chronologically inside the window.
- BUYs are copied with the configured stake sizing (fee + slippage priced in).
  Fixed, percent and Kelly stakes are per POSITION: the first entry gets the
  stake, later adds by the wallet only top the copy back up to the stake
  (after a partial exit) and are otherwise logged as "filtered". Mirror and
  portfolio-share sizing scale with the source notional and stay per trade.
- SELLs are mirrored proportionally to the fraction the source sold.
- After the replay, remaining open positions are settled against market data:
  resolved markets pay out at the final token price (no fee on redemption),
  unresolved positions are marked-to-market at the current token price.
- The equity curve marks open positions to market along the way when a
  price history is available for their tokens (``fetch_price_history``):
  equity(t) = bankroll + realized(t) + sum over open copies of
  shares x price(t) - cost. Tokens without history stay at cost until they
  close; the final point always carries the settle-time mark-to-market.
- A flat-stake benchmark replays the same signals with a constant stake.
- Kelly sizing (``SIZING_KELLY``) reads ``stake_value`` as the assumed edge in
  probability points over the copied entry price and stakes
  ``kelly_fraction`` × full Kelly of current equity (quarter-Kelly by default):
  the estimate is uncertain and platform/resolution risk lives outside the
  model, and past f* expected log growth falls off a cliff.

Where hindsight enters (and where it does not):

- The replay itself is forward-only. Resolutions settle at their own
  ``end_time`` and never before, so a payout cannot fund a copy that happened
  earlier.
- ``auto_fit`` is the exception: it reads the whole window to pick a follow
  threshold or a stake. That is hindsight by construction and is marked as
  such in ``stats["auto_fit"]["hindsight"]``.
- ``strategy_comparison`` ranks every sizing variant on the same window it was
  chosen on. The top row is the maximum of N in-sample runs, not an
  out-of-sample result.
"""

from __future__ import annotations

import inspect
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import Any, Callable

import pandas as pd

from app.quant import kelly_binary
from app.venue_fees import polymarket_category_rate

SIZING_FIXED = "fixed"
SIZING_PERCENT = "percent"
SIZING_MIRROR = "mirror"
SIZING_PORTFOLIO = "portfolio_share"
SIZING_KELLY = "kelly"
SIZING_MODES = (SIZING_FIXED, SIZING_PERCENT, SIZING_MIRROR, SIZING_PORTFOLIO, SIZING_KELLY)
#: Modi, deren Einsatz je POSITION gilt, nicht je Quell-Trade. Eine Wallet
#: baut eine Position oft aus Dutzenden Kaeufen auf; wer jeden davon mit dem
#: vollen Einsatz spiegelt, zahlt fuer eine Position das Vielfache dessen,
#: was "Einsatz je Copy" verspricht, und die Kasse ist nach wenigen
#: Positionen leer, obwohl die Wallet nur eine Handvoll offen hat. Nachkaeufe
#: fuellen deshalb nur bis zum Einsatz auf (nach einem Teilausstieg), sonst
#: gelten sie als "filtered". Mirror und Portfolio-Anteil skalieren mit dem
#: Quell-Notional und bleiben je Trade.
PER_POSITION_SIZING = (SIZING_FIXED, SIZING_PERCENT, SIZING_KELLY)

STRATEGY_COPY = "copy"
STRATEGY_FADE = "fade"
STRATEGIES = (STRATEGY_COPY, STRATEGY_FADE)

#: Wie die Gebuehr berechnet wird. "curve" nimmt das Venue-Modell aus
#: app/venue_fees.py, "flat" den pauschalen bps-Satz aus der Konfiguration.
FEE_MODEL_CURVE = "curve"
FEE_MODEL_FLAT = "flat"
FEE_MODELS = (FEE_MODEL_CURVE, FEE_MODEL_FLAT)

MIN_STAKE = 1.0

#: Bewertungskurve: hoechstens so viele Token je Lauf mit Preisverlauf
#: nachladen (offene Positionen zuerst, dann nach Einsatz). Eine
#: Market-Maker-Wallet beruehrt tausende Token in Stunden; die Positionen
#: darueber hinaus bleiben bis zum Schluss zum Einstand bewertet, und das
#: steht im Ergebnis.
MTM_TOKEN_CAP = 120
MTM_WORKERS = 8

#: Auto-Fit waehlt Schwelle und Einsatz aus dem GANZEN Fenster, also aus
#: Zahlen, die am Tag null noch nicht feststanden. Der Satz haengt an jedem
#: Lauf, in dem er angewendet wurde. Englisch, weil die Oberflaechen es sind.
AUTO_FIT_HINDSIGHT_NOTE = (
    "Auto-fit picked this from the finished window: the wallet's peak concurrency and the "
    "size distribution of its entries are only known at the end. A copier could not have set "
    "it on day one, so read this as the setting that fit this window, not as an achievable result."
)

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
    # Nur wirksam bei fee_model == FEE_MODEL_FLAT. Der Wert war die
    # Voreinstellung fuer alle Laeufe und lag bei der Haelfte des Buches
    # weit unter der wirklichen Gebuehr.
    fee_bps: float = 20.0
    fee_model: str = FEE_MODEL_CURVE
    #: Polymarket staffelt den Taker-Satz nach Kategorie. Die Wallet-Historie
    #: fuehrt keine mit, also gilt ohne Angabe der allgemeine Satz.
    fee_category: str | None = None
    slippage_bps: float = 50.0
    flat_stake: float = 25.0
    strategy: str = STRATEGY_COPY
    max_exposure_pct: float = 100.0
    trader_portfolio_value: float = 0.0
    # Fraction of full Kelly applied in SIZING_KELLY mode. Quarter-Kelly by
    # default: the assumed edge is an estimate, and overbetting past the
    # optimum destroys growth asymmetrically.
    kelly_fraction: float = 0.25
    #: Einsatz automatisch an das Tempo der Quell-Wallet anpassen: der
    #: Einsatz je Copy wird so gewaehlt, dass die Hoechstzahl gleichzeitig
    #: offener Quell-Positionen in Bankroll und Exposure-Deckel passt.
    #: Wirkt nur bei SIZING_FIXED und SIZING_PERCENT; die uebrigen Modi
    #: dimensionieren sich selbst. Was angewendet wurde, steht in
    #: ``stats["auto_fit"]`` — nichts wird still veraendert.
    auto_fit: bool = False
    #: Nur Quell-Trades ab diesem Notional kopieren. Kleinere BUYs werden
    #: als "filtered" markiert (bewusste Auswahl, kein Fehlschlag); der
    #: Auto-Fit setzt die Schwelle selbst, wenn der ganze Flow nicht in
    #: die Bankroll passt. 0 = alles kopieren.
    min_follow_notional: float = 0.0


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


@dataclass
class WindowData:
    """Alles, was ein Fenster an Netz kostet, einmal geladen.

    Der teure Teil eines Backtests ist nicht das Replay, sondern der Weg
    dahin: bis zu 30.000 Activity-Zeilen in Scheiben plus die Aufloesungen
    aller beruehrten Token. ``run_backtest`` und ``strategy_comparison``
    nehmen ein fertiges ``WindowData`` entgegen, damit ein Server dieselbe
    Wallet im selben Fenster fuer jede Einstellung nur einmal laedt — vorher
    lud jeder Klick auf RUN alles neu und lief bei aktiven Wallets in die
    Minute.
    """

    wallet: str
    days: int
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    trades: pd.DataFrame
    window_truncated: bool
    token_values: dict[str, dict[str, Any]]
    loaded_at: pd.Timestamp
    #: Preisverlauf je Token, gefuellt von ``run_backtest`` beim ersten
    #: Lauf, der ihn braucht; jeder weitere Lauf im selben Fenster liest
    #: ihn hier statt neu zu laden.
    price_history: dict[str, pd.DataFrame] = field(default_factory=dict)


def load_window_data(
    config: BacktestConfig,
    *,
    fetch_activity: Callable[..., pd.DataFrame] | None = None,
    fetch_markets_by_ids: Callable[[list[str]], list[dict[str, Any]]] | None = None,
    fetch_markets_by_event_slugs: Callable[[list[str]], list[dict[str, Any]]] | None = None,
    token_values: dict[str, dict[str, Any]] | None = None,
    now: pd.Timestamp | None = None,
) -> WindowData:
    """Trades und Aufloesungen eines Fensters laden (siehe ``WindowData``)."""

    from src import prediction_markets as md

    fetch_activity = fetch_activity or md.get_polymarket_activity
    fetch_markets_by_ids = fetch_markets_by_ids or md.get_polymarket_markets_by_condition_ids
    fetch_markets_by_event_slugs = fetch_markets_by_event_slugs or md.get_polymarket_markets_by_event_slugs
    window_end = now if now is not None else pd.Timestamp.now(tz="UTC")
    window_start = window_end - pd.Timedelta(days=int(config.days))
    trades, window_truncated = fetch_window_trades(config.wallet, window_start, fetch_activity)
    if token_values is None:
        token_values = _resolve_token_values(
            trades, fetch_markets_by_ids, fetch_markets_by_event_slugs, md.polymarket_token_value_map
        )
    return WindowData(
        wallet=config.wallet,
        days=int(config.days),
        window_start=window_start,
        window_end=window_end,
        trades=trades,
        window_truncated=bool(window_truncated),
        token_values=token_values,
        loaded_at=pd.Timestamp.now(tz="UTC"),
    )


def _empty_ledger() -> pd.DataFrame:
    return pd.DataFrame(columns=LEDGER_COLUMNS)


def _empty_positions() -> pd.DataFrame:
    return pd.DataFrame(columns=POSITION_COLUMNS)


def fee_rate_for(config: BacktestConfig) -> Callable[[float], float]:
    """Die Gebuehr als Anteil am Einsatz, als Funktion des Ausfuehrungspreises.

    Polymarket rechnet ``fee = shares * rate * p * (1 - p)``. Ein Kauf ueber
    ``stake`` bekommt ``stake / p`` Anteile, also ist die Gebuehr
    ``stake * rate * (1 - p)``; beim Verkauf gilt dieselbe Form, weil der
    Erloes ``shares * p`` ist. Die Gebuehr haengt damit nur am Preis, und
    zwar stark: bei einem allgemeinen Satz von 5 Prozent kostet ein Taker
    bei 0.50 rund 250 Basispunkte und bei 0.90 rund 50. Die pauschalen
    20 bps, die hier als Voreinstellung standen, sind in der Mitte des
    Buches mehr als zehnmal zu billig, und eine zu billige Gebuehr
    schmeichelt jedem Ergebnis.
    """
    if str(config.fee_model or "").strip().lower() == FEE_MODEL_FLAT:
        pauschal = max(0.0, float(config.fee_bps)) / 10_000.0
        return lambda price: pauschal
    rate = polymarket_category_rate(config.fee_category)
    return lambda price: rate * (1.0 - max(0.0, min(1.0, float(price))))


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
    asof: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    """Replay source trades chronologically. Returns (ledger, open positions by asset).

    When ``token_values`` is provided, positions in markets that resolved DURING
    the window are settled at their resolution time inside the replay — the
    payout flows back into cash and frees exposure-cap room, exactly like in
    reality. Without it (legacy behavior), everything settles at the end.

    ``asof`` is the end of the window. Resolutions run at their own due time,
    not only when the wallet happens to trade again: without it, a resolution
    that falls after the last trade of the window stayed pending and was
    booked afterwards by ``settle``, which writes no running equity into the
    row. Nothing due after ``asof`` is settled, so the window edge stays the
    window edge.
    """

    cash = float(config.bankroll)
    realized_net = 0.0
    fee_rate = fee_rate_for(config)
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
            # Unter der Folge-Schwelle wird nicht kopiert — bewusste
            # Auswahl ("filtered"), kein Fehlschlag. Die Quellbestaende
            # oben zaehlen weiter, damit spaetere SELLs richtig spiegeln.
            if config.min_follow_notional > 0.0 and float(trade.get("notional", 0.0) or 0.0) < config.min_follow_notional:
                log(trade.get("time"), "BUY", "filtered", record, note=f"below the follow threshold (${config.min_follow_notional:,.0f})")
                continue
            base_price = (1.0 - price) if fade else price
            stake = _stake_for(config, equity_now(), float(trade.get("notional", 0.0) or 0.0), base_price)
            held = positions.get(position_key)
            if held is not None and float(held.get("shares", 0.0) or 0.0) > 0.0 and config.sizing_mode in PER_POSITION_SIZING:
                # Die Wallet kauft nach. Der Einsatz gilt je Position: es
                # wird hoechstens bis zum Einsatz aufgefuellt (etwa nach
                # einem Teilausstieg), nie ein zweiter voller Einsatz
                # gelegt. Was darueber liegt, ist bewusst nicht gefolgt.
                room = stake - float(held.get("cost_basis", 0.0) or 0.0)
                if room < MIN_STAKE:
                    log(
                        trade.get("time"),
                        "BUY",
                        "filtered",
                        record,
                        note=f"already following this position (${float(held.get('cost_basis', 0.0) or 0.0):,.2f} in)",
                    )
                    continue
                stake = room
            exposure_room = max_open - open_cost
            if stake > exposure_room:
                stake = max(0.0, exposure_room)
                if stake < MIN_STAKE:
                    log(trade.get("time"), "BUY", "skipped", record, note=f"exposure cap reached ({config.max_exposure_pct:.0f}% of bankroll in open copies)")
                    continue
            # Der Ausfuehrungspreis steht vor der Gebuehr fest, weil die
            # Gebuehr an ihm haengt und nicht am Einsatz allein.
            exec_price = min(0.999, base_price * (1.0 + slip_rate))
            satz = fee_rate(exec_price)
            fee = stake * satz
            if stake + fee > cash:
                stake = max(0.0, cash / (1.0 + satz))
                fee = stake * satz
            if stake < MIN_STAKE:
                log(trade.get("time"), "BUY", "skipped", record, note="stake below minimum / out of cash")
                continue
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
                    # Wann diese Position aufgemacht wurde. ``settle`` braucht
                    # das, damit eine Auszahlung nicht vor ihrem eigenen Kauf
                    # in der Kurve landet (Maerkte melden ein ``end_time``,
                    # das vor dem Einstieg liegen kann).
                    "opened_at": pd.to_datetime(trade.get("time"), utc=True, errors="coerce"),
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
                # Kein Fehlschlag: die Position wurde nie gefolgt (unter der
                # Schwelle, vor dem Fenster eroeffnet oder beim Kauf am
                # Limit) — der Verkauf betrifft uns schlicht nicht.
                log(trade.get("time"), "SELL", "filtered", record, note="position not followed")
                continue
            fraction = 1.0 if src_before <= 0.0 else min(1.0, size / src_before)
            sell_shares = held["shares"] * fraction
            base_price = (1.0 - price) if fade else price
            exec_price = max(0.001, base_price * (1.0 - slip_rate))
            proceeds = sell_shares * exec_price
            fee = proceeds * fee_rate(exec_price)
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

    # Der letzte Trade ist kein Termin. Was danach und noch innerhalb des
    # Fensters faellig wird, wird hier abgerechnet: zur eigenen
    # Faelligkeit, nicht zum Fensterende und nicht erst, wenn die Wallet
    # zufaellig wieder handelt. Alles nach ``asof`` bleibt offen.
    # Die Reihenfolge bleibt dabei chronologisch: was hier noch offen ist,
    # war beim letzten Trade noch nicht faellig.
    if asof is not None:
        settle_due(asof)

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
            # Kein Vorgriff: der gemeldete ``end_time`` eines Marktes kann
            # vor dem Kauf liegen, und dann stand die Auszahlung in der
            # Kurve, bevor die Position ueberhaupt existierte. ``replay``
            # klammert dasselbe beim Einplanen (schedule_resolution); ohne
            # diese Zeile galt es nur auf dem einen der beiden Wege.
            opened_at = position.get("opened_at")
            if isinstance(opened_at, pd.Timestamp) and pd.notna(opened_at) and event_time < opened_at:
                event_time = opened_at
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
                    # Das Token, nicht der Positionsschluessel. Beim Fade
                    # heisst der Schluessel "fade:<token>", die BUY- und
                    # SELL-Zeilen desselben Durchgangs tragen aber das
                    # Token. ``position_rounds`` haette den Ausstieg sonst
                    # nie seinem Einstieg zuordnen koennen.
                    "asset": lookup_asset,
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
    price_history: dict[str, pd.DataFrame] | None = None,
    fade: bool = False,
) -> pd.DataFrame:
    """Equity series: bankroll + cumulative net realized + open copies marked to market.

    ``price_history`` (Token -> Frame(time, price)) bewertet die offenen
    Kopien an jeder Stuetzstelle zum letzten bekannten Preis. Ohne Verlauf
    bleibt eine Position bis zum Schluss zum Einstand stehen; das war vorher
    die einzige Fassung, und bei einer Wallet, die nur haelt, war die Kurve
    dreissig Tage lang eine Gerade mit einem Sprung am Ende. Die letzte
    Stuetzstelle traegt immer ``final_unrealized`` aus der Abrechnung, damit
    Kurve und Kennzahlen dieselbe Zahl nennen.

    Die Aufloesung folgt der Spanne: bis sieben Tage stundenweise, darueber
    taeglich. Vorher war die Kurve immer taeglich ueber das ANGEFRAGTE
    Fenster — deckten die Daten nur zwei Tage ab, zeigte sie 28 erfundene
    flache Tage und dann eine Stufe. Der Aufrufer uebergibt deshalb die
    tatsaechlich abgedeckte Spanne (run_backtest: ab effective_start, wenn
    das Fenster abgeschnitten ist).
    """

    span = window_end - window_start
    freq = "h" if span <= pd.Timedelta(days=7) else "D"
    anchor = (lambda ts: ts.floor("h")) if freq == "h" else (lambda ts: ts.normalize())
    points = pd.date_range(anchor(window_start), anchor(window_end), freq=freq, tz="UTC")
    if points.empty:
        points = pd.DatetimeIndex([anchor(window_end)], tz="UTC")
    curve = pd.DataFrame({"time": points, "equity": float(bankroll)})
    if ledger is not None and not ledger.empty:
        events = ledger[ledger["status"].isin(["copied", "settled"])].copy()
        if not events.empty:
            events["time"] = pd.to_datetime(events["time"], utc=True, errors="coerce")
            events = events.dropna(subset=["time"])
            events["net"] = events["realized_pnl"].fillna(0.0) - events["fee"].fillna(0.0).where(
                events["action"].eq("BUY"), 0.0
            )
            # resample-Bins liegen auf denselben Grenzen wie date_range oben
            # (Mitternacht bei "D", volle Stunde bei "h") — reindex passt.
            verlauf = events.set_index("time")["net"].sort_index().cumsum().resample(freq).last().ffill()
            curve = curve.set_index("time")
            curve["realized"] = verlauf.reindex(curve.index).ffill().fillna(0.0)
            curve["equity"] = float(bankroll) + curve["realized"]
            curve = curve.drop(columns=["realized"]).reset_index()
    if price_history and ledger is not None and not ledger.empty:
        unterwegs = _unrealized_path(ledger, pd.DatetimeIndex(curve["time"]), price_history, fade)
        # Die letzte Stuetzstelle gehoert der Abrechnung (final_unrealized).
        unterwegs.iloc[-1] = 0.0
        curve["equity"] = curve["equity"] + unterwegs.to_numpy()
    if final_unrealized:
        curve.loc[curve.index[-1], "equity"] += float(final_unrealized)
    peak = curve["equity"].cummax()
    curve["drawdown"] = (curve["equity"] - peak) / peak.where(peak > 0, other=1.0)
    return curve


def _unrealized_path(
    ledger: pd.DataFrame,
    index: pd.DatetimeIndex,
    price_history: dict[str, pd.DataFrame],
    fade: bool = False,
) -> pd.Series:
    """Unrealisiertes Ergebnis der offenen Kopien je Stuetzstelle.

    Bestand und Einstand je Token laufen aus dem Ledger (BUY hebt, SELL und
    RESOLVE senken), der Preis aus dem Verlauf (letzter Wert vor der
    Stuetzstelle). Vor dem ersten Verlaufspunkt und fuer Token ohne
    Verlauf zaehlt die Position zum Einstand, also mit null.
    """

    total = pd.Series(0.0, index=index)
    events = ledger[ledger["status"].isin(["copied", "settled"])].copy()
    if events.empty:
        return total
    events["time"] = pd.to_datetime(events["time"], utc=True, errors="coerce")
    events = events.dropna(subset=["time"])
    sign = events["action"].map({"BUY": 1.0, "SELL": -1.0, "RESOLVE": -1.0}).fillna(0.0)
    events["d_shares"] = events["shares"].fillna(0.0).astype(float) * sign
    events["d_cost"] = events["stake"].fillna(0.0).astype(float) * sign
    events["asset"] = events["asset"].astype(str)
    for asset, history in price_history.items():
        if history is None or history.empty:
            continue
        rows = events[events["asset"] == str(asset)]
        if rows.empty:
            continue
        shares = rows.groupby("time")["d_shares"].sum().sort_index().cumsum()
        cost = rows.groupby("time")["d_cost"].sum().sort_index().cumsum()
        shares_t = shares.reindex(index, method="ffill").fillna(0.0)
        cost_t = cost.reindex(index, method="ffill").fillna(0.0)
        px = pd.Series(
            pd.to_numeric(history["price"], errors="coerce").to_numpy(),
            index=pd.to_datetime(history["time"], utc=True, errors="coerce"),
        ).dropna()
        px = px[~px.index.isna()]
        px = px[~px.index.duplicated(keep="last")].sort_index()
        if px.empty:
            continue
        px_t = px.reindex(index, method="ffill")
        if fade:
            px_t = 1.0 - px_t
        held = (shares_t > 1e-9) & px_t.notna()
        unreal = (shares_t * px_t - cost_t).where(held, 0.0)
        total = total + unreal.fillna(0.0).to_numpy()
    return total


def _empty_history() -> pd.DataFrame:
    return pd.DataFrame(columns=["time", "price"])


def mark_to_market_history(
    ledger: pd.DataFrame,
    open_positions: pd.DataFrame | None,
    fetch_price_history: Callable[[str, str], pd.DataFrame],
    cache: dict[str, pd.DataFrame],
    interval: str,
    max_tokens: int = MTM_TOKEN_CAP,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Preisverlauf fuer die kopierten Token laden (oder aus ``cache`` lesen).

    Reihenfolge: am Fensterende noch offene Positionen zuerst (sie machen
    die Gerade), dann nach Einsatz. Ueber ``max_tokens`` hinaus wird nichts
    geladen; ``info`` sagt, wie viele Positionen bewertet sind und ob der
    Deckel griff. Ein fehlgeschlagener Abruf liefert einen leeren Verlauf
    und wird nicht wiederholt.
    """

    info: dict[str, Any] = {"positions_marked": 0, "positions_total": 0, "capped": False, "interval": interval}
    if ledger is None or ledger.empty:
        return {}, info
    buys = ledger[ledger["status"].eq("copied") & ledger["action"].eq("BUY")]
    if buys.empty:
        return {}, info
    cost_by_asset = buys.groupby(buys["asset"].astype(str))["stake"].sum()
    offen: set[str] = set()
    if open_positions is not None and not open_positions.empty and "asset" in open_positions:
        offen = {str(a).removeprefix("fade:") for a in open_positions["asset"]}
    ranked = [a for a in cost_by_asset.index if a]
    ranked.sort(key=lambda a: (a not in offen, -float(cost_by_asset[a])))
    info["positions_total"] = len(ranked)
    info["capped"] = len(ranked) > max_tokens
    chosen = ranked[:max_tokens]
    missing = [a for a in chosen if a not in cache]

    def laden(asset: str) -> pd.DataFrame:
        try:
            frame_ = fetch_price_history(asset, interval)
        except Exception:
            return _empty_history()
        if frame_ is None or frame_.empty or "time" not in frame_ or "price" not in frame_:
            return _empty_history()
        return frame_[["time", "price"]].copy()

    if missing:
        with ThreadPoolExecutor(max_workers=MTM_WORKERS) as pool:
            for asset, frame_ in zip(missing, pool.map(laden, missing)):
                cache[asset] = frame_
    history = {a: cache[a] for a in chosen if a in cache and cache[a] is not None and not cache[a].empty}
    info["positions_marked"] = len(history)
    return history, info


#: Restanteile unter dieser Schwelle gelten als zu. ``replay`` raeumt eine
#: Position bei <= 1e-9 aus dem Buch; hier gilt dieselbe Grenze.
SHARE_EPS = 1e-9

#: Ein Ergebnis unter dieser Schwelle ist flach. Nicht Null selbst, damit
#: eine Rundung auf dem letzten Bit nicht ueber Sieg oder Niederlage
#: entscheidet.
FLAT_EPS = 1e-9

ROUND_COLUMNS = [
    "asset",
    "market_key",
    "title",
    "outcome",
    "opened_at",
    "closed_at",
    "shares_bought",
    "shares_closed",
    "entries",
    "exits",
    "cost",
    "realized_pnl",
    "closed",
    "result",
]

POSITION_RESULTS = ("win", "loss", "flat")


def position_rounds(ledger: pd.DataFrame) -> pd.DataFrame:
    """Eine Zeile je Position statt je Ausstiegsereignis.

    Ein Durchgang beginnt mit dem ersten BUY auf ein Token, an dem nichts
    mehr offen ist, und endet, sobald seine Anteile wieder bei null sind
    (SELL bis auf den Rest, oder RESOLVE). Wird dasselbe Token spaeter erneut
    gekauft, ist das ein zweiter Durchgang und nicht die Fortsetzung des
    ersten.

    Warum das hier steht: ``closed_trades`` war die Zahl der SELL- und
    RESOLVE-Zeilen. Eine Position, die in drei Tranchen verkauft wurde,
    zaehlte dreifach, in Zaehler UND Nenner der Trefferquote. Eine Wallet,
    die ihre Gewinner stueckweise abbaut und ihre Verlierer in einem Stueck
    fallen laesst, bekam davon eine Quote geschenkt, die niemand geworfen
    hat. ``realized_pnl`` bleibt davon unberuehrt: Geld ist Geld, auch aus
    dem Teilausstieg einer Position, die noch laeuft.
    """

    if ledger is None or ledger.empty:
        return pd.DataFrame(columns=ROUND_COLUMNS)
    frame = ledger[ledger["status"].isin(["copied", "settled"])].copy()
    frame = frame[frame["action"].isin(["BUY", "SELL", "RESOLVE"])]
    if frame.empty:
        return pd.DataFrame(columns=ROUND_COLUMNS)
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    frame = frame.sort_values("time", kind="stable")

    offen: dict[str, dict[str, Any]] = {}
    runden: list[dict[str, Any]] = []

    def abschliessen(key: str) -> None:
        runde = offen.pop(key, None)
        if runde is None:
            return
        runde["closed"] = True
        pnl = float(runde["realized_pnl"])
        runde["result"] = "flat" if abs(pnl) <= FLAT_EPS else ("win" if pnl > 0.0 else "loss")
        runden.append(runde)

    for _, row in frame.iterrows():
        key = str(row.get("asset", "") or "")
        shares = float(row.get("shares", 0.0) or 0.0)
        action = str(row.get("action", ""))
        if action == "BUY":
            if shares <= 0.0:
                continue
            runde = offen.get(key)
            if runde is None:
                runde = {
                    "asset": key,
                    "market_key": str(row.get("market_key", "") or ""),
                    "title": str(row.get("title", "") or ""),
                    "outcome": str(row.get("outcome", "") or ""),
                    "opened_at": row.get("time"),
                    "closed_at": pd.NaT,
                    "shares_bought": 0.0,
                    "shares_closed": 0.0,
                    "entries": 0,
                    "exits": 0,
                    "cost": 0.0,
                    "realized_pnl": 0.0,
                    "closed": False,
                    "result": "",
                }
                offen[key] = runde
            runde["shares_bought"] += shares
            runde["entries"] += 1
            runde["cost"] += float(row.get("stake", 0.0) or 0.0)
            continue
        runde = offen.get(key)
        if runde is None:
            # Ausstieg ohne eigenen Einstieg im Ledger: nichts, was hier
            # zu einer Position gehoert (der Kauf lag vor dem Fenster).
            continue
        runde["shares_closed"] += shares
        runde["exits"] += 1
        runde["realized_pnl"] += float(row.get("realized_pnl", 0.0) or 0.0)
        runde["closed_at"] = row.get("time")
        rest = runde["shares_bought"] - runde["shares_closed"]
        if action == "RESOLVE" or rest <= max(SHARE_EPS, runde["shares_bought"] * SHARE_EPS):
            abschliessen(key)

    for runde in offen.values():
        runde["closed"] = False
        runde["result"] = ""
        runden.append(runde)

    out = pd.DataFrame(runden, columns=ROUND_COLUMNS)
    if out.empty:
        return out
    return out.sort_values("opened_at", kind="stable").reset_index(drop=True)


def compute_stats(ledger: pd.DataFrame, open_positions: pd.DataFrame, curve: pd.DataFrame, bankroll: float) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "bankroll": float(bankroll),
        "copied_trades": 0,
        "skipped_trades": 0,
        # Geschlossene POSITIONEN, nicht Ausstiegsereignisse (position_rounds).
        "closed_trades": 0,
        "wins": 0,
        "losses": 0,
        # Aufloesungen, die genau die Kosten zurueckgaben: entschieden haben
        # sie nichts, also stehen sie ausserhalb des Quotennenners.
        "flat_trades": 0,
        "decided_trades": 0,
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
    stats["skip_reasons"] = {"out_of_cash": 0, "exposure_cap": 0, "no_position": 0, "bad_data": 0, "other": 0}
    stats["filtered_trades"] = 0
    # Warum bewusst nicht gefolgt wurde: Folge-Schwelle, fremder Verkauf
    # oder Nachkauf in eine Position, die schon mit vollem Einsatz laeuft.
    stats["filter_reasons"] = {"below_threshold": 0, "sell_not_followed": 0, "already_following": 0, "other": 0}
    if ledger is not None and not ledger.empty:
        copied = ledger[ledger["status"].isin(["copied", "settled"])]
        skipped = ledger[ledger["status"].eq("skipped")]
        stats["copied_trades"] = int((copied["action"].isin(["BUY", "SELL"])).sum())
        stats["skipped_trades"] = int(len(skipped))
        # Bewusst nicht gefolgt (Schwelle, fremde Verkaeufe) — getrennt von
        # den echten Fehlschlaegen, damit "skipped" Versagen bedeutet.
        stats["filtered_trades"] = int(ledger["status"].eq("filtered").sum())
        for note in ledger.loc[ledger["status"].eq("filtered"), "note"].fillna("").astype(str):
            if "below the follow threshold" in note:
                stats["filter_reasons"]["below_threshold"] += 1
            elif "not followed" in note:
                stats["filter_reasons"]["sell_not_followed"] += 1
            elif "already following" in note:
                stats["filter_reasons"]["already_following"] += 1
            else:
                stats["filter_reasons"]["other"] += 1
        # Gemessene Skip-Gruende statt einer Pauschalzahl: die Oberflaeche
        # soll sagen koennen, WARUM sie nicht mitging (Kasse leer und
        # Exposure-Deckel sind Bankroll-Grenzen, keine Datenluecken).
        for note in skipped["note"].fillna("").astype(str):
            if "out of cash" in note:
                stats["skip_reasons"]["out_of_cash"] += 1
            elif "exposure cap" in note:
                stats["skip_reasons"]["exposure_cap"] += 1
            elif "no copied position" in note:
                stats["skip_reasons"]["no_position"] += 1
            elif "bad trade data" in note:
                stats["skip_reasons"]["bad_data"] += 1
            else:
                stats["skip_reasons"]["other"] += 1
        stats["fees_paid"] = float(copied["fee"].fillna(0.0).sum())
        stats["volume_copied"] = float(copied.loc[copied["action"].eq("BUY"), "stake"].fillna(0.0).sum())
        closers = copied[copied["action"].isin(["SELL", "RESOLVE"])]
        # Jede Zaehlung unten laeuft ueber geschlossene Positionen. Vorher
        # war es die Zahl der Ausstiegszeilen: drei Tranchen einer einzigen
        # Position waren drei Trades und drei Siege, und eine Aufloesung zu
        # genau null sass ohne Sieg und ohne Niederlage im Nenner.
        runden = position_rounds(ledger)
        geschlossen = runden[runden["closed"]] if not runden.empty else runden
        ergebnis = geschlossen["realized_pnl"].fillna(0.0) if not geschlossen.empty else pd.Series(dtype="float64")
        stats["closed_trades"] = int(len(geschlossen))
        stats["wins"] = int((geschlossen["result"] == "win").sum()) if not geschlossen.empty else 0
        stats["losses"] = int((geschlossen["result"] == "loss").sum()) if not geschlossen.empty else 0
        stats["flat_trades"] = int((geschlossen["result"] == "flat").sum()) if not geschlossen.empty else 0
        # Eine flache Position hat nichts entschieden. Sie im Nenner zu
        # lassen zieht die Quote nach unten, ohne dass irgendetwas gegen die
        # Strategie spricht; sie wegzulassen und zu verschweigen wuerde die
        # Stichprobe schoenen. Also beides: raus aus dem Nenner, eigene Zahl.
        stats["decided_trades"] = stats["wins"] + stats["losses"]
        if stats["decided_trades"]:
            stats["win_rate"] = stats["wins"] / stats["decided_trades"]
        gross_win = float(ergebnis[ergebnis > 0].sum())
        gross_loss = float(-ergebnis[ergebnis < 0].sum())
        if gross_loss > 0:
            stats["profit_factor"] = gross_win / gross_loss
        elif gross_win > 0:
            stats["profit_factor"] = float("inf")
        stats["best_trade"] = float(ergebnis.max()) if len(ergebnis) else 0.0
        stats["worst_trade"] = float(ergebnis.min()) if len(ergebnis) else 0.0
        # Das Geld bleibt ereignisbasiert: ein Teilausstieg aus einer noch
        # laufenden Position ist gebuchtes Ergebnis, auch wenn die Position
        # oben noch nicht als geschlossen zaehlt.
        pnl = closers["realized_pnl"].fillna(0.0)
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


def _supports_end_param(fetch_activity: Callable[..., pd.DataFrame]) -> bool:
    """Ob der Fetcher ein ``end``-Keyword (Unix-Sekunden) annimmt."""

    try:
        return "end" in inspect.signature(fetch_activity).parameters
    except (TypeError, ValueError):
        return False


def fetch_window_trades(
    wallet: str,
    window_start: pd.Timestamp,
    fetch_activity: Callable[..., pd.DataFrame],
    page_size: int = 500,
    max_rows: int = 30_000,
    slice_rows: int = 3000,
) -> pd.DataFrame:
    """Page the wallet's activity feed back until the window start (TRADE rows only).

    The public data API rejects deep pagination (offset+limit beyond a few
    thousand rows), so offsets alone cannot cover a real window for an active
    wallet. When the fetcher accepts an ``end`` timestamp (the default
    ``get_polymarket_activity`` does), the scan opens a new slice at the oldest
    timestamp seen instead of paging deeper — offset resets to zero and the
    window keeps extending backwards. The boundary row is fetched twice by
    design (``end`` is inclusive; several trades can share one second) and
    removed by the transaction-hash dedupe below. ``max_rows`` stays as a
    safety cap; only when it is hit is the window reported as truncated.
    Errors on follow-up pages keep the rows already fetched instead of failing
    the whole backtest.
    """

    frames: list[pd.DataFrame] = []
    offset = 0
    total = 0
    slice_end: int | None = None
    truncated = False
    window_covered = False
    supports_end = _supports_end_param(fetch_activity)
    while total < max_rows:
        # Ein transienter Fehler (Rate-Limit, Netz) darf nicht den ganzen
        # Scan beenden — sonst deckt der Backtest still nur einen Bruchteil
        # des Fensters ab. Zwei Wiederholungen mit kurzem Backoff, erst
        # danach gilt die Seite als verloren.
        page = None
        letzter_fehler: Exception | None = None
        for versuch in range(3):
            try:
                if slice_end is None:
                    page = fetch_activity(wallet, limit=page_size, offset=offset)
                else:
                    page = fetch_activity(wallet, limit=page_size, offset=offset, end=slice_end)
                letzter_fehler = None
                break
            except Exception as exc:
                letzter_fehler = exc
                if versuch < 2:
                    time.sleep(0.6 * (versuch + 1))
        if letzter_fehler is not None:
            if frames:
                truncated = True
                break
            raise letzter_fehler
        if page is None or page.empty:
            window_covered = True
            break
        frames.append(page)
        total += len(page)
        oldest = pd.to_datetime(page["time"], utc=True, errors="coerce").min()
        if pd.isna(oldest) or oldest < window_start:
            window_covered = True
            break
        if len(page) < page_size:
            window_covered = True
            break
        offset += page_size
        if offset + page_size > slice_rows:
            if not supports_end:
                break
            next_end = int(oldest.timestamp())
            if slice_end is not None and next_end >= slice_end:
                # Mehr Zeilen in einer Sekunde als eine Scheibe fasst — hier
                # gaebe es keinen Fortschritt mehr, nur dieselbe Antwort.
                break
            slice_end = next_end
            offset = 0
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


def _resolve_token_values(
    trades: pd.DataFrame,
    fetch_markets_by_ids: Callable[[list[str]], list[dict[str, Any]]],
    fetch_markets_by_event_slugs: Callable[[list[str]], list[dict[str, Any]]] | None,
    token_value_builder: Callable[[list[dict[str, Any]]], dict[str, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """Token -> Wert/Status fuer alle gehandelten Maerkte des Fensters.

    Erst ueber die conditionIds (eine Batch-Abfrage je 20). Was dort fehlt —
    Sport-Untermaerkte kommen aus ``/markets?condition_ids=`` regelmaessig
    leer zurueck — wird ueber das Elternereignis nachgeschlagen
    (``/events?slug=``). Ohne diesen zweiten Weg blieben ganze Spieltage
    unaufgeloest: keine Wins/Losses, alles "open at cost".
    """

    if trades is None or trades.empty:
        return {}
    trade_keys = sorted({str(key) for key in trades.get("market_key", pd.Series(dtype=str)).dropna().astype(str) if key})
    markets = fetch_markets_by_ids(trade_keys) if trade_keys else []
    token_values = token_value_builder(markets)
    if fetch_markets_by_event_slugs is None or "asset" not in trades.columns:
        return token_values
    slug_col = "event_slug" if "event_slug" in trades.columns else ("slug" if "slug" in trades.columns else None)
    if slug_col is None:
        return token_values
    fehlend = trades[~trades["asset"].astype(str).isin(set(token_values))]
    slugs = sorted({str(s).strip() for s in fehlend[slug_col].dropna().astype(str) if str(s).strip()})
    if not slugs:
        return token_values
    extra = fetch_markets_by_event_slugs(slugs)
    if extra:
        for key, value in token_value_builder(extra).items():
            token_values.setdefault(key, value)
    return token_values


def source_peak_concurrency(
    trades: pd.DataFrame,
    token_values: dict[str, dict[str, Any]] | None = None,
) -> int:
    """Hoechstzahl gleichzeitig offener Positionen der QUELL-Wallet im Fenster.

    Chronologischer Durchlauf ueber die Trades selbst: BUY oeffnet oder
    erhoeht, SELL reduziert, und eine Position gilt als geschlossen, sobald
    ihr Markt laut ``token_values`` aufgeloest ist. Das ist die Kennzahl,
    an der eine Copy-Bankroll wirklich haengt: nicht wie VIEL die Wallet
    handelt, sondern wie viele Positionen sie zugleich offen halten kann.
    """

    return _peak_concurrent(source_position_intervals(trades, token_values))


def source_position_intervals(
    trades: pd.DataFrame,
    token_values: dict[str, dict[str, Any]] | None = None,
) -> list[tuple[pd.Timestamp, pd.Timestamp | None, float]]:
    """Offene Zeitraeume der QUELL-Positionen: (Einstieg, Ausstieg, Einstiegs-Notional).

    Chronologischer Durchlauf ueber die Trades selbst: der erste BUY oeffnet
    eine Position (ihr Notional ist die Einstiegsgroesse), SELL auf null
    schliesst sie, und ein Markt gilt als geschlossen, sobald er laut
    ``token_values`` aufgeloest ist. ``None`` als Ausstieg heisst: am
    Fensterende noch offen. Aus den Intervallen liest der Auto-Fit beides
    ab — wie viele Positionen zugleich offen sind, und wie gross die Wallet
    einsteigt.
    """

    if trades is None or trades.empty:
        return []
    shares: dict[str, float] = {}
    offen: dict[str, tuple[pd.Timestamp, float]] = {}
    pending: list[tuple[pd.Timestamp, str]] = []
    intervals: list[tuple[pd.Timestamp, pd.Timestamp | None, float]] = []

    def schliessen(asset: str, wann: pd.Timestamp) -> None:
        start = offen.pop(asset, None)
        if start is not None:
            intervals.append((start[0], wann, start[1]))

    for _, trade in trades.sort_values("time", ascending=True).iterrows():
        now = pd.to_datetime(trade.get("time"), utc=True, errors="coerce")
        while pending and pd.notna(now) and pending[0][0] <= now:
            wann, done = pending.pop(0)
            shares.pop(done, None)
            schliessen(done, wann)
        side = str(trade.get("side", "") or "").upper()
        asset = str(trade.get("asset", "") or "")
        size = float(trade.get("size", 0.0) or 0.0)
        if not asset or size <= 0.0:
            continue
        if side == "BUY":
            neu = asset not in shares
            shares[asset] = shares.get(asset, 0.0) + size
            if neu:
                offen[asset] = (now, float(trade.get("notional", 0.0) or 0.0))
                if token_values:
                    info = token_values.get(asset, {})
                    end_time = info.get("end_time")
                    if info.get("closed") and isinstance(end_time, pd.Timestamp) and pd.notna(end_time):
                        resolve_time = end_time if pd.isna(now) or end_time >= now else now
                        pending.append((resolve_time, asset))
                        pending.sort(key=lambda item: item[0])
        elif side == "SELL":
            rest = shares.get(asset, 0.0) - size
            if asset in shares:
                if rest <= 1e-9:
                    shares.pop(asset, None)
                    schliessen(asset, now)
                else:
                    shares[asset] = rest
    for asset in list(offen):
        start = offen.pop(asset)
        intervals.append((start[0], None, start[1]))
    return intervals


def _peak_concurrent(
    intervals: list[tuple[pd.Timestamp, pd.Timestamp | None, float]],
    threshold: float = 0.0,
) -> int:
    """Hoechstzahl gleichzeitig offener Positionen mit Einstieg >= threshold."""

    events: list[tuple[pd.Timestamp, int]] = []
    ende = pd.Timestamp.max.tz_localize("UTC")
    for entry, exit_, notional in intervals:
        if notional < threshold or not isinstance(entry, pd.Timestamp) or pd.isna(entry):
            continue
        events.append((entry, 1))
        events.append((exit_ if isinstance(exit_, pd.Timestamp) and pd.notna(exit_) else ende, -1))
    # Bei gleichem Zeitpunkt zaehlt der Ausstieg vor dem Einstieg.
    events.sort(key=lambda item: (item[0], item[1]))
    peak = laufend = 0
    for _, delta in events:
        laufend += delta
        peak = max(peak, laufend)
    return peak


def _fit_follow_threshold(
    intervals: list[tuple[pd.Timestamp, pd.Timestamp | None, float]],
    capacity: int,
) -> float | None:
    """Kleinste Einstiegs-Schwelle, bei der das gefilterte Tempo ins Budget passt.

    Monoton: eine hoehere Schwelle folgt weniger Positionen, also faellt
    die Spitzen-Gleichzeitigkeit. Binaersuche ueber die vorkommenden
    Einstiegsgroessen; ``None``, wenn selbst die groessten Einstiege (etwa
    lauter gleich grosse) nicht unter die Kapazitaet kommen.
    """

    if capacity <= 0 or not intervals:
        return None
    if _peak_concurrent(intervals, 0.0) <= capacity:
        return 0.0
    werte = sorted({notional for _, _, notional in intervals})
    if _peak_concurrent(intervals, werte[-1]) > capacity:
        return None
    lo, hi = 0, len(werte) - 1
    while lo < hi:
        mitte = (lo + hi) // 2
        if _peak_concurrent(intervals, werte[mitte]) <= capacity:
            hi = mitte
        else:
            lo = mitte + 1
    return float(werte[lo])


def _auto_fit_config(
    config: BacktestConfig,
    intervals: list[tuple[pd.Timestamp, pd.Timestamp | None, float]],
) -> tuple[BacktestConfig, dict[str, Any]]:
    """Die Copy-Logik an das gemessene Tempo der Wallet anpassen.

    Zwei Hebel, in dieser Reihenfolge:

    1. **Schwelle statt Staub.** Passt nicht der ganze Flow ins Budget
       (Bankroll x Exposure-Deckel, zehn Prozent Reserve fuer Gebuehren
       und Slippage), folgt der Backtest beim EINGESTELLTEN Einsatz nur
       noch den groessten Einstiegen der Wallet — wie ein echter Copier,
       der Conviction-Positionen mitgeht statt jeden Market-Making-Kruemel.
       Alles darunter markiert der Replay als "filtered", nicht als
       Fehlschlag.
    2. **Einsatz schrumpfen** bleibt der Rueckfall, wenn keine Schwelle
       trennt (etwa lauter gleich grosse Einstiege): dann wird der Einsatz
       je Copy so verkleinert, dass die volle Gleichzeitigkeit passt.

    Nichts davon passiert still: was angewendet wurde, steht in
    ``stats["auto_fit"]`` und auf der Seite.

    **Rueckschau.** Beide Hebel lesen das GANZE Fenster, bevor der erste Trade
    kopiert wird: die Spitzen-Gleichzeitigkeit und die Verteilung der
    Einstiegsgroessen stehen erst am Ende fest. Ein Copier haette diese
    Schwelle am Tag null nicht waehlen koennen. Der Lauf ist damit keine
    Vorwaerts-Rueckrechnung mehr, sondern die Frage "welche Schwelle haette
    zu diesem Fenster gepasst" — und genau das steht als ``hindsight`` im
    Ergebnis, damit die Seite es nicht als erzielbares Ergebnis ausgibt.
    """

    peak = _peak_concurrent(intervals)
    info: dict[str, Any] = {
        "applied": False,
        "mode": None,
        "peak_concurrent": int(peak),
        "stake": None,
        "follow_threshold": None,
        "followed_positions": len(intervals),
        "capacity": None,
        # Nur True, wenn tatsaechlich etwas angewendet wurde: die reine
        # Messung des Tempos steht auch ohne Auto-Fit im Ergebnis und
        # veraendert den Lauf nicht.
        "hindsight": False,
        "note": "",
    }
    if peak <= 0:
        return config, info
    budget = float(config.bankroll) * max(0.0, min(float(config.max_exposure_pct), 100.0)) / 100.0
    geschrumpft = max(MIN_STAKE, min(float(config.max_stake), 0.9 * budget / peak))
    info["stake"] = geschrumpft
    if not config.auto_fit or config.sizing_mode not in (SIZING_FIXED, SIZING_PERCENT):
        return config, info
    # Der Einsatz, den die Einstellungen ergeben — er bestimmt, wie viele
    # Copies gleichzeitig ins Budget passen.
    if config.sizing_mode == SIZING_PERCENT:
        stake_user = float(config.bankroll) * float(config.stake_value) / 100.0
    else:
        stake_user = float(config.stake_value)
    stake_user = max(MIN_STAKE, min(float(config.max_stake), stake_user))
    if budget > 0:
        stake_user = min(stake_user, budget)
    capacity = max(1, int(0.9 * budget // stake_user)) if budget > 0 else 0
    info["capacity"] = capacity
    threshold = _fit_follow_threshold(intervals, capacity)
    if threshold is not None:
        followed = sum(1 for _, _, notional in intervals if notional >= threshold)
        info.update({
            "applied": True,
            "mode": "threshold",
            "stake": stake_user,
            "follow_threshold": float(threshold),
            "followed_positions": followed,
            "hindsight": True,
            "note": AUTO_FIT_HINDSIGHT_NOTE,
        })
        return replace(config, min_follow_notional=float(threshold)), info
    # Keine Schwelle trennt: Einsatz je Copy schrumpfen, allem folgen.
    info.update({
        "applied": True,
        "mode": "stake",
        "stake": geschrumpft,
        "hindsight": True,
        "note": AUTO_FIT_HINDSIGHT_NOTE,
    })
    if config.sizing_mode == SIZING_PERCENT and config.bankroll > 0:
        return replace(config, stake_value=100.0 * geschrumpft / float(config.bankroll)), info
    return replace(config, stake_value=geschrumpft), info


def run_backtest(
    config: BacktestConfig,
    *,
    fetch_activity: Callable[..., pd.DataFrame] | None = None,
    fetch_markets_by_ids: Callable[[list[str]], list[dict[str, Any]]] | None = None,
    fetch_markets_by_event_slugs: Callable[[list[str]], list[dict[str, Any]]] | None = None,
    token_values: dict[str, dict[str, Any]] | None = None,
    now: pd.Timestamp | None = None,
    data: WindowData | None = None,
    fetch_price_history: Callable[[str, str], pd.DataFrame] | None = None,
) -> BacktestResult:
    """Full backtest: fetch window trades, replay with sizing + flat benchmark, settle, score.

    Mit ``data`` (ein fertiges ``WindowData``) entfaellt der Netzweg: das
    Replay laeuft auf den geladenen Trades und Aufloesungen.

    ``fetch_price_history(token_id, interval)`` liefert den Preisverlauf
    eines Tokens fuer die Bewertungskurve. Im Produktionspfad ohne
    injizierte Fetcher ist das der CLOB-Verlauf; mit ``data`` reicht der
    Aufrufer ihn mit, und die Verlaeufe bleiben in ``data.price_history``.
    Ohne Fetcher bleiben offene Kopien bis zum Schluss zum Einstand.
    """

    if data is not None:
        window_end = data.window_end
        window_start = data.window_start
        trades = data.trades
        window_truncated = data.window_truncated
        token_values = data.token_values if token_values is None else token_values
    else:
        if fetch_activity is None or fetch_markets_by_ids is None:
            from src import prediction_markets as md

            fetch_activity = fetch_activity or md.get_polymarket_activity
            fetch_markets_by_ids = fetch_markets_by_ids or md.get_polymarket_markets_by_condition_ids
            # Der Slug-Rueckweg gehoert zum Produktionspfad; injizierte Fetcher
            # (Tests) bekommen ihn nur, wenn sie ihn selbst mitbringen.
            fetch_markets_by_event_slugs = fetch_markets_by_event_slugs or md.get_polymarket_markets_by_event_slugs
            token_value_builder = md.polymarket_token_value_map
            fetch_price_history = fetch_price_history or md.get_polymarket_price_history_lifetime
        else:
            from src import prediction_markets as md

            token_value_builder = md.polymarket_token_value_map

        window_end = now if now is not None else pd.Timestamp.now(tz="UTC")
        window_start = window_end - pd.Timedelta(days=int(config.days))
        trades, window_truncated = fetch_window_trades(config.wallet, window_start, fetch_activity)

        if token_values is None:
            token_values = _resolve_token_values(trades, fetch_markets_by_ids, fetch_markets_by_event_slugs, token_value_builder)

    # Tempo der Quell-Wallet messen und, wenn verlangt, die Copy-Logik
    # daran anpassen (Folge-Schwelle oder geschrumpfter Einsatz) — statt
    # blind in Kasse-leer/Exposure-Deckel zu laufen.
    intervals = source_position_intervals(trades, token_values)
    replay_config, auto_fit_info = _auto_fit_config(config, intervals)
    ledger, positions = replay(trades, replay_config, token_values, asof=window_end)
    flat_config = BacktestConfig(
        wallet=config.wallet,
        days=config.days,
        bankroll=config.bankroll,
        sizing_mode=SIZING_FIXED,
        stake_value=config.flat_stake,
        max_stake=config.flat_stake,
        fee_bps=config.fee_bps,
        fee_model=config.fee_model,
        fee_category=config.fee_category,
        slippage_bps=config.slippage_bps,
        flat_stake=config.flat_stake,
        strategy=config.strategy,
    )
    flat_ledger, flat_positions = replay(trades, flat_config, token_values, asof=window_end)

    settlement, open_positions = settle(positions, token_values, asof=window_end)
    flat_settlement, flat_open = settle(flat_positions, token_values, asof=window_end)

    full_ledger = pd.concat([ledger, settlement], ignore_index=True) if not settlement.empty else ledger
    flat_full = pd.concat([flat_ledger, flat_settlement], ignore_index=True) if not flat_settlement.empty else flat_ledger

    unrealized = float(open_positions["unrealized_pnl"].sum()) if not open_positions.empty else 0.0
    flat_unrealized = float(flat_open["unrealized_pnl"].sum()) if not flat_open.empty else 0.0
    # Ist das Fenster abgeschnitten, beginnt die Kurve an der tatsaechlich
    # abgedeckten Kante. Sonst behauptete der flache Vorlauf Wissen ueber
    # Tage, aus denen kein einziger Trade geladen wurde.
    curve_start = window_start
    if window_truncated and trades is not None and not trades.empty:
        oldest_trade = pd.to_datetime(trades["time"], utc=True, errors="coerce").min()
        if pd.notna(oldest_trade) and oldest_trade > curve_start:
            curve_start = oldest_trade
    # Bewertungskurve: Preisverlauf der kopierten Token, stundenweise bis
    # zu einem Monat, darueber in Sechs-Stunden-Schritten.
    interval = "1h" if (window_end - curve_start) <= pd.Timedelta(days=31) else "6h"
    price_history: dict[str, pd.DataFrame] = {}
    mtm_info: dict[str, Any] = {"positions_marked": 0, "positions_total": 0, "capped": False, "interval": None}
    if fetch_price_history is not None:
        cache = getattr(data, "price_history", None) if data is not None else None
        if cache is None:
            cache = {}
        price_history, mtm_info = mark_to_market_history(full_ledger, open_positions, fetch_price_history, cache, interval)
    fade = config.strategy == STRATEGY_FADE
    curve = equity_curve(full_ledger, curve_start, window_end, config.bankroll, unrealized, price_history=price_history, fade=fade)
    flat_curve = equity_curve(flat_full, curve_start, window_end, config.bankroll, flat_unrealized, price_history=price_history, fade=fade)
    curve["benchmark"] = flat_curve["equity"].to_numpy()

    stats = compute_stats(full_ledger, open_positions, curve, config.bankroll)
    flat_stats = compute_stats(flat_full, flat_open, flat_curve, config.bankroll)
    stats["window_truncated"] = bool(window_truncated)
    stats["mark_to_market"] = mtm_info
    stats["auto_fit"] = auto_fit_info
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
    fetch_markets_by_event_slugs: Callable[[list[str]], list[dict[str, Any]]] | None = None,
    token_values: dict[str, dict[str, Any]] | None = None,
    now: pd.Timestamp | None = None,
    data: WindowData | None = None,
) -> pd.DataFrame:
    """Replay the same window once per sizing variant and rank the outcomes.

    Fetches the wallet's trades and market resolutions a single time (or
    takes them from ``data``), then runs the full replay/settle/score
    pipeline for every variant. Fee, slippage, exposure cap, strategy
    (copy/fade) and trader portfolio value come from ``config``; only the
    sizing changes per row. Sorted by final equity.
    """

    from src import prediction_markets as md

    if data is not None:
        window_end, window_start, trades = data.window_end, data.window_start, data.trades
        resolved_token_values = data.token_values if token_values is None else token_values
    else:
        if fetch_markets_by_ids is None:
            # Produktionspfad: der Slug-Rueckweg gehoert dazu (siehe
            # _resolve_token_values); injizierte Fetcher bringen ihn selbst mit.
            fetch_markets_by_event_slugs = fetch_markets_by_event_slugs or md.get_polymarket_markets_by_event_slugs
        fetch_activity = fetch_activity or md.get_polymarket_activity
        fetch_markets_by_ids = fetch_markets_by_ids or md.get_polymarket_markets_by_condition_ids
        window_end = now if now is not None else pd.Timestamp.now(tz="UTC")
        window_start = window_end - pd.Timedelta(days=int(config.days))
        trades, _truncated = fetch_window_trades(config.wallet, window_start, fetch_activity)
        resolved_token_values = token_values
        if resolved_token_values is None:
            resolved_token_values = _resolve_token_values(
                trades, fetch_markets_by_ids, fetch_markets_by_event_slugs, md.polymarket_token_value_map
            )
    if variants is None:
        variants = default_strategy_variants(config)
    rows: list[dict[str, Any]] = []
    for label, sizing_mode, stake_value in variants:
        variant_config = BacktestConfig(
            wallet=config.wallet,
            days=config.days,
            bankroll=config.bankroll,
            sizing_mode=sizing_mode,
            stake_value=stake_value,
            max_stake=config.max_stake,
            fee_bps=config.fee_bps,
            fee_model=config.fee_model,
            fee_category=config.fee_category,
            slippage_bps=config.slippage_bps,
            flat_stake=config.flat_stake,
            strategy=config.strategy,
            max_exposure_pct=config.max_exposure_pct,
            trader_portfolio_value=config.trader_portfolio_value,
        )
        ledger, positions = replay(trades, variant_config, resolved_token_values, asof=window_end)
        settlement, open_positions = settle(positions, resolved_token_values, asof=window_end)
        full_ledger = pd.concat([ledger, settlement], ignore_index=True) if not settlement.empty else ledger
        unrealized = float(open_positions["unrealized_pnl"].sum()) if not open_positions.empty else 0.0
        # Verlaeufe, die der Hauptlauf schon geladen hat, bewerten auch die
        # Varianten; nachgeladen wird hier nichts.
        cached_history = {a: f for a, f in (data.price_history if data is not None else {}).items() if f is not None and not f.empty}
        curve = equity_curve(
            full_ledger, window_start, window_end, config.bankroll, unrealized,
            price_history=cached_history, fade=config.strategy == STRATEGY_FADE,
        )
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
                # Der Nenner der Trefferquote gehoert in dieselbe Zeile:
                # copied_trades zaehlt auch die noch offenen Einstiege.
                # closed_trades sind geschlossene Positionen, decided_trades
                # davon die entschiedenen (der Nenner der Quote).
                "closed_trades": stats["closed_trades"],
                "decided_trades": stats["decided_trades"],
                "flat_trades": stats["flat_trades"],
                "copied_trades": stats["copied_trades"],
                "skipped_trades": stats["skipped_trades"],
                "volume_copied": stats["volume_copied"],
            }
        )
    comparison = pd.DataFrame(rows)
    if comparison.empty:
        return comparison
    return comparison.sort_values("final_equity", ascending=False).reset_index(drop=True)
