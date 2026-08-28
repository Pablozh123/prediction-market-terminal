"""Compile data/claims.yaml into the module the web frontend imports.

    python scripts/publish_claims.py            # write web/js/claims_register.js
    python scripts/publish_claims.py --check     # only report drift (exit 1)

The frontend must be able to render a caveat before it has spoken to
anything, so the register travels with the bundle instead of arriving as a
response. This script is the only writer of web/js/claims_register.js;
scripts/lint_claims.py runs the same comparison in CI, so a register change
that is not recompiled fails there rather than shipping a page whose caveats
are one revision behind.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import claims

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="do not write; exit 1 when the module is out of date")
    args = parser.parse_args(argv)

    register_path = claims.CLAIMS_PATH
    module_path = claims.FRONTEND_MODULE_PATH
    name = claims.FRONTEND_MODULE_REL
    anzahl = len(claims.frontend_register(register_path)["disclaimers"])
    wanted = claims.frontend_module_source(register_path)
    current = module_path.read_text(encoding="utf-8") if module_path.exists() else ""

    if current == wanted:
        print(f"{name} is up to date ({anzahl} disclaimers)")
        return 0
    if args.check:
        print(f"error: {name} does not match data/claims.yaml; "
              "run python scripts/publish_claims.py", file=sys.stderr)
        return 1
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(wanted, encoding="utf-8")
    print(f"wrote {name} ({anzahl} disclaimers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
