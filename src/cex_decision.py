"""Optional Jev shadow gate. Explicit CLI opt-in, public numeric features only.

The returned choice probability is not a calibrated probability of a profitable
trade. Network round-trip time is recorded and charged by the paper replay.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from pathlib import Path

import requests

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
PROMPT_VERSION = "cex-shadow-1"
FEATURES = {"cex_return_bps", "lookback_ms", "other_cex_return_bps", "ask", "bid", "book_age_ms",
            "seconds_to_close", "shares", "fee_rate", "holding_ms", "max_price_jump", "max_ask"}


def features_hash(features: dict) -> str:
    return hashlib.sha256(json.dumps(features, sort_keys=True, allow_nan=False,
                                     separators=(",", ":")).encode()).hexdigest()


def judge(features: dict, key: str, model: str = "jev-latest", session=None) -> dict:
    start = time.monotonic_ns()
    try:
        state = {name: value for name, value in features.items() if name in FEATURES}
        if any(value is not None and (type(value) not in (int, float) or
                                     not math.isfinite(value)) for value in state.values()):
            raise ValueError("Nonfinite or nonnumeric decision feature")
        # Exact comparisons and costs are computed outside the decision model.
        own, other = state.get("cex_return_bps"), state.get("other_cex_return_bps")
        state["cross_venue_alignment"] = ("unknown" if other is None or own is None else
                                          "aligned" if own * other > 0 else "opposed_or_flat")
        if state.get("ask") is not None and state.get("bid") is not None and state.get("fee_rate") is not None:
            ask, bid, rate = state["ask"], state["bid"], state["fee_rate"]
            state["immediate_roundtrip_loss_per_share"] = ask - bid + rate * (ask * (1-ask) + bid * (1-bid))
        body = {"state": state, "model": model, "questions": {"decision": {
            "type": "choice",
            "instructions": "Choose whether to retain this BTC impulse-following PAPER candidate. "
                            "Only the supplied past/current features are known. Do not assume a future return, "
                            "settlement outcome, profitable trade or an 85% win probability. All arithmetic, "
                            "position limits and execution checks run in code. Missing evidence favors skip.",
            "criteria": {"skip": "Insufficient or conflicting evidence that the CEX impulse will lead the "
                                   "prediction quote enough to overcome the measured round-trip loss.",
                         "enter": "The cross-venue evidence supports retaining this candidate for the "
                                    "paper experiment despite costs and reversal risk."}}}}
        transport = session or requests
        response = transport.post(ENDPOINT, headers={"Authorization": f"Bearer {key}"},
                                  json=body, timeout=(3, 10), allow_redirects=False)
        response.raise_for_status()
        if len(response.content) > 64_000:
            raise ValueError("Oversized decision response")
        data = response.json()
        answer = data["answers"]["decision"]
        probabilities = answer["probabilities"]
        if answer["choice"] not in {"enter", "skip"} or answer.get("type") != "choice":
            raise ValueError("Unknown choice or response type")
        if set(probabilities) != {"enter", "skip"}:
            raise ValueError("Unknown probability labels")
        for value in [answer["confidence"], *probabilities.values()]:
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Invalid choice probabilities")
        if abs(sum(probabilities.values()) - 1) > .02:
            raise ValueError("Probabilities do not sum to one")
        if probabilities[answer["choice"]] < max(probabilities.values()):
            raise ValueError("Choice disagrees with probabilities")
        resolved_model = data["model"]
        if not isinstance(resolved_model, str) or not 0 < len(resolved_model) <= 256:
            raise ValueError("Invalid model identity")
        usage = {name: data["usage"][name] for name in ("input_tokens", "output_tokens")}
        if any(type(value) is not int or value < 0 for value in usage.values()):
            raise ValueError("Invalid token usage")
        result = {"choice": answer["choice"], "confidence": answer["confidence"],
                  "probabilities": probabilities, "model": resolved_model, "usage": usage}
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError) as exc:
        result = {"choice": "abstain", "error": type(exc).__name__}
    return {**result, "latency_ms": (time.monotonic_ns() - start) / 1e6, "prompt_version": PROMPT_VERSION}


def load_decisions(path: Path, run: Path) -> dict:
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    decisions = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("events_sha256") != manifest.get("events_sha256"):
            raise ValueError("Decisions belong to a different capture")
        if row.get("prompt_version") != PROMPT_VERSION:
            raise ValueError("Decisions belong to a different prompt version")
        if row["signal_id"] in decisions:
            raise ValueError("Duplicate decision IDs")
        decisions[row["signal_id"]] = row
    return decisions


def score_run(run: Path, max_calls: int, model: str = "jev-latest") -> dict:
    if not 1 <= max_calls <= 1000:
        raise ValueError("max_calls must be between 1 and 1000")
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise ValueError("Set TYPESAFE_API_KEY to opt into billable Jev shadow calls")
    run = Path(run)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    path = run / "decisions.jsonl"
    cached = load_decisions(path, run) if path.exists() else {}
    calls, abstentions = 0, 0
    with requests.Session() as session, path.open("a", encoding="utf-8") as output:
        for line in (run / "decision_inputs.jsonl").read_text(encoding="utf-8").splitlines():
            signal = json.loads(line)
            if signal["signal_id"] in cached:
                continue
            result = judge(signal["features"], key, model, session)
            result.update(signal_id=signal["signal_id"], events_sha256=manifest["events_sha256"],
                          input_sha256=features_hash(signal["features"]), prompt_version=PROMPT_VERSION)
            output.write(json.dumps(result, allow_nan=False) + "\n")
            output.flush()
            calls += 1
            abstentions += result["choice"] == "abstain"
            if calls >= max_calls:
                break
    return {"path": str(path), "calls": calls, "abstentions": abstentions, "cached": len(cached)}
