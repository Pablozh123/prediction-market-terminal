"""Render current and historical evidence without changing its observation dates."""

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node is required for renderer checks")
class ResearchRefreshRenderTests(unittest.TestCase):
    def test_recent_cards_lead_and_plans_are_distinct_from_findings(self):
        script = """
import assert from 'node:assert/strict';
import { renderMicrostructure } from './web/js/pages/microstructure_page.js';
const old = { id: 'old', frage: 'Old finding', status: 'historical', verdikt_art: 'offen',
  basis: { fenster: '2026-07-18 to 2026-07-28' },
  follow_up: { status: 'planned', question: 'Can <unsafe> quotes survive?', report: 'docs/research/plan.md' } };
const recent = { id: 'recent', frage: 'Recent finding', status: 'recent', verdikt_art: 'offen',
  published_at_utc: '2026-10-12T10:28:17+00:00', basis: { fenster: '2026-10-11 to 2026-10-12' } };
const html = renderMicrostructure({ studien: [old, recent], zaehler: { gesamt: 2 },
  stand_utc: '2026-10-12T16:00:00+00:00' }, { stamp: 'versioned' });
assert.ok(html.includes('Recent research'));
assert.ok(html.includes('Historical studies'));
assert.ok(html.includes('id="research/microstructure/recent"'));
assert.ok(html.includes('id="research/microstructure/old"'));
assert.ok(html.indexOf('id="research/microstructure/recent"') < html.indexOf('id="research/microstructure/old"'));
assert.ok(html.includes('NEXT TEST · PLANNED'));
assert.ok(html.includes('Can &lt;unsafe&gt; quotes survive?'));
assert.ok(!html.includes('<unsafe>'));
assert.ok(html.includes('2026-07-18 to 2026-07-28'));
assert.ok(html.includes('Page export dates do not extend'));
"""
        result = subprocess.run(
            [shutil.which("node"), "--input-type=module", "-e", script], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
