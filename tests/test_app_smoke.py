"""Headless smoke test for the Streamlit app: every page renders.

Streamlit's ``AppTest`` executes the whole app script once per page and
reports any uncaught exception. This is the only check that covers the
14k-line monolith end to end, so it runs in the normal unit run and in CI.

It used to be opt-in behind ``RUN_APP_SMOKE`` because it fetched from the
public APIs: slow and flaky. That gate cost more than it saved. A KeyError
in ``trader_flow_scores`` took the pages Search and Traders down for several
pull requests while CI stayed green, because the only test that would have
seen it was one of three silent skips.

The fix is not a shorter check, it is a hermetic one: ``requests`` is routed
to ``tests/market_api_fixtures.py``, a small standing market picture. That
removes both reasons for the gate at once, network and runtime, and it makes
the run deterministic.

The fixtures deliver rows on purpose. With empty responses nearly every
aggregation returns at its ``if frame.empty`` guard, and the smoke would
render two dozen empty pages without touching the code that breaks. A
separate test below asserts the fixtures keep delivering rows, so the check
cannot quietly decay into a no-op.

``RUN_APP_SMOKE=1`` still exists and now means what it says: additionally run
the same pass against the live public APIs, to catch schema drift on the
other side of the wire.
"""

import ast
import os
import unittest
from pathlib import Path

from tests.market_api_fixtures import offline_market_apis

APP = str(Path(__file__).resolve().parents[1] / "prediction_terminal.py")

#: Die acht Research-Seiten fehlten in dieser Liste, seit es sie gibt. Der
#: Smoke hat 16 von 24 Seiten geladen und die uebrigen nie angefasst; der
#: Test darunter haelt die Liste ab jetzt an PAGES fest.
PAGE_SLUGS = [
    "overview",
    "search",
    "markets",
    "traders",
    "track",
    "live-trades",
    "wallets",
    "backtester",
    "copy-trade",
    "whale-flow",
    "suspicious",
    "cross-venue",
    "monitor",
    "resolved",
    "portfolio",
    "settings",
    "review-queue",
    "category-efficiency",
    "mentions-latency",
    "live-runs",
    "microstructure",
    "pilot",
    "pipeline-forward",
    "methodology",
]


