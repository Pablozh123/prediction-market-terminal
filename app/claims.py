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


def forbidden_phrases(path: str | Path = CLAIMS_PATH) -> list[tuple[str, str]]:
    rows = load_claims(path).get("forbidden_phrases") or []
    pairs: list[tuple[str, str]] = []
    for row in rows:
        if isinstance(row, dict) and str(row.get("phrase", "")).strip():
            pairs.append((str(row["phrase"]), str(row.get("reason", ""))))
    return pairs


def find_forbidden(text: str, path: str | Path = CLAIMS_PATH) -> list[tuple[str, str]]:
    """Forbidden phrases found in ``text``: case-insensitive, same-line only.

    Deliberately simple: a phrase broken across a line break is not a match,
    so the linter reports exact, reviewable lines instead of fuzzy spans.
    """

    hits: list[tuple[str, str]] = []
    pairs = forbidden_phrases(path)
    for line in str(text or "").splitlines() or [""]:
        lowered = line.lower()
        for phrase, reason in pairs:
            if phrase.lower() in lowered:
                hits.append((phrase, reason))
    return hits


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
