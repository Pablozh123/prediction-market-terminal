"""Size outliers: a wallet trading far above what its market usually sees.

No points, no freshness, no category weight. This is the question the
tracker posts ask first and the insider score never asked on its own: this
market usually sees a certain size of flow; one wallet just put in many
times that. The baseline is the market's own recent tape (its last thousand
prints, the ones older than the window under judgement), the yardstick is
the 99th percentile of what one wallet put into the market within an hour
over that tape, and a wallet whose money in the last hour reaches twice the
yardstick, and at least the whale threshold, is an outlier. Then the second
question, the one that gives the picture: was it the only wallet above the
baseline in that window, or one of several?

Calibrated by eye on 2026-09-05 over four live markets: at twice the 99th
percentile the rule names 0.2 to 2.5 wallet-hours a day per market, the two
fresh Fed whales of that week among them; at three times the 95th
percentile it named four to fourteen a day. The numbers are chosen, not
fitted, and the env variables below move them without a deploy.

Streamlit-free, network-free: the per-market tapes come in as frames.
"""

from __future__ import annotations

import os
from typing import Any, Iterable, Mapping

import pandas as pd

from app.filters import numeric_col
from app.format import money
from src.prediction_markets import identified_wallets

#: The yardstick: this quantile of per-wallet-hour totals in the baseline.
OUTLIER_QUANTILE = 0.99
#: A wallet's money in the window must reach this multiple of the yardstick.
OUTLIER_RATIO = 2.0
#: Below this many baseline prints the market has no baseline yet.
OUTLIER_MIN_PRINTS = 100
#: The window under judgement, in minutes before "now".
OUTLIER_RECENT_MINUTES = 60.0
#: How many markets one scan measures against their own tape (largest
#: wallet total first); each is one call of about half a second, cached.
OUTLIER_MAX_MARKETS = 25
#: How many prints of a market's tape the baseline reads.
BASELINE_PRINTS = 1000

BASELINE_SOLID = "solid"
BASELINE_THIN = "thin"
BASELINE_NONE = "none"


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return float(default)
    return value if value > 0 else float(default)


def outlier_rules() -> dict[str, Any]:
    """The rule as numbers, env overrides included, so every surface prints
    the same yardstick it was judged by."""

    quantile = _env_float("RISK_OUTLIER_QUANTILE", OUTLIER_QUANTILE)
    if not 0.5 <= quantile < 1.0:
        quantile = OUTLIER_QUANTILE
    return {
        "quantile": quantile,
        "ratio": _env_float("RISK_OUTLIER_RATIO", OUTLIER_RATIO),
        "min_prints": int(_env_float("RISK_OUTLIER_MIN_PRINTS", OUTLIER_MIN_PRINTS)),
        "recent_minutes": _env_float("RISK_OUTLIER_RECENT_MINUTES", OUTLIER_RECENT_MINUTES),
        "max_markets": int(_env_float("RISK_OUTLIER_MAX_MARKETS", OUTLIER_MAX_MARKETS)),
        "baseline_prints": BASELINE_PRINTS,
    }


def _prep(prints: pd.DataFrame) -> pd.DataFrame:
    if prints is None or prints.empty:
        return pd.DataFrame(columns=["time", "notional", "wallet", "trader", "side", "outcome", "price"])
    df = prints.copy()
    df["time"] = pd.to_datetime(df["time"] if "time" in df.columns else pd.Series(pd.NaT, index=df.index), utc=True, errors="coerce")
    df["notional"] = numeric_col(df, "notional").clip(lower=0.0)
    df["wallet"] = df.get("wallet", pd.Series("", index=df.index)).fillna("").astype(str).str.lower().str.strip()
    df["trader"] = df.get("trader", pd.Series("", index=df.index)).fillna("").astype(str)
    df["side"] = df.get("side", pd.Series("", index=df.index)).fillna("").astype(str).str.upper()
    df["outcome"] = df.get("outcome", pd.Series("", index=df.index)).fillna("").astype(str).str.upper()
    df["price"] = pd.to_numeric(df.get("price", pd.Series(dtype=float)), errors="coerce")
    df = df.dropna(subset=["time"])
    df = df[identified_wallets(df["wallet"])]
    return df.sort_values("time").reset_index(drop=True)