def declared_page_slugs() -> list[str]:
    """Slugs aus dem ``PAGES``-Dict des Monolithen, ohne ihn auszufuehren.

    Der Monolith ist ein Streamlit-Skript: ein Import wuerde die App
    starten. Das Dict steht als Literal im Quelltext, der Syntaxbaum
    genuegt also. Die Slug-Regel ist dieselbe wie in PAGE_QUERY_SLUGS.
    """

    tree = ast.parse(Path(APP).read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if "PAGES" not in targets or not isinstance(node.value, ast.Dict):
            continue
        return [
            key.value.lower().replace(" ", "-")
            for key in node.value.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        ]
    raise AssertionError("no module-level PAGES dict found in prediction_terminal.py")


#: Tests, die bewusst nicht im Standardlauf laufen. Die Liste ist kurz zu
#: halten: jeder Eintrag ist eine Pruefung, die niemand sieht.
OPT_IN_BY_DESIGN = {"test_app_smoke.LiveAppSmokeTests.test_every_page_loads_against_the_live_apis"}


def skip_gated_test_ids() -> set[str]:
    """Alle Tests, die ein Skip-Dekorator dauerhaft abschaltet.

    Geladen, nicht ausgefuehrt: der Loader baut die Suite, gelesen wird nur
    das Flag, das ``unittest.skip`` und Geschwister setzen. Laufzeit-Skips
    ueber ``self.skipTest`` stehen bewusst nicht drin, die haengen an Daten
    und melden sich im Lauf selbst.
    """

    tests_dir = Path(__file__).resolve().parent
    # Ohne top_level_dir, genau wie der Runner in der CI: tests/ ist kein
    # Paket, der Loader legt es selbst auf den Suchpfad.
    suite = unittest.defaultTestLoader.discover(str(tests_dir), pattern="test_*.py")

    def walk(node):
        if isinstance(node, unittest.TestSuite):
            for child in node:
                yield from walk(child)
        else:
            yield node

    gated = set()
    for test in walk(suite):
        method = getattr(test, getattr(test, "_testMethodName", ""), None)
        if getattr(type(test), "__unittest_skip__", False) or getattr(method, "__unittest_skip__", False):
            gated.add(test.id().removeprefix("tests."))
    return gated

#: ``safe_load`` swallows a failing fetch and writes this into the page. On
#: fixtures nothing may fail, so the phrase marks a parser that broke behind
#: the fallback: the page still claims to be live and shows nothing.
SAFE_LOAD_FAILURE_MARKER = "unavailable:"


def run_page(slug: str, secrets: dict | None = None):
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(APP, default_timeout=60)
    app.query_params["page"] = slug
    for key, value in (secrets or {}).items():
        app.secrets[key] = value
    app.run()
    return app


def swallowed_fetch_failures(app) -> list[str]:
    return [
        str(block.value)
        for block in app.warning
        if SAFE_LOAD_FAILURE_MARKER in str(block.value)
    ]


class AppSmokeTests(unittest.TestCase):
    """Every page renders, against fixtures, in the normal unit run."""

    def test_every_page_loads_without_exception(self) -> None:
        # Beide Zusicherungen teilen sich einen Durchlauf pro Seite: das
        # Skript einmal auszufuehren kostet rund drei Sekunden, und diese
        # Pruefung soll im normalen Lauf bleiben, nicht wieder abgeschaltet
        # werden, weil sie zu lange braucht.
        with offline_market_apis():
            for slug in PAGE_SLUGS:
                with self.subTest(page=slug):
                    app = run_page(slug)
                    self.assertFalse(bool(app.exception), f"{slug}: {app.exception}")
                    # Auf Fixtures darf kein Abruf scheitern. Tut er es doch,
                    # hat ein Parser aufgegeben und safe_load hat es
                    # verschluckt: genau das Muster, das eine Seite live
                    # aussehen laesst, obwohl sie nichts mehr zeigt.
                    self.assertEqual(
                        [],
                        swallowed_fetch_failures(app),
                        f"{slug}: a fetch failed on fixtures and safe_load swallowed it",
                    )


class SmokeGateTests(unittest.TestCase):
    """Der Seiten-Smoke darf nicht wieder hinter eine Umgebungsvariable.

    Genau das war die Ursache dafuer, dass zwei kaputte Seiten mehrere PRs
    lang gruen durchliefen: der einzige Test, der sie geladen haette, war
    einer von drei stillen Skips. Ein Skip-Dekorator an der Klasse faellt
    ab jetzt hier auf, statt lautlos die Pruefung abzuraeumen.
    """

    def test_the_page_smoke_runs_in_the_default_unit_run(self) -> None:
        self.assertFalse(
            getattr(AppSmokeTests, "__unittest_skip__", False),
            "AppSmokeTests must not be skip-gated: it is the only end-to-end check of the monolith",
        )
        for name in ("test_every_page_loads_without_exception",):
            self.assertFalse(
                getattr(getattr(AppSmokeTests, name), "__unittest_skip__", False),
                f"{name} must not be skip-gated",
            )

    def test_every_navigable_page_is_in_the_smoke_list(self) -> None:
        # Eine neue Seite, die nicht in PAGE_SLUGS steht, waere ungeprueft.
        # Genau so sind die acht Research-Seiten am Smoke vorbeigelaufen.
        self.assertEqual(sorted(declared_page_slugs()), sorted(PAGE_SLUGS))

    def test_no_test_is_skip_gated_without_being_declared_here(self) -> None:
        # Die Suite meldete konstant "skipped=3", und alle drei waren die
        # Seiten-Pruefungen. Eine Zahl im Abschlussbericht liest niemand als
        # Warnung. Ab jetzt muss jeder dauerhaft abgeschaltete Test hier
        # stehen, sonst faellt die Suite darueber.
        self.assertEqual(OPT_IN_BY_DESIGN, skip_gated_test_ids())


class FixtureCoverageTests(unittest.TestCase):
    """Die Fixtures muessen Zeilen liefern, sonst prueft der Smoke nichts.

    Auf leeren Antworten steigt fast jede Aggregation an ihrem
    ``if frame.empty``-Wachposten sofort aus. Ein Smoke gegen leere Fixtures
    laedt 16 Seiten und beruehrt die Rechenwege nicht, an denen die Fehler
    sitzen. Dieser Test haelt das Marktbild gefuellt.
    """

    def test_fixtures_deliver_rows_so_the_smoke_is_not_a_no_op(self) -> None:
        from src import prediction_markets as md

        with offline_market_apis():
            self.assertFalse(md.get_polymarket_markets(limit=50).empty)
            self.assertFalse(md.get_polymarket_trades(limit=50).empty)
            self.assertFalse(md.get_polymarket_leaderboard(limit=10).empty)
            self.assertFalse(md.get_kalshi_markets(limit=10).empty)
            self.assertFalse(md.get_kalshi_trades(limit=10).empty)

    def test_the_fixture_tape_reaches_the_aggregation_that_broke(self) -> None:
        # trader_flow_scores hat auf jedem nicht leeren Tape geworfen. Das
        # Fixture-Tape muss also nicht leer bei ihm ankommen, sonst faehrt
        # der Smoke wieder blind an dieser Stelle vorbei.
        from src import prediction_markets as md

        with offline_market_apis():
            tape = md.get_polymarket_trades(limit=50)
        scores = md.trader_flow_scores(tape, whale_threshold=2500.0)
        self.assertFalse(scores.empty)
        self.assertGreaterEqual(int(scores["markets"].max()), 2)


FAKE_AUTH_SECRETS = {
    "redirect_uri": "http://localhost:8503/oauth2callback",
    "cookie_secret": "smoke-test-secret",
    "client_id": "smoke-client-id",
    "client_secret": "smoke-client-secret",
    "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
}


class AuthGateSmokeTests(unittest.TestCase):
    """Settings admin gate: open without [auth] secrets, fail-closed with them."""

    def _run_settings(self, with_auth_secrets: bool):
        with offline_market_apis():
            app = run_page("settings", {"auth": dict(FAKE_AUTH_SECRETS)} if with_auth_secrets else None)
        self.assertFalse(bool(app.exception), str(app.exception))
        return app

    def test_settings_open_in_local_mode_without_auth_secrets(self) -> None:
        app = self._run_settings(with_auth_secrets=False)
        self.assertTrue(len(app.slider) > 0, "settings widgets should render in open mode")
        markdown_text = " ".join(str(block.value) for block in app.markdown)
        self.assertNotIn("Admin access required", markdown_text)
        button_keys = {getattr(button, "key", "") for button in app.button}
        self.assertNotIn("sidebar_sign_in", button_keys, "no sign-in surface without auth secrets")

    def test_settings_fail_closed_with_auth_secrets_and_anonymous_user(self) -> None:
        app = self._run_settings(with_auth_secrets=True)
        self.assertEqual(len(app.slider), 0, "settings widgets must stay hidden behind the gate")
        markdown_text = " ".join(str(block.value) for block in app.markdown)
        self.assertIn("Admin access required", markdown_text)
        button_keys = {getattr(button, "key", "") for button in app.button}
        self.assertIn("settings_sign_in", button_keys)
        self.assertIn("sidebar_sign_in", button_keys)


@unittest.skipUnless(
    os.environ.get("RUN_APP_SMOKE"),
    "set RUN_APP_SMOKE=1 to additionally run the page smoke against the live public APIs",
)
class LiveAppSmokeTests(unittest.TestCase):
    """Derselbe Durchlauf gegen die echten APIs, opt-in.

    Nicht Teil des Gates: er braucht Netz und ist damit von fremder
    Verfuegbarkeit abhaengig. Sein Zweck ist der, den Fixtures nicht
    erfuellen koennen, naemlich zu merken, wenn eine oeffentliche API ihr
    Schema aendert.
    """

    def test_every_page_loads_against_the_live_apis(self) -> None:
        for slug in PAGE_SLUGS:
            with self.subTest(page=slug):
                app = run_page(slug)
                self.assertFalse(bool(app.exception), f"{slug}: {app.exception}")


if __name__ == "__main__":
    unittest.main()
