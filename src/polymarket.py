"""Polymarket API client with Cloudflare DNS fallback (bypasses Swiss ISP block)."""

import time as _time
import socket
import requests
import pandas as pd

ENDPOINTS = [
    "https://gamma-api.polymarket.com",
    "https://clob.polymarket.com",
]

# ── DNS-Patch: Cloudflare statt ISP-DNS (umgeht Schweizer Block) ──────────────

def _apply_dns_patch():
    """Patcht socket.getaddrinfo um 1.1.1.1 für Polymarket-Domains zu nutzen."""
    try:
        import dns.resolver
        _orig  = socket.getaddrinfo
        _res   = dns.resolver.Resolver()
        _res.nameservers = ['1.1.1.1', '8.8.8.8']
        _hosts = {'gamma-api.polymarket.com', 'clob.polymarket.com'}

        def _patched(host, port, *args, **kwargs):
            if host in _hosts:
                try:
                    ip = str(_res.resolve(host, 'A')[0])
                    return _orig(ip, port, *args, **kwargs)
                except Exception:
                    pass
            return _orig(host, port, *args, **kwargs)

        socket.getaddrinfo = _patched
        return True
    except ImportError:
        return False  # dnspython nicht installiert → kein Patch

_DNS_PATCHED = _apply_dns_patch()


# ── Märkte laden ──────────────────────────────────────────────────────────────

def get_markets(limit: int = 50, active_only: bool = True) -> pd.DataFrame:
    """Lädt aktive Märkte von der Polymarket Gamma-API.

    Nutzt Cloudflare DNS (1.1.1.1) um den Schweizer ISP-Block zu umgehen.
    Fallback auf Demo-Daten wenn API nicht erreichbar.
    """
    params = {
        "limit":    limit,
        "active":   str(active_only).lower(),
        "closed":   "false",
        "archived": "false",
    }

    last_exc = None
    for base in ENDPOINTS:
        try:
            response = requests.get(f"{base}/markets", params=params, timeout=8)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                data = data.get("results", data.get("data", []))

            rows = []
            for market in data:
                # Wahrscheinlichkeit: outcomePrices[0] (Yes-Preis) bevorzugt
                prob = None
                outcome_prices = market.get("outcomePrices")
                if outcome_prices:
                    try:
                        prices = outcome_prices if isinstance(outcome_prices, list) \
                                 else __import__('json').loads(outcome_prices)
                        prob = float(prices[0])
                    except (ValueError, TypeError, IndexError):
                        prob = None

                if prob is None:
                    best_ask = market.get("bestAsk")
                    best_bid = market.get("bestBid")
                    if best_ask is not None and best_bid is not None:
                        try:
                            prob = (float(best_ask) + float(best_bid)) / 2
                        except (ValueError, TypeError):
                            prob = None

                # clobTokenId für Preis-History
                clob_ids = market.get("clobTokenIds", "[]")
                if isinstance(clob_ids, str):
                    import json as _json
                    try: clob_ids = _json.loads(clob_ids)
                    except: clob_ids = []
                clob_token_id = clob_ids[0] if clob_ids else None

                rows.append({
                    "id":             market.get("conditionId") or market.get("id"),
                    "clob_token_id":  clob_token_id,
                    "question":       market.get("question", ""),
                    "category":       market.get("category", ""),
                    "probability":    prob,
                    "volume":         market.get("volumeNum") or market.get("volume"),
                    "end_date":       market.get("endDate"),
                    "url":            f"https://polymarket.com/event/{market.get('slug', '')}",
                })

            df = pd.DataFrame(rows)
            df = df[df["probability"].notna()]
            return df

        except Exception as exc:
            last_exc = exc
            continue

    raise ConnectionError(f"Polymarket API nicht erreichbar: {last_exc}")


# ── Historische Preise ────────────────────────────────────────────────────────

def get_price_history(clob_token_id: str, days: int = 30) -> pd.DataFrame:
    """Historische Tagespreise eines Marktes vom Polymarket CLOB API.

    Parameters
    ----------
    clob_token_id : Polymarket CLOB token/asset id (aus get_markets()["clob_token_id"]).
                    Die CLOB prices-history API erwartet die Asset ID, nicht die conditionId.
    days          : Anzahl vergangener Tage (Standard: 30)

    Returns
    -------
    DataFrame mit Spalten 'date' (datetime.date) und 'price' (float 0..1).
    Leerer DataFrame wenn API nicht erreichbar.
    """
    end_ts   = int(_time.time())
    start_ts = end_ts - days * 86400

    url    = "https://clob.polymarket.com/prices-history"
    params = {
        "market":   clob_token_id,
        "startTs":  start_ts,
        "endTs":    end_ts,
        "interval": "1d",
        "fidelity": 100,
    }

    try:
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()

        history = data.get("history", data) if isinstance(data, dict) else data
        if not history:
            return pd.DataFrame(columns=["date", "price"])

        df = pd.DataFrame(history)
        if "t" not in df.columns or "p" not in df.columns:
            return pd.DataFrame(columns=["date", "price"])

        df["date"]  = pd.to_datetime(df["t"], unit="s", utc=True).dt.date
        df["price"] = df["p"].astype(float)
        return df[["date", "price"]].sort_values("date").reset_index(drop=True)

    except Exception:
        return pd.DataFrame(columns=["date", "price"])
