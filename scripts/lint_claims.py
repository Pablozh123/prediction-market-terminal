"""Copy linter for the claim register (Brief 03).

Walks the defined text sources and fails (exit 1) when a forbidden phrase
from data/claims.yaml appears, printing file, line, phrase and reason.
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
)

# Files that define or quote the forbidden list itself.
EXCLUDED = {
    Path("data/claims.yaml"),
    Path("docs/specs/p0/03_caveat_framework.md"),
}

STALE_MAX_AGE_DAYS = 30


def collect_files(patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for match in sorted(glob.glob(pattern, recursive=True)):
            path = Path(match)
            if not path.is_file():
                continue
            normalized = Path(path.as_posix())
            if normalized in EXCLUDED or normalized in seen:
                continue
            seen.add(normalized)
            files.append(path)
    return files


def lint_file(path: Path, pairs: list[tuple[str, str]]) -> list[tuple[int, str, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"warning: could not read {path}: {exc}", file=sys.stderr)
        return []
    violations: list[tuple[int, str, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        for phrase, reason in pairs:
            if phrase.lower() in lowered:
                violations.append((line_number, phrase, reason))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint text sources against data/claims.yaml forbidden phrases.")
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
        for line_number, phrase, reason in lint_file(path, pairs):
            failed = True
            print(f"{path.as_posix()}:{line_number}: forbidden phrase '{phrase}' — {reason}")

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
