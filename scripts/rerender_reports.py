"""Re-render study reports from their stored JSON, without recomputing anything.

Every study module writes three artefacts side by side: the full result dict as
JSON, a CSV of the rows, and a Markdown report built from that same dict. The
JSON is the record; the Markdown is a rendering of it. So when the wording of a
report changes, there is no reason to re-run the study over gigabytes of
recorder data, and every reason not to: a re-run would hit live APIs, pick up
newer prices, and silently change the numbers a finished report already states.

This script therefore reloads each stored JSON and calls the module's own
renderer on it. The numbers are guaranteed identical because they are the same
numbers; only the prose around them is rebuilt.

Usage:
  python -m scripts.rerender_reports                 # every report
  python -m scripts.rerender_reports --module mm_pnl # one module
  python -m scripts.rerender_reports --dry-run
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = REPO_ROOT / "docs" / "research"

#: Module name -> (artefact prefix, whether a PNG is rendered from the same
#: result dict). The prefix is not always the module name: orderflow_study
#: writes ``orderflow_<tag>``, so deriving it from the import path would silently
#: skip that study's reports.
MODULES = {
    "mm_pnl": ("mm_pnl", True),
    "orderflow_study": ("orderflow", True),
    "edge_segments": ("edge_segments", True),
    "cross_venue_gaps": ("cross_venue_gaps", False),
    "gap_lifetime": ("gap_lifetime", False),
    "reward_selection": ("reward_selection", False),
    "book_reconcile": ("book_reconcile", False),
    "resolution_rules": ("resolution_rules", False),
}


def reports_for(module_name: str, research_dir: Path = RESEARCH_DIR
                ) -> list[tuple[str, Path]]:
    """(tag, json path) for every stored report of one module, tag order stable."""
    prefix = f"{MODULES[module_name][0]}_"
    out = []
    for path in sorted(research_dir.glob(f"{prefix}*.json")):
        out.append((path.stem[len(prefix):], path))
    return out


def rerender(module_name: str, tag: str, json_path: Path,
             research_dir: Path = RESEARCH_DIR, png: bool = False) -> list[Path]:
    """Rebuild the Markdown (and PNG) for one stored result. Returns what changed."""
    module = importlib.import_module(f"src.{module_name}")
    results = json.loads(json_path.read_text(encoding="utf-8"))
    stem = MODULES[module_name][0]
    written = []

    md_path = research_dir / f"{stem}_{tag}.md"
    body = module._markdown(results, tag)
    if not md_path.exists() or md_path.read_text(encoding="utf-8") != body:
        md_path.write_text(body, encoding="utf-8")
        written.append(md_path)

    if png and hasattr(module, "render_png"):
        png_path = research_dir / f"{stem}_{tag}.png"
        try:
            module.render_png(results, png_path)
            written.append(png_path)
        except Exception as exc:  # noqa: BLE001 - a missing plot is not fatal
            print(f"  PNG skipped for {module_name}_{tag}: {type(exc).__name__}")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--module", action="append",
                        help="only this module (repeatable)")
    parser.add_argument("--research-dir", default=str(RESEARCH_DIR))
    parser.add_argument("--dry-run", action="store_true",
                        help="list what would be rebuilt")
    args = parser.parse_args(argv)

    research_dir = Path(args.research_dir)
    wanted = args.module or list(MODULES)
    unknown = [name for name in wanted if name not in MODULES]
    if unknown:
        parser.error(f"unknown module(s): {', '.join(unknown)}")

    total = 0
    for name in wanted:
        for tag, json_path in reports_for(name, research_dir):
            if args.dry_run:
                print(f"would rebuild {name}_{tag}")
                total += 1
                continue
            written = rerender(name, tag, json_path, research_dir,
                               png=MODULES[name][1])
            for path in written:
                print(f"rebuilt {path.name}")
            total += len(written)
    print(f"{total} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
