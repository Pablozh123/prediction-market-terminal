"""Claim and caveat framework over the versioned register data/claims.yaml.

The register holds three blocks: named ``disclaimers`` (de/en short texts
shown next to scores), ``allowed_claims`` (each with evidence pointer and a
last-verified date), and ``forbidden_phrases`` (language that must never
appear in product copy; enforced by scripts/lint_claims.py).

UI code never hardcodes caveat language: it asks ``disclaimer(key, lang)``
and builds score meta-lines through ``scoreline_view`` so every number is
shown with n, CI, sample-quality badge and snapshot timestamp in one
consistent shape. Streamlit-free, like the rest of ``app/``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.format import snapshot_label

CLAIMS_PATH = Path("data/claims.yaml")

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

QUALITY_BADGES = {
    "insufficient": "INSUFFICIENT SAMPLE",
    "developing": "DEVELOPING SAMPLE",
    "adequate": "ADEQUATE SAMPLE",
}


def load_claims(path: str | Path = CLAIMS_PATH) -> dict[str, Any]:
    """Parsed claims register; cached per file modification time."""

    resolved = Path(path)
    key = str(resolved)
    try:
        mtime = resolved.stat().st_mtime
    except OSError:
        return {}
    hit = _CACHE.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    with open(resolved, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        data = {}
    _CACHE[key] = (mtime, data)
    return data


def disclaimer(key: str, lang: str = "de", path: str | Path = CLAIMS_PATH) -> str:
    """Named short disclaimer in the requested language (falls back to the other)."""

    entry = (load_claims(path).get("disclaimers") or {}).get(key) or {}
    if not isinstance(entry, dict):
        return str(entry or "")
    text = entry.get(lang)
    if text:
        return str(text)
    for fallback in entry.values():
        if fallback:
            return str(fallback)
    return ""


def forbidden_rules(path: str | Path = CLAIMS_PATH
                    ) -> list[tuple[str, str, tuple[str, ...]]]:
    """(phrase, reason, allowed longer phrases) for every registered rule.

    The third element exists because some banned wordings are a prefix of a
    legitimate technical term. Forbidding a promise that risk is absent is
    right for a product that must never promise a sure thing, and wrong for
    the reference rate in a Sharpe ratio, which is spelled the same way.
    Narrowing the phrase itself would be the worse fix: the same words in
    front of "profit" would then stop being caught, and that is exactly what
    the rule exists for.
    """
    rows = load_claims(path).get("forbidden_phrases") or []
    out: list[tuple[str, str, tuple[str, ...]]] = []
    for row in rows:
        if isinstance(row, dict) and str(row.get("phrase", "")).strip():
            allowed = row.get("allow") or []
            if isinstance(allowed, str):
                allowed = [allowed]
            out.append((str(row["phrase"]), str(row.get("reason", "")),
                        tuple(str(item) for item in allowed)))
    return out


def forbidden_phrases(path: str | Path = CLAIMS_PATH) -> list[tuple[str, str]]:
    """(phrase, reason) for every registered rule, without the allowances."""
    return [(phrase, reason) for phrase, reason, _ in forbidden_rules(path)]


def find_forbidden_lines(text: str, path: str | Path = CLAIMS_PATH
                         ) -> list[tuple[int, str, str]]:
    """(line number, phrase, reason) for every violation in ``text``.

    This is the single matcher. The command-line linter reports line numbers
    and callers in the app do not, but both must agree on what counts as a
    violation: two implementations would mean an allowance registered in
    data/claims.yaml silently applies in one place and not the other.

    Case-insensitive and same-line only, so a phrase broken across a line
    break is not a match and every report points at an exact reviewable line.
    """

    hits: list[tuple[int, str, str]] = []
    rules = forbidden_rules(path)
    for number, line in enumerate(str(text or "").splitlines() or [""], start=1):
        lowered = line.lower()
        for phrase, reason, allowed in rules:
            haystack = lowered
            for permitted in allowed:
                haystack = haystack.replace(permitted.lower(), " ")
            if phrase.lower() in haystack:
                hits.append((number, phrase, reason))
    return hits


def find_forbidden(text: str, path: str | Path = CLAIMS_PATH) -> list[tuple[str, str]]:
    """Forbidden phrases found in ``text``, without line numbers."""
    return [(phrase, reason) for _, phrase, reason in find_forbidden_lines(text, path)]


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def stale_claims(max_age_days: int = 30, today: date | None = None, path: str | Path = CLAIMS_PATH) -> list[dict[str, Any]]:
    """Allowed claims whose last verification is older than ``max_age_days``.

    A claim without a parseable ``last_verified`` date counts as stale — an
    unverifiable verification date is exactly what the register exists to
    prevent.
    """

    today = today or datetime.now(timezone.utc).date()
    stale: list[dict[str, Any]] = []
    for row in load_claims(path).get("allowed_claims") or []:
        if not isinstance(row, dict):
            continue
        verified = _as_date(row.get("last_verified"))
        if verified is None or (today - verified).days > int(max_age_days):
            stale.append(
                {
                    "id": str(row.get("id", "")),
                    "last_verified": row.get("last_verified"),
                    "age_days": None if verified is None else (today - verified).days,
                }
            )
    return stale


def scoreline_view(
    *,
    n: int | None = None,
    ci: str | None = None,
    quality: str | None = None,
    verdict: str | None = None,
    disclaimer_key: str | None = None,
    snapshot_at: Any = None,
    lang: str = "en",
    path: str | Path = CLAIMS_PATH,
) -> dict[str, str]:
    """Text parts for one score line: meta (n, CI, snapshot), badge, note.

    The insufficient-sample rule lives here, once: with ``quality ==
    "insufficient"`` the note replaces any verdict language with the
    thin-sample disclaimer — the number itself stays visible.
    """

    meta_parts: list[str] = []
    if n is not None:
        meta_parts.append(f"n={int(n):,}")
    if ci:
        meta_parts.append(f"95% CI {ci}")
    if snapshot_at is not None:
        label = snapshot_label(snapshot_at)
        if label != "-":
            meta_parts.append(f"snapshot {label}")

    quality_key = str(quality or "").strip().lower()
    badge = QUALITY_BADGES.get(quality_key, "")

    note_parts: list[str] = []
    if quality_key == "insufficient":
        note_parts.append(disclaimer("thin_sample", lang, path))
    elif verdict:
        note_parts.append(str(verdict))
    if disclaimer_key:
        text = disclaimer(disclaimer_key, lang, path)
        if text and text not in note_parts:
            note_parts.append(text)

    return {
        "meta": " · ".join(part for part in meta_parts if part),
        "badge": badge,
        "note": " ".join(part for part in note_parts if part),
    }
