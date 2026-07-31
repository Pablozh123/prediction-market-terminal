"""Is the streamed book actually right? On Polymarket, nothing else can say.

Every study in this repo that uses stream data rests on one unverified
assumption: that the book we assembled from a snapshot plus deltas still
matches the exchange. On Kalshi a sequence number would catch a lost message.
Polymarket sends no sequence numbers at all, so a dropped or misapplied update
is invisible - the book simply drifts, quietly, and every spread, mid and
imbalance computed from it is wrong in a way no test and no error log reveals.

This module closes that hole the only way the protocol allows: it periodically
pulls the REST book, which is authoritative, and compares it against the
streamed state. The comparison is cheap - Polymarket's book endpoint allows
1,500 requests per ten seconds, orders of magnitude more than a sampling
reconciler needs.

It records a divergence time series rather than asserting. A single mismatch
proves nothing: the two observations are taken microseconds apart and a fast
book legitimately moves between them. What matters is the shape over time -
whether divergence is rare and transient, or persistent and growing. Only the
second is a bug, and only a series can tell them apart.

Read-only research tooling: public endpoints, no order path, no credentials.

Usage:
  python -m src.book_reconcile --tokens 12 --rounds 5 --tag live
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

from src import book_recorder as rec
from src import book_stream as bs

REPO_ROOT = Path(__file__).resolve().parents[1]
MICRO_DIR = REPO_ROOT / "data" / "microstructure"
RESEARCH_DIR = REPO_ROOT / "docs" / "research"

CLOB_BOOK_URL = "https://clob.polymarket.com/book"
HEADERS = {"User-Agent": "prediction-market-terminal reconciler/1.0 (read-only)"}

#: Ab hier gilt ein Unterschied als echt und nicht als Zeitversatz zwischen
#: den beiden Beobachtungen. Ein Tick ist 0.001.
TICK = 0.001
TOLERANCE_TICKS = 1.0

RECONCILE_FIELDS = [
    "ts_utc", "token_id", "stream_bid", "rest_bid", "stream_ask", "rest_ask",
    "bid_diff_ticks", "ask_diff_ticks", "verdict", "stream_age_s",
]


@dataclass(frozen=True, slots=True)
class Comparison:
    """One streamed book against one REST book at nearly the same instant."""

    token_id: str
    stream_bid: float | None
    stream_ask: float | None
    rest_bid: float | None
    rest_ask: float | None
    stream_age_s: float

    @property
    def bid_diff_ticks(self) -> float | None:
        if self.stream_bid is None or self.rest_bid is None:
            return None
        return round(abs(self.stream_bid - self.rest_bid) / TICK, 2)

    @property
    def ask_diff_ticks(self) -> float | None:
        if self.stream_ask is None or self.rest_ask is None:
            return None
        return round(abs(self.stream_ask - self.rest_ask) / TICK, 2)

    def verdict(self, tolerance: float = TOLERANCE_TICKS) -> str:
        """match, drift, or a named reason why no comparison was possible."""
        if self.stream_bid is None and self.stream_ask is None:
            return "kein Stream-Buch"
        if self.rest_bid is None and self.rest_ask is None:
            return "kein REST-Buch"
        diffs = [d for d in (self.bid_diff_ticks, self.ask_diff_ticks)
                 if d is not None]
        if not diffs:
            return "eine Seite fehlt"
        return "match" if max(diffs) <= tolerance else "drift"

    def as_row(self, ts_utc: str, tolerance: float = TOLERANCE_TICKS) -> dict:
        return {
            "ts_utc": ts_utc,
            "token_id": self.token_id,
            "stream_bid": self.stream_bid,
            "rest_bid": self.rest_bid,
            "stream_ask": self.stream_ask,
            "rest_ask": self.rest_ask,
            "bid_diff_ticks": self.bid_diff_ticks,
            "ask_diff_ticks": self.ask_diff_ticks,
            "verdict": self.verdict(tolerance),
            "stream_age_s": round(self.stream_age_s, 3),
        }


def _get_json(url: str, params: dict | None = None, timeout: int = 20):
    resp = requests.get(url, params=params or {}, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def rest_touch(payload: dict) -> tuple[float | None, float | None]:
    """(best bid, best ask) from a REST book, sorted explicitly.

    The venue's own OpenAPI spec and its prose page disagree about level
    ordering, so nothing here relies on the order they arrive in.
    """
    def best(levels, pick):
        prices = []
        for level in levels or []:
            try:
                prices.append(float(level["price"] if isinstance(level, dict)
                                    else level[0]))
            except (TypeError, ValueError, KeyError, IndexError):
                continue
        return pick(prices) if prices else None

    book = payload or {}
    return best(book.get("bids"), max), best(book.get("asks"), min)


def compare(token_id: str, stream_state: bs.StreamState, rest_payload: dict,
            stream_age_s: float = 0.0) -> Comparison:
    """One streamed book against the authoritative REST book."""
    book = stream_state.books.get(token_id)
    rest_bid, rest_ask = rest_touch(rest_payload)
    return Comparison(
        token_id=token_id,
        stream_bid=book.best_bid() if book else None,
        stream_ask=book.best_ask() if book else None,
        rest_bid=rest_bid, rest_ask=rest_ask,
        stream_age_s=stream_age_s)


def summarise(rows: list[dict]) -> dict:
    """Shape of the divergence, which is the whole point of the series."""
    total = len(rows)
    if not total:
        return {"comparisons": 0, "match": 0, "drift": 0, "match_rate": None,
                "max_diff_ticks": None, "unusable": 0}
    verdicts = [r["verdict"] for r in rows]
    diffs = [max(d for d in (r["bid_diff_ticks"], r["ask_diff_ticks"])
                 if d is not None)
             for r in rows
             if r["bid_diff_ticks"] is not None or r["ask_diff_ticks"] is not None]
    usable = sum(1 for v in verdicts if v in ("match", "drift"))
    return {
        "comparisons": total,
        "match": verdicts.count("match"),
        "drift": verdicts.count("drift"),
        "unusable": total - usable,
        "match_rate": round(verdicts.count("match") / usable, 4) if usable else None,
        "max_diff_ticks": round(max(diffs), 2) if diffs else None,
        "mean_diff_ticks": round(sum(diffs) / len(diffs), 3) if diffs else None,
    }


def run_round(token_ids: list[str], stream_state: bs.StreamState,
              get_json=_get_json, tolerance: float = TOLERANCE_TICKS,
              now: datetime | None = None) -> list[dict]:
    """Pull REST for each token and compare against the current stream state."""
    ts = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[dict] = []
    for token_id in token_ids:
        try:
            payload = get_json(CLOB_BOOK_URL, {"token_id": token_id})
        except Exception:  # noqa: BLE001 - ein Abruf darf die Runde nicht kippen
            continue
        rows.append(compare(token_id, stream_state, payload).as_row(ts, tolerance))
    return rows


def run_study(token_count: int = 12, rounds: int = 5, seconds_per_round: float = 45.0,
              out_dir: Path = MICRO_DIR, ws_factory=bs._default_ws_factory,
              get_json=_get_json, rest_get_json=None,
              tolerance: float = TOLERANCE_TICKS) -> dict:
    """Stream for a while, then compare against REST. Repeat.

    Each round streams first so the local book has something to be wrong
    about, then reconciles. A round that never connects contributes nothing
    rather than a false match.
    """
    rest_get_json = rest_get_json or get_json
    tokens = [t["token_id"] for t in
              bs.select_stream_tokens(get_json=get_json, top_n=token_count)]
    tokens = tokens[:token_count]
    all_rows: list[dict] = []
    connected_rounds = 0
    for _ in range(max(1, rounds)):
        state = bs.StreamState()
        summary = _stream_into(state, tokens, seconds_per_round, ws_factory)
        if not summary.get("connected"):
            continue
        connected_rounds += 1
        all_rows.extend(run_round(tokens, state, get_json=rest_get_json,
                                  tolerance=tolerance))
    return {
        "tokens": len(tokens),
        "rounds_requested": rounds,
        "rounds_connected": connected_rounds,
        "seconds_per_round": seconds_per_round,
        "tolerance_ticks": tolerance,
        "summary": summarise(all_rows),
        "rows": all_rows,
    }


def _stream_into(state: bs.StreamState, tokens: list[str], seconds: float,
                 ws_factory) -> dict:
    """Fill ``state`` from the socket for ``seconds``. Never raises."""
    import json as _json

    try:
        socket = ws_factory(bs.WS_URL)
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "error": f"{type(exc).__name__}: {exc}"}
    deadline = time.monotonic() + float(seconds)
    try:
        socket.send(_json.dumps(bs.subscribe_message(tokens)))
        while time.monotonic() < deadline:
            try:
                raw = socket.recv()
            except Exception:  # noqa: BLE001 - Timeout ist der Normalfall
                continue
            for event in bs.parse_payload(raw):
                state.handle(event, bs.utc_now_iso())
    finally:
        try:
            socket.close()
        except Exception:  # noqa: BLE001
            pass
    return {"connected": True}


def append_rows(out_dir: Path, rows: list[dict],
                now: datetime | None = None) -> None:
    day = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    rec.append_csv(Path(out_dir) / f"reconcile_{day}.csv", RECONCILE_FIELDS, rows)


def _fmt(value, spec="{:.2f}") -> str:
    return "-" if value is None else spec.format(value)


def _markdown(results: dict, tag: str) -> str:
    s = results["summary"]
    lines = [
        f"# Buch-Abgleich Stream gegen REST ({tag})",
        "",
        f"{results['tokens']} Tokens, {results['rounds_connected']} von "
        f"{results['rounds_requested']} Runden verbunden, "
        f"{results['seconds_per_round']:.0f} Sekunden Stream je Runde, "
        f"Toleranz {results['tolerance_ticks']:.0f} Tick.",
        "",
        f"Vergleiche {s['comparisons']}, davon uebereinstimmend {s['match']}, "
        f"abweichend {s['drift']}, nicht vergleichbar {s['unusable']}. "
        f"Uebereinstimmungsquote {_fmt(s['match_rate'], '{:.1%}')}, "
        f"groesste Abweichung {_fmt(s['max_diff_ticks'], '{:.1f}')} Ticks, "
        f"mittlere {_fmt(s.get('mean_diff_ticks'), '{:.2f}')} Ticks.",
        "",
        "## Warum das noetig ist",
        "",
        "Polymarket sendet keine Sequenznummern. Auf Kalshi verraet eine Luecke "
        "im Zaehler, dass eine Nachricht verloren ging; auf Polymarket gibt es "
        "diesen Zaehler nicht. Ein verlorenes oder falsch angewendetes Update "
        "ist damit unsichtbar - das Buch driftet lautlos, und jeder Spread, "
        "jeder Mid und jede Imbalance daraus ist falsch, ohne dass ein Test "
        "oder ein Log das zeigt. Der Abgleich gegen das REST-Buch ist der "
        "einzige Weg, den das Protokoll offen laesst.",
        "",
        "## Lesehilfe",
        "",
        "Eine einzelne Abweichung beweist nichts: die beiden Beobachtungen "
        "liegen Millisekunden auseinander, und ein schnelles Buch bewegt sich "
        "in dieser Zeit voellig zu Recht. Aussagekraeftig ist die Form ueber "
        "die Zeit - ob Abweichung selten und voruebergehend ist oder haeufig "
        "und wachsend. Nur das Zweite ist ein Fehler, und nur eine Zeitreihe "
        "kann die beiden auseinanderhalten. Deshalb schreibt dieses Modul eine "
        "Reihe und behauptet nichts.",
        "",
        "Read-only-Forschung, keine Handelsempfehlung.",
    ]
    return "\n".join(lines)


def write_outputs(results: dict, tag: str,
                  research_dir: Path = RESEARCH_DIR) -> dict[str, Path]:
    research_dir.mkdir(parents=True, exist_ok=True)
    json_path = research_dir / f"book_reconcile_{tag}.json"
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    csv_path = research_dir / f"book_reconcile_{tag}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RECONCILE_FIELDS)
        writer.writeheader()
        for row in results["rows"]:
            writer.writerow({k: row.get(k) for k in RECONCILE_FIELDS})
    md_path = research_dir / f"book_reconcile_{tag}.md"
    md_path.write_text(_markdown(results, tag), encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "md": md_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True)
    parser.add_argument("--tokens", type=int, default=12)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--seconds", type=float, default=45.0)
    args = parser.parse_args(argv)

    results = run_study(token_count=args.tokens, rounds=args.rounds,
                        seconds_per_round=args.seconds)
    append_rows(MICRO_DIR, results["rows"])
    paths = write_outputs(results, args.tag)
    print({k: v for k, v in results.items() if k != "rows"})
    print({key: str(path) for key, path in paths.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
