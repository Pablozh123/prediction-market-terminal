"""Das Image traegt das Caveat-Register, sonst nichts aus data/.

/api/claims las auf dem Deploy-Host eine leere Datei: .dockerignore liess
data/ komplett weg, und das Register liegt genau dort. Die Ausnahme fuer die
eine versionierte Datei steht in .dockerignore und im Dockerfile; dieser
Test haelt beide zusammen.
"""

from __future__ import annotations

import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]


class DockerImageTests(unittest.TestCase):
    def test_claims_register_kommt_ins_image(self) -> None:
        dockerfile = (WURZEL / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY data/claims.yaml ./data/claims.yaml", dockerfile)
        ignore = [z.strip() for z in (WURZEL / ".dockerignore").read_text(encoding="utf-8").splitlines()]
        self.assertIn("data/", ignore)
        self.assertIn("!data/claims.yaml", ignore)
        # Die Ausnahme muss nach dem Ausschluss stehen, sonst gilt sie nicht.
        self.assertGreater(ignore.index("!data/claims.yaml"), ignore.index("data/"))
        self.assertTrue((WURZEL / "data" / "claims.yaml").is_file())
        # railway up honours .gitignore: without the exception the upload
        # lacks the file and the Dockerfile COPY fails (build 2026-09-04).
        gitignore = [z.strip() for z in (WURZEL / ".gitignore").read_text(encoding="utf-8").splitlines()]
        self.assertIn("!data/claims.yaml", gitignore)
        self.assertGreater(gitignore.index("!data/claims.yaml"), gitignore.index("data/"))


if __name__ == "__main__":
    unittest.main()