def _hours(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    return max(0.0, float((frame["time"].max() - frame["time"].min()).total_seconds()) / 3600.0)


def market_baseline(
    prints: pd.DataFrame,
    *,
    before: Any,
    quantile: float = OUTLIER_QUANTILE,
    min_prints: int = OUTLIER_MIN_PRINTS,
) -> dict[str, Any]:
    """What this market usually sees, from its prints older than ``before``.

    ``yardstick`` is the ``quantile`` of per-wallet-hour totals (every wallet's
    money summed per clock hour); ``max`` the largest single print, ``state``
    solid / thin / none by the print count against ``min_prints``.
    """

    df = _prep(prints)
    cut = pd.Timestamp(before)
    if cut.tzinfo is None:
        cut = cut.tz_localize("UTC")
    hist = df[df["time"] < cut]
    n = int(len(hist))
    out: dict[str, Any] = {
        "n": n,
        "state": BASELINE_SOLID if n >= int(min_prints) else (BASELINE_THIN if n else BASELINE_NONE),
        "quantile": float(quantile),
        "min_prints": int(min_prints),
        "yardstick": None, "median": None, "p95": None, "max": None,
        "wallet_hours": 0, "wallets": 0, "hours": 0.0, "volume": 0.0, "volume_per_hour": None,
        "first_utc": "", "last_utc": "",
        "yardstick_label": "", "max_label": "", "hours_label": "",
    }
    if not n:
        return out
    hours = _hours(hist)
    per_wallet_hour = hist.groupby([hist["wallet"], hist["time"].dt.floor("h")])["notional"].sum()
    out.update({
        "yardstick": float(per_wallet_hour.quantile(float(quantile))),
        "median": float(hist["notional"].median()),
        "p95": float(hist["notional"].quantile(0.95)),
        "max": float(hist["notional"].max()),
        "wallet_hours": int(len(per_wallet_hour)),
        "wallets": int(hist["wallet"].nunique()),
        "hours": round(hours, 1),
        "volume": float(hist["notional"].sum()),
        "volume_per_hour": float(hist["notional"].sum() / hours) if hours > 0 else None,
        "first_utc": hist["time"].min().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_utc": hist["time"].max().strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    out["yardstick_label"] = money(out["yardstick"])
    out["max_label"] = money(out["max"])
    out["hours_label"] = hours_label(hours)
    return out


def hours_label(hours: float) -> str:
    value = max(0.0, float(hours or 0.0))
    return f"{value:.0f} h" if value < 48.0 else f"{value / 24.0:.1f} d"


def _side_label(group: pd.DataFrame) -> str:
    """The wallet's dominant side in words: "YES buys", "NO sells", or ""."""

    if group.empty:
        return ""
    buckets = group.groupby([group["side"], group["outcome"]])["notional"].sum().sort_values(ascending=False)
    if buckets.empty:
        return ""
    side, outcome = buckets.index[0]
    if outcome not in ("YES", "NO"):
        return ""
    return f"{outcome} {'sells' if side == 'SELL' else 'buys'}"


def wallet_window(prints: pd.DataFrame, *, since: Any, until: Any) -> pd.DataFrame:
    """Every wallet's money in the window: prints, largest, total, side,
    price (notional-weighted), first and last print, share of the window."""

    columns = ["wallet", "trader", "prints", "largest", "total", "side", "price", "first_print", "last_print", "share"]
    df = _prep(prints)
    lo = pd.Timestamp(since)
    hi = pd.Timestamp(until)
    if lo.tzinfo is None:
        lo = lo.tz_localize("UTC")
    if hi.tzinfo is None:
        hi = hi.tz_localize("UTC")
    window = df[(df["time"] >= lo) & (df["time"] <= hi)]
    if window.empty:
        return pd.DataFrame(columns=columns)
    total_volume = float(window["notional"].sum())
    rows: list[dict[str, Any]] = []
    for wallet, group in window.groupby("wallet", sort=False):
        weight = group["notional"].sum()
        priced = group[group["price"].notna() & (group["price"] > 0)]
        price = float((priced["price"] * priced["notional"]).sum() / priced["notional"].sum()) if not priced.empty and priced["notional"].sum() > 0 else None
        names = [t for t in group["trader"].tolist() if t]
        rows.append({
            "wallet": str(wallet),
            "trader": names[0] if names else "",
            "prints": int(len(group)),
            "largest": float(group["notional"].max()),
            "total": float(weight),
            "side": _side_label(group),
            "price": round(price, 4) if price is not None else None,
            "first_print": group["time"].min(),
            "last_print": group["time"].max(),
            "share": float(weight / total_volume) if total_volume > 0 else 0.0,
        })
    return pd.DataFrame(rows, columns=columns).sort_values("total", ascending=False).reset_index(drop=True)


def market_picture(
    prints: pd.DataFrame,
    *,
    now: Any,
    whale_threshold: float,
    rules: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """One market against its own tape: the baseline, every wallet of the
    recent window with its ratio to the yardstick, which of them are
    elevated, and the verdict (none / single / several)."""

    cfg = dict(outlier_rules())
    if rules:
        cfg.update(rules)
    clock = pd.Timestamp(now)
    if clock.tzinfo is None:
        clock = clock.tz_localize("UTC")
    since = clock - pd.Timedelta(minutes=float(cfg["recent_minutes"]))
    baseline = market_baseline(prints, before=since, quantile=float(cfg["quantile"]), min_prints=int(cfg["min_prints"]))
    window = wallet_window(prints, since=since, until=clock)
    yardstick = baseline.get("yardstick")
    floor = float(whale_threshold or 0.0)
    wallets: list[dict[str, Any]] = []
    for _, row in window.iterrows():
        ratio = (float(row["total"]) / float(yardstick)) if yardstick else None
        elevated = bool(
            baseline["state"] == BASELINE_SOLID and ratio is not None
            and ratio >= float(cfg["ratio"]) and float(row["total"]) >= floor
        )
        wallets.append({
            "wallet": row["wallet"],
            "name": row["trader"],
            "prints": int(row["prints"]),
            "largest": float(row["largest"]),
            "total": float(row["total"]),
            "side": row["side"],
            "price": row["price"],
            "first_print": row["first_print"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_print": row["last_print"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "share": round(float(row["share"]), 4),
            "ratio": round(ratio, 2) if ratio is not None else None,
            "elevated": elevated,
            "total_label": money(float(row["total"])),
            "largest_label": money(float(row["largest"])),
            "ratio_label": ratio_label(ratio),
        })
    wallets.sort(key=lambda w: (not w["elevated"], -w["total"]))
    elevated = sum(1 for w in wallets if w["elevated"])
    window_volume = float(window["total"].sum()) if not window.empty else 0.0
    usual = baseline.get("volume_per_hour")
    volume_ratio = (window_volume / (float(usual) * float(cfg["recent_minutes"]) / 60.0)) if usual else None
    verdict = "none" if not elevated else ("single" if elevated == 1 else "several")
    return {
        "baseline": baseline,
        "rules": {k: cfg[k] for k in ("quantile", "ratio", "min_prints", "recent_minutes")},
        "floor": floor,
        "window": {
            "minutes": float(cfg["recent_minutes"]),
            "since": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "until": clock.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "wallets": int(len(wallets)),
            "volume": window_volume,
            "volume_label": money(window_volume),
            "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
            "volume_ratio_label": ratio_label(volume_ratio) if volume_ratio is not None else "",
        },
        "wallets": wallets,
        "elevated": int(elevated),
        "verdict": verdict,
        "verdict_text": verdict_text(verdict, elevated, int(len(wallets)), baseline["state"], int(baseline["n"])),
    }


def verdict_text(verdict: str, elevated: int, wallets_in_window: int, state: str, n: int) -> str:
    if state != BASELINE_SOLID:
        return f"no baseline yet: {n} prints in the market's tape before the window" if n else "no baseline: no prints before the window"
    others = max(0, wallets_in_window - elevated)
    if verdict == "single":
        return f"the only wallet above the baseline in this window ({others} other wallet{'s' if others != 1 else ''} inside it)"
    if verdict == "several":
        return f"{elevated} wallets above the baseline in this window ({others} inside it)"
    return f"no wallet above the baseline ({wallets_in_window} in the window)"


def ratio_label(ratio: Any) -> str:
    try:
        value = float(ratio)
    except (TypeError, ValueError):
        return ""
    if value != value:
        return ""
    return f"{value:.0f}×" if value >= 10 else f"{value:.1f}×"


def candidate_markets(tape: pd.DataFrame, *, whale_threshold: float, limit: int | None = None) -> list[dict[str, Any]]:
    """Polymarket markets of a tape worth measuring: those where one wallet's
    money in the tape reaches the whale threshold, largest such total first.
    Each item: market_key, title, url."""

    if tape is None or tape.empty or not {"wallet", "market_key"}.issubset(tape.columns):
        return []
    df = tape.copy()
    df["platform"] = df.get("platform", pd.Series("Polymarket", index=df.index)).fillna("").astype(str)
    df["market_key"] = df["market_key"].fillna("").astype(str)
    df["wallet"] = df["wallet"].fillna("").astype(str).str.lower().str.strip()
    df["notional"] = numeric_col(df, "notional").clip(lower=0.0)
    df = df[df["platform"].str.lower().eq("polymarket") & df["market_key"].str.startswith("0x") & identified_wallets(df["wallet"])]
    if df.empty:
        return []
    totals = df.groupby(["market_key", "wallet"])["notional"].sum().reset_index()
    top = totals.groupby("market_key")["notional"].max().sort_values(ascending=False)
    top = top[top >= float(whale_threshold)]
    keys = [str(k) for k in top.index]
    if limit is not None:
        keys = keys[: max(0, int(limit))]
    titles = df.drop_duplicates("market_key").set_index("market_key")
    out: list[dict[str, Any]] = []
    for key in keys:
        row = titles.loc[key] if key in titles.index else None
        out.append({
            "market_key": key,
            "title": str(row.get("title", "")) if row is not None else "",
            "url": str(row.get("url", "")) if row is not None else "",
            "top_wallet_total": float(top[key]),
        })
    return out


def size_outliers(
    tapes: Mapping[str, pd.DataFrame],
    *,
    now: Any,
    whale_threshold: float,
    rules: Mapping[str, Any] | None = None,
    meta: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Every market against its own tape. Returns (rows, pictures): one flat
    row per elevated wallet (ratio descending) and one picture per market
    that has at least one elevated wallet."""

    rows: list[dict[str, Any]] = []
    pictures: list[dict[str, Any]] = []
    info = meta or {}
    for key, tape in (tapes or {}).items():
        picture = market_picture(tape, now=now, whale_threshold=whale_threshold, rules=rules)
        extra = dict(info.get(key) or {})
        title = str(extra.get("title") or (tape["title"].iloc[0] if tape is not None and not tape.empty and "title" in tape.columns else "") or "")
        url = str(extra.get("url") or (tape["url"].iloc[0] if tape is not None and not tape.empty and "url" in tape.columns else "") or "")
        venue = str(extra.get("venue") or "Polymarket")
        category = str(extra.get("category") or "")
        picture.update({"market_key": str(key), "title": title, "url": url, "venue": venue, "category": category})
        if not picture["elevated"]:
            continue
        pictures.append(picture)
        baseline = picture["baseline"]
        for wallet in picture["wallets"]:
            if not wallet["elevated"]:
                continue
            rows.append({
                "venue": venue, "market_key": str(key), "title": title, "url": url, "category": category,
                "wallet": wallet["wallet"], "name": wallet["name"],
                "total": wallet["total"], "largest": wallet["largest"], "prints": wallet["prints"],
                "side": wallet["side"], "price": wallet["price"], "share": wallet["share"],
                "ratio": wallet["ratio"], "yardstick": baseline["yardstick"],
                "baseline_n": baseline["n"], "baseline_hours": baseline["hours"], "baseline_max": baseline["max"],
                "baseline_wallet_hours": baseline["wallet_hours"],
                "elevated_wallets": picture["elevated"], "wallets_in_window": picture["window"]["wallets"],
                "verdict": picture["verdict"], "verdict_text": picture["verdict_text"],
                "window_minutes": picture["window"]["minutes"],
                "window_volume_ratio": picture["window"]["volume_ratio"],
                "first_print": wallet["first_print"], "last_print": wallet["last_print"],
                "first_trade_days": None, "first_trade_state": "unmeasured", "first_trade_label": "not asked",
                "total_label": wallet["total_label"], "largest_label": wallet["largest_label"],
                "ratio_label": wallet["ratio_label"], "yardstick_label": money(float(baseline["yardstick"] or 0.0)),
                "baseline_max_label": money(float(baseline["max"] or 0.0)),
            })
    rows.sort(key=lambda r: -(r["ratio"] or 0.0))
    pictures.sort(key=lambda p: -max((w["ratio"] or 0.0) for w in p["wallets"] if w["elevated"]))
    return rows, pictures


def attach_first_trades(rows: Iterable[dict[str, Any]], pictures: Iterable[dict[str, Any]], origins: Mapping[str, Any] | None) -> None:
    """Write the measured first trade (days before the wallet's last print in
    the window) into the rows and the pictures' wallet lists, in place."""

    from app import api_views as apv
    from app import suspicion as susp

    lookup = susp._origin_lookup(origins)

    def _fill(item: dict[str, Any]) -> None:
        origin = lookup.get(str(item.get("wallet") or "").lower())
        state = susp.ORIGIN_UNMEASURED if origin is None else origin[1]
        days = None
        if origin is not None and origin[1] == susp.ORIGIN_MEASURED and origin[0] is not None:
            last = pd.Timestamp(item.get("last_print"))
            if pd.notna(last):
                if last.tzinfo is None:
                    last = last.tz_localize("UTC")
                days = round(max(0.0, (last.timestamp() - float(origin[0])) / 86_400.0), 2)
        item["first_trade_days"] = days
        item["first_trade_state"] = state
        item["first_trade_label"] = apv.first_trade_label(days, state)

    for row in rows:
        _fill(row)
    for picture in pictures:
        for wallet in picture.get("wallets") or []:
            _fill(wallet)


def outlier_payload(
    rows: list[dict[str, Any]],
    pictures: list[dict[str, Any]],
    *,
    rules: Mapping[str, Any] | None = None,
    screened: int = 0,
    errors: list[str] | None = None,
    as_of: str = "",
    whale_threshold: float | None = None,
) -> dict[str, Any]:
    """The section of the risk payload: rules in words and numbers, the
    flat rows, the market pictures, and how many markets were measured."""

    cfg = dict(outlier_rules())
    if rules:
        cfg.update(rules)
    return {
        "rules": {
            **{k: cfg[k] for k in ("quantile", "ratio", "min_prints", "recent_minutes", "max_markets", "baseline_prints")},
            "floor": float(whale_threshold) if whale_threshold is not None else None,
            "reads": (
                f"A wallet whose money in the last {cfg['recent_minutes']:g} minutes reaches {cfg['ratio']:g} times the "
                f"{int(round(cfg['quantile'] * 100))}th percentile of what one wallet put into the same market within an hour, "
                f"over the market's own last {cfg['baseline_prints']} prints before the window, and at least the whale threshold. "
                f"Markets with fewer than {cfg['min_prints']} prints before the window have no baseline yet and are not judged."
            ),
        },
        "rows": rows,
        "markets": pictures,
        "count": len(rows),
        "screened": int(screened),
        "errors": list(errors or []),
        "as_of": as_of,
        "note": "No points and no probability: the market's own tape is the yardstick, and the verdict says whether the wallet was alone above it.",
    }
