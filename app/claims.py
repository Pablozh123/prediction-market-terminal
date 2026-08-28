"""Claim and caveat framework over the versioned register data/claims.yaml.

The register holds four blocks: named ``disclaimers`` (de/en short texts
shown next to scores, each naming the surfaces that must render it),
``allowed_claims`` (each with evidence pointer and a last-verified date),
``forbidden_phrases`` (language that must never appear in product copy) and
``caveat_markers`` (wording that marks a standing caveat, so a disclaimer
written by hand into a surface is found). The last two are enforced by
scripts/lint_claims.py.

UI code never hardcodes caveat language: it asks ``disclaimer(key, lang)``
and builds score meta-lines through ``scoreline_view`` so every number is
shown with n, CI, sample-quality badge and snapshot timestamp in one
consistent shape. Streamlit-free, like the rest of ``app/``.

The web frontend reads the same register rather than a copy of its wording:
``ui_register`` shapes it for /api/claims (api_views.claims_payload), and
scripts/publish_claims.py compiles it into web/js/claims_register.js so a
page can render its caveat before any request is made. Both are checked
against this file by the lint, so neither can drift.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.format import snapshot_label

#: Anchored at the repository, not at the working directory: the register is
#: read by the API process, which is started from wherever the host feels
#: like. A relative default returned an empty caveat there, and an empty
#: caveat is the failure this module exists to prevent.
CLAIMS_PATH = Path(__file__).resolve().parents[1] / "data" / "claims.yaml"

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


#: Language keys inside a disclaimer entry. Everything else in the entry is
#: metadata (``surfaces``), not text, and must never be returned as a caveat.
LANGS = ("de", "en")


def disclaimer(key: str, lang: str = "de", path: str | Path = CLAIMS_PATH) -> str:
    """Named short disclaimer in the requested language (falls back to the other)."""

    entry = (load_claims(path).get("disclaimers") or {}).get(key) or {}
    if not isinstance(entry, dict):
        return str(entry or "")
    text = entry.get(lang)
    if text:
        return str(text)
    for other in LANGS:
        fallback = entry.get(other)
        if fallback:
            return str(fallback)
    return ""


def disclaimer_keys(path: str | Path = CLAIMS_PATH) -> list[str]:
    """Every registered disclaimer key, in register order."""

    block = load_claims(path).get("disclaimers") or {}
    return [str(key) for key in block] if isinstance(block, dict) else []


def surfaces(key: str, path: str | Path = CLAIMS_PATH) -> tuple[str, ...]:
    """Files that must render this disclaimer, as declared in the register."""

    entry = (load_claims(path).get("disclaimers") or {}).get(key) or {}
    if not isinstance(entry, dict):
        return ()
    declared = entry.get("surfaces") or []
    if isinstance(declared, str):
        declared = [declared]
    return tuple(str(item).strip() for item in declared if str(item).strip())


def surface_map(path: str | Path = CLAIMS_PATH) -> dict[str, list[str]]:
    """{file: [disclaimer keys it must render]} over the whole register.

    This is the half of the register that was missing: it not only forbids
    wording, it names where each caveat has to appear. Without it an entry
    can stop being rendered and nothing notices — which is exactly how
    leaderboard_caveat, wallet_reader_caveat, screen_not_proof and
    backtest_modeled ended up with no reader at all.
    """

    out: dict[str, list[str]] = {}
    for key in disclaimer_keys(path):
        for surface in surfaces(key, path):
            out.setdefault(surface, []).append(key)
    return out


def ui_register(lang: str | None = None, path: str | Path = CLAIMS_PATH) -> dict[str, Any]:
    """The register in the shape a UI consumes: texts plus their surfaces.

    ``lang`` None keeps both languages (what /api/claims and the compiled
    frontend module carry, so a client can switch without a second request);
    a language code reduces each entry to that text with the usual fallback.
    ``forbidden_phrases`` stays out: it governs authoring, not display.
    """

    data = load_claims(path)
    entries: dict[str, Any] = {}
    for key in disclaimer_keys(path):
        row: dict[str, Any]
        if lang:
            row = {"text": disclaimer(key, lang, path)}
        else:
            row = {code: disclaimer(key, code, path) for code in LANGS if disclaimer(key, code, path)}
        declared = surfaces(key, path)
        if declared:
            row["surfaces"] = list(declared)
        entries[key] = row
    claims_out = []
    for row in data.get("allowed_claims") or []:
        if not isinstance(row, dict):
            continue
        claims_out.append({
            "id": str(row.get("id", "")),
            "text": str(row.get("text", "")),
            "evidence": str(row.get("evidence", "")),
            "last_verified": str(row.get("last_verified", "")),
        })
    return {
        "version": int(data.get("version") or 0),
        "updated": str(data.get("updated") or ""),
        "lang": str(lang or ""),
        "disclaimers": entries,
        "allowed_claims": claims_out,
    }


def caveat_marker_rules(path: str | Path = CLAIMS_PATH
                        ) -> list[tuple[str, tuple[str, ...]]]:
    """(marker, allowed longer phrases) for every registered caveat marker.

    Same allowance mechanism as the forbidden rules, and for the same reason:
    a marker broad enough to catch a hand-written disclaimer will sometimes
    sit inside method prose about one measurement. That exception is a
    register entry with a reason, not a hidden exclusion in the linter.
    """

    rows = load_claims(path).get("caveat_markers") or []
    out: list[tuple[str, tuple[str, ...]]] = []
    for row in rows:
        if isinstance(row, str):
            out.append((row, ()))
            continue
        if isinstance(row, dict) and str(row.get("marker", "")).strip():
            allowed = row.get("allow") or []
            if isinstance(allowed, str):
                allowed = [allowed]
            out.append((str(row["marker"]), tuple(str(item) for item in allowed)))
    return out


def registered_texts(path: str | Path = CLAIMS_PATH) -> tuple[str, ...]:
    """Every disclaimer text in the register, both languages."""

    out: list[str] = []
    for key in disclaimer_keys(path):
        for code in LANGS:
            text = disclaimer(key, code, path)
            if text:
                out.append(text)
    return tuple(out)


def find_unregistered_caveats(text: str, path: str | Path = CLAIMS_PATH
                              ) -> list[tuple[int, str, str]]:
    """(line number, marker, line excerpt) for hand-written caveats in ``text``.

    A line counts as a hand-written caveat when it carries registered caveat
    wording without being a registered text itself. Registered texts pass so
    the compiled register module and any file quoting an entry verbatim stay
    clean; everything else is a disclaimer that no review ever saw.
    """

    known = registered_texts(path)
    rules = caveat_marker_rules(path)
    hits: list[tuple[int, str, str]] = []
    for number, line in enumerate(str(text or "").splitlines() or [""], start=1):
        haystack = line.lower()
        for permitted in (allowed for _, allowances in rules for allowed in allowances):
            haystack = haystack.replace(permitted.lower(), " ")
        for registered in known:
            haystack = haystack.replace(registered.lower(), " ")
        for marker, _allowed in rules:
            if marker.lower() in haystack:
                hits.append((number, marker, line.strip()[:160]))
    return hits


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


#: Path of the compiled register the browser imports, repo-anchored like the
#: register itself.
FRONTEND_MODULE_REL = "web/js/claims_register.js"
FRONTEND_MODULE_PATH = Path(__file__).resolve().parents[1] / "web" / "js" / "claims_register.js"

_MODULE_HEADER = """// GENERATED FILE. Do not edit, and do not write caveat wording here.
//
// Source of record: data/claims.yaml. Regenerate with
//
//     python scripts/publish_claims.py
//
// and scripts/lint_claims.py fails when this file and the register disagree.
//
// The register is compiled into the bundle rather than fetched because a
// caveat that arrives with a response is a caveat that is missing while the
// response is on its way, and absent entirely on a static file host with no
// API behind it. web/js/claims.js reads this object and merges a newer
// register from /api/claims when one answers.

export const REGISTER = """


def frontend_register(path: str | Path = CLAIMS_PATH) -> dict[str, Any]:
    """The subset of the register the browser needs: version, date, texts."""

    data = load_claims(path)
    entries: dict[str, dict[str, str]] = {}
    for key in disclaimer_keys(path):
        texts = {code: disclaimer(key, code, path) for code in LANGS if disclaimer(key, code, path)}
        if texts:
            entries[key] = texts
    return {
        "version": int(data.get("version") or 0),
        "updated": str(data.get("updated") or ""),
        "disclaimers": entries,
    }


def frontend_module_source(path: str | Path = CLAIMS_PATH) -> str:
    """Full text of web/js/claims_register.js for the current register."""

    body = json.dumps(frontend_register(path), indent=2, ensure_ascii=False, sort_keys=False)
    return _MODULE_HEADER + body + ";\n"


def parse_frontend_module(text: str) -> dict[str, Any] | None:
    """The register object out of a compiled module, or None when unreadable."""

    marker = "export const REGISTER = "
    start = str(text or "").find(marker)
    if start < 0:
        return None
    body = text[start + len(marker):].strip()
    if body.endswith(";"):
        body = body[:-1]
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


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
