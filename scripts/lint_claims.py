"""Copy linter for the claim register (Brief 03).

Four checks, all against data/claims.yaml, all failing with exit 1:

1. **Forbidden phrases.** A registered ban appears in a text source.
2. **Unregistered disclaimers.** A surface writes a standing caveat by hand
   instead of rendering a register entry. A register that only forbids
   wording but does not supply it is half a register: every hand-written
   disclaimer is copy that no review ever checked against the rules.
3. **Entries that stopped being shown.** Every disclaimer that names its
   `surfaces` must actually be rendered there, and every caveat('<key>')
   must name an entry that exists. This is the check that would have caught
   the state this file was written in: four entries, no reader anywhere.
4. **Drift in the compiled register.** web/js/claims_register.js is
   generated from data/claims.yaml (scripts/publish_claims.py); a register
   change that was not recompiled would ship a page whose caveats are one
   revision behind.

Additionally warns (exit 0) about allowed claims whose last verification is
older than 30 days.

Run:
    python scripts/lint_claims.py                 # lint the default sources
    python scripts/lint_claims.py --paths X.md    # lint specific files/globs
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import claims

# Text sources the register governs. tests/ is exempt on purpose (test strings
# must be able to quote violations), as are the files that define the list.
LINT_SOURCES = (
    "prediction_terminal.py",
    "app/*.py",
    "docs/specs/**/*.md",
    "README.md",
    # The control-room frontend is the surface that goes public, so its copy is
    # exactly what the register exists to govern. Linting only the Streamlit app
    # would leave the published wording unchecked.
    "web/index.html",
    "web/js/**/*.js",
)

# Where a caveat must come from the register rather than from prose. This is
# the published web frontend plus the API payloads it and every other client
# read. prediction_terminal.py is deliberately not in here yet: the Streamlit
# monolith carries its own disclaimers and migrating them is its own change,
# not a side effect of this one. Adding it later is one line, and the check
# will then have something to say about roughly eight places.
CAVEAT_SOURCES = (
    "web/index.html",
    "web/js/**/*.js",
    "app/api_views.py",
)

# Files that define or quote the forbidden list itself.
EXCLUDED = {
    Path("data/claims.yaml"),
    Path("docs/specs/p0/03_caveat_framework.md"),
}

# The compiled register carries every registered text by definition; it is
# checked for drift instead (check 4).
CAVEAT_EXCLUDED = {Path(claims.FRONTEND_MODULE_REL)}

STALE_MAX_AGE_DAYS = 30


def collect_files(patterns: list[str] | tuple[str, ...], excluded: set[Path] | None = None) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    skip = EXCLUDED if excluded is None else excluded
    for pattern in patterns:
        for match in sorted(glob.glob(pattern, recursive=True)):
            path = Path(match)
            if not path.is_file():
                continue
            normalized = Path(path.as_posix())
            if normalized in skip or normalized in seen:
                continue
            seen.add(normalized)
            files.append(path)
    return files


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"warning: could not read {path}: {exc}", file=sys.stderr)
        return None


def lint_file(path: Path) -> list[tuple[int, str, str]]:
    """Violations in one file, matched by app.claims so the rules stay single-source."""
    text = _read(path)
    return [] if text is None else claims.find_forbidden_lines(text)


def lint_caveats(paths: list[Path]) -> tuple[list[str], dict[str, set[str]]]:
    """Hand-written caveats plus, per file, the register keys it renders."""

    findings: list[str] = []
    rendered: dict[str, set[str]] = {}
    known = set(claims.disclaimer_keys())
    for path in paths:
        text = _read(path)
        if text is None:
            continue
        name = path.as_posix()
        for line_number, marker, excerpt in claims.find_unregistered_caveats(text):
            findings.append(
                f"{name}:{line_number}: hand-written caveat ('{marker}'): put the sentence in "
                f"data/claims.yaml and render it with caveat('<key>'): {excerpt}"
            )
        for line_number, key in claims.caveat_calls(text):
            rendered.setdefault(name, set()).add(key)
            if key not in known:
                findings.append(
                    f"{name}:{line_number}: caveat('{key}') is not in data/claims.yaml"
                )
    return findings, rendered


def lint_surfaces(rendered: dict[str, set[str]]) -> list[str]:
    """Register entries whose declared surface does not render them."""

    findings: list[str] = []
    for surface, keys in sorted(claims.surface_map().items()):
        gezeigt = rendered.get(surface)
        if gezeigt is None:
            findings.append(
                f"data/claims.yaml: {surface} is named as a surface but is not among the linted "
                "sources (CAVEAT_SOURCES in scripts/lint_claims.py)"
            )
            continue
        for key in keys:
            if key not in gezeigt:
                findings.append(
                    f"data/claims.yaml: disclaimer '{key}' names {surface} as its surface, "
                    f"but that file never calls caveat('{key}')"
                )
    return findings


def lint_compiled_register() -> list[str]:
    """Drift between data/claims.yaml and the module the browser imports."""

    module = claims.FRONTEND_MODULE_PATH
    if not module.exists():
        return [f"{claims.FRONTEND_MODULE_REL} is missing: run python scripts/publish_claims.py"]
    if module.read_text(encoding="utf-8") != claims.frontend_module_source():
        return [f"{claims.FRONTEND_MODULE_REL} is out of date: run python scripts/publish_claims.py"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint text sources against data/claims.yaml.")
    parser.add_argument("--paths", nargs="*", default=None, help="Override the default source globs.")
    args = parser.parse_args()

    pairs = claims.forbidden_phrases()
    if not pairs:
        print("error: no forbidden phrases loaded from data/claims.yaml", file=sys.stderr)
        return 1

    patterns = args.paths if args.paths else list(LINT_SOURCES)
    files = collect_files(patterns)
    if not files:
        print("warning: no files matched the lint sources", file=sys.stderr)

    failed = False
    for path in files:
        for line_number, phrase, reason in lint_file(path):
            failed = True
            print(f"{path.as_posix()}:{line_number}: forbidden phrase '{phrase}': {reason}")

    # Die drei Registerpruefungen laufen nur ueber die eigenen Quellen; mit
    # --paths ist der Aufruf eine gezielte Textpruefung (so ruft der Test sie
    # auf) und kann ueber die Flaechenabdeckung nichts wissen.
    caveat_files: list[Path] = []
    if args.paths is None:
        caveat_files = collect_files(CAVEAT_SOURCES, excluded=EXCLUDED | CAVEAT_EXCLUDED)
        findings, rendered = lint_caveats(caveat_files)
        findings += lint_surfaces(rendered)
        findings += lint_compiled_register()
        for line in findings:
            failed = True
            print(line)

    for entry in claims.stale_claims(max_age_days=STALE_MAX_AGE_DAYS):
        age = entry["age_days"]
        age_text = f"{age} days old" if age is not None else "no parseable last_verified date"
        print(
            f"warning: claim '{entry['id']}' needs re-verification ({age_text}, max {STALE_MAX_AGE_DAYS})",
            file=sys.stderr,
        )

    if failed:
        return 1
    print(f"claims lint ok: {len(files)} files checked against {len(pairs)} forbidden phrases")
    if caveat_files:
        print(f"caveat check ok: {len(caveat_files)} surface files, "
              f"{len(claims.disclaimer_keys())} registered disclaimers, "
              f"{len(claims.surface_map())} files named as surfaces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
