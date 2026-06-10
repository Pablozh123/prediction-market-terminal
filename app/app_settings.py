"""Persisted application settings (data/app_settings.json).

Streamlit-free: used by the terminal's Settings page and by background scripts
(alert scanner) that need the same configuration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path("data/app_settings.json")

DEFAULTS: dict[str, Any] = {
    # Data loading
    "market_sample": 250,
    "trade_sample": 250,
    "whale_threshold": 2500,
    # Backtester defaults
    "backtest_bankroll": 10_000.0,
    "backtest_max_bet": 25.0,
    "backtest_fee_bps": 20.0,
    "backtest_slippage_bps": 50.0,
    "backtest_flat_stake": 25.0,
    # Alert scanner / delivery
    "alerts_enabled": False,
    "alert_interval_minutes": 10,
    "alert_min_move_cents": 3.0,
    "alert_holder_checks": 0,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
}

_INT_KEYS = {"market_sample", "trade_sample", "whale_threshold", "alert_interval_minutes", "alert_holder_checks"}
_FLOAT_KEYS = {
    "backtest_bankroll",
    "backtest_max_bet",
    "backtest_fee_bps",
    "backtest_slippage_bps",
    "backtest_flat_stake",
    "alert_min_move_cents",
}
_BOOL_KEYS = {"alerts_enabled"}


def _coerce(key: str, value: Any) -> Any:
    try:
        if key in _INT_KEYS:
            return int(float(value))
        if key in _FLOAT_KEYS:
            return float(value)
        if key in _BOOL_KEYS:
            return bool(value)
    except (TypeError, ValueError):
        return DEFAULTS[key]
    return str(value) if value is not None else DEFAULTS[key]


def load_settings(path: str | Path = SETTINGS_PATH) -> dict[str, Any]:
    """Load settings merged over defaults; unknown keys are dropped, bad values reset."""

    settings = dict(DEFAULTS)
    file_path = Path(path)
    if file_path.exists():
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw = {}
        if isinstance(raw, dict):
            for key in DEFAULTS:
                if key in raw:
                    settings[key] = _coerce(key, raw[key])
    return settings


def save_settings(settings: dict[str, Any], path: str | Path = SETTINGS_PATH) -> dict[str, Any]:
    """Persist known keys (coerced) and return the cleaned settings dict."""

    cleaned = {key: _coerce(key, settings.get(key, DEFAULTS[key])) for key in DEFAULTS}
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    return cleaned
