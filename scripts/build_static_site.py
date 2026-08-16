#!/usr/bin/env python3
"""Build a self-contained static copy of the control-room frontend into dist/.

    python scripts/build_static_site.py            # -> dist/
    python scripts/build_static_site.py --out /tmp/site
    python -m http.server -d dist 8000             # look at it locally

The result is web/ plus the published research payloads under data/:

    dist/index.html
    dist/css/…
    dist/js/…
    dist/data/*.json        <- public/data/*.json

Hosted from any static file server (site root or a sub-path, since every
reference in web/ is relative) the RESEARCH pages work fully: web/js/api.js
tries the JSON API first, gets no answer, and falls back to ./data/<file>.json.
The live pages (markets, tape, wallets, risk, backtester) have no static
source and show their "waiting for API" empty state, which is the honest
outcome — no numbers are invented.

Idempotent: the output directory is rebuilt from scratch on every run, so
files removed from web/ or public/data/ disappear from dist/ as well.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "public" / "data"
DEFAULT_OUT = ROOT / "dist"

# Never copied, wherever they sit inside web/.
SKIP_NAMES = {"__pycache__", ".DS_Store", "Thumbs.db"}


def _skip(directory: str, names: list[str]) -> set[str]:
    return {n for n in names if n in SKIP_NAMES or n.startswith(".")}


def referenced_payloads(api_js: Path) -> list[str]:
    """File names the frontend expects under ./data/ (from the STATISCH table)."""

    if not api_js.exists():
        return []
    text = api_js.read_text(encoding="utf-8")
    return sorted(set(re.findall(r"'([A-Za-z0-9_\-]+\.json)'", text)))


def build(out: Path) -> int:
    if not WEB_DIR.is_dir():
        print(f"error: {WEB_DIR} not found", file=sys.stderr)
        return 2
    if not DATA_DIR.is_dir():
        print(f"error: {DATA_DIR} not found", file=sys.stderr)
        return 2
    out = out.resolve()
    # The output directory is wiped before every build, so a stray --out must
    # not point at the repository, one of its parents, or an unrelated folder
    # that holds something else. A previous build (has index.html) is fine.
    if out == ROOT or out in ROOT.parents:
        print(f"error: refusing to use {out} as output (it contains the repository)", file=sys.stderr)
        return 2
    if out.exists() and any(out.iterdir()) and not (out / "index.html").exists():
        print(f"error: {out} exists, is not empty and is not a previous build; pick another --out", file=sys.stderr)
        return 2
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(WEB_DIR, out, ignore=_skip)
    data_out = out / "data"
    data_out.mkdir(parents=True, exist_ok=True)
    copied = 0
    for src in sorted(DATA_DIR.glob("*.json")):
        shutil.copy2(src, data_out / src.name)
        copied += 1

    missing = [name for name in referenced_payloads(WEB_DIR / "js" / "api.js") if not (data_out / name).exists()]
    print(f"static site written to {out}")
    print(f"  {copied} payload(s) under {data_out.relative_to(out)}/")
    for name in ("index.html", "js", "css"):
        marker = "ok" if (out / name).exists() else "MISSING"
        print(f"  {name}: {marker}")
    if missing:
        print("  note: api.js references payloads that public/data/ does not have yet: " + ", ".join(missing))
        print("        those research tabs will show their empty state until the next publish run.")
    return 0 if (out / "index.html").exists() else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory (default: dist/)")
    args = parser.parse_args(argv)
    return build(args.out)


if __name__ == "__main__":
    raise SystemExit(main())
