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
    dist/study/<slug>/…     <- one crawlable page per frozen study
    dist/.well-known/…      <- security.txt (the only dot-directory copied)

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
import json
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import static_studies as st  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "public" / "data"
DEFAULT_OUT = ROOT / "dist"

# Never copied, wherever they sit inside web/. Dot-prefixed names are
# editor and OS leftovers, with one exception: .well-known/ carries
# security.txt and must ship.
SKIP_NAMES = {"__pycache__", ".DS_Store", "Thumbs.db"}
KEEP_DOTNAMES = {".well-known"}


def _skip(directory: str, names: list[str]) -> set[str]:
    return {n for n in names if n in SKIP_NAMES or (n.startswith(".") and n not in KEEP_DOTNAMES)}


def referenced_payloads(api_js: Path) -> list[str]:
    """File names the frontend expects under ./data/ (from the STATISCH table)."""

    if not api_js.exists():
        return []
    text = api_js.read_text(encoding="utf-8")
    return sorted(set(re.findall(r"'([A-Za-z0-9_\-]+\.json)'", text)))


def write_study_pages(out: Path, data_out: Path) -> list[str]:
    """One crawlable document per frozen study, plus its sitemap entries.

    The app is hash-routed, so every study lives at the same URL as far as a
    crawler is concerned — web/sitemap.xml says so and lists only the real
    documents. The findings are the content of this site, so each one gets an
    address: dist/study/<slug>/index.html, built from the published payload,
    with no figure that is not in that file.
    """

    quelle = data_out / "microstructure.json"
    if not quelle.exists():
        return []
    try:
        payload = json.loads(quelle.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        print(f"  note: {quelle.name} could not be read ({err}); no study pages written")
        return []
    seiten = st.study_pages(payload)
    if not seiten:
        return []
    for slug, html in seiten.items():
        ziel = out / st.STUDY_DIR / slug
        ziel.mkdir(parents=True, exist_ok=True)
        (ziel / "index.html").write_text(html, encoding="utf-8")
    sitemap = out / "sitemap.xml"
    if sitemap.exists():
        stand = str(payload.get("stand_utc") or "")[:10] or date.today().isoformat()
        sitemap.write_text(
            st.sitemap_mit_studien(sitemap.read_text(encoding="utf-8"), sorted(seiten), stand),
            encoding="utf-8")
    return sorted(seiten)


def build(out: Path, api_base: str = "") -> int:
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

    if api_base:
        index = out / "index.html"
        html = index.read_text(encoding="utf-8")
        marker = '<meta name="api-base" content="">'
        if marker not in html:
            print("error: web/index.html has no <meta name=\"api-base\"> tag to fill", file=sys.stderr)
            return 2
        html = html.replace(marker, f'<meta name="api-base" content="{api_base}">', 1)
        index.write_text(html, encoding="utf-8")

    studien = write_study_pages(out, data_out)

    missing = [name for name in referenced_payloads(WEB_DIR / "js" / "api.js") if not (data_out / name).exists()]
    print(f"static site written to {out}")
    print(f"  api base: {api_base or '(same origin)'}")
    print(f"  {copied} payload(s) under {data_out.relative_to(out)}/")
    for name in ("index.html", "js", "css"):
        marker = "ok" if (out / name).exists() else "MISSING"
        print(f"  {name}: {marker}")
    if studien:
        print(f"  {len(studien)} study page(s) under {st.STUDY_DIR}/, listed in sitemap.xml")
    else:
        print("  no study pages: microstructure.json is missing or carries no study with an id")
    if missing:
        print("  note: api.js references payloads that public/data/ does not have yet: " + ", ".join(missing))
        print("        those research tabs will show their empty state until the next publish run.")
    return 0 if (out / "index.html").exists() else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory (default: dist/)")
    parser.add_argument(
        "--api-base",
        default=os.environ.get("API_BASE_URL", ""),
        help="absolute URL of the live API when it is hosted elsewhere, e.g. https://api.example.org "
        "(default: env API_BASE_URL, else same origin)",
    )
    args = parser.parse_args(argv)
    api_base = args.api_base.strip().rstrip("/")
    if api_base and not api_base.startswith(("http://", "https://")):
        print("error: --api-base must be an absolute http(s) URL", file=sys.stderr)
        return 2
    return build(args.out, api_base)


if __name__ == "__main__":
    raise SystemExit(main())
