import re
import unittest
import xml.etree.ElementTree as ET

from app import cluster_figure as fig

PAYLOAD = {
    "graph": {
        "regel": "same side of at least 2 markets within 5 minutes",
        "fenster": "2026-08-06 00:56 to 22:15 UTC · 21.3 h · 1,032 prints",
        "kennzahl": {"wallets": 4, "kanten": 3, "cluster": 2, "modularitaet": 0.6},
        "spanne": {"x": [-1.0, 1.0], "y": [-1.0, 1.0]},
        "cluster": [
            {"id": 1, "name": "C-1", "groesse": 3, "volumen": 30000.0, "volumen_label": "$30.0k"},
            {"id": 2, "name": "C-2", "groesse": 2, "volumen": 12000.0, "volumen_label": "$12.0k"},
        ],
        "knoten": [
            {"wallet": "0xa", "kurz": "0xa…1", "x": -1.0, "y": -1.0, "cluster": 1, "volumen": 10000.0, "maerkte": 3, "trades": 5, "geteilt": 2},
            {"wallet": "0xb", "kurz": "0xb…2", "x": -0.5, "y": -0.8, "cluster": 1, "volumen": 12000.0, "maerkte": 3, "trades": 6, "geteilt": 2},
            {"wallet": "0xc", "kurz": "0xc…3", "x": 0.4, "y": 0.6, "cluster": 1, "volumen": 8000.0, "maerkte": 2, "trades": 3, "geteilt": 2},
            {"wallet": "0xd", "kurz": "0xd…4", "x": 1.0, "y": 1.0, "cluster": 2, "volumen": 12000.0, "maerkte": 2, "trades": 4, "geteilt": 2},
        ],
        "kanten": [
            {"a": 0, "b": 1, "geteilt": 3, "notional": 22000.0},
            {"a": 1, "b": 2, "geteilt": 2, "notional": 20000.0},
            {"a": 2, "b": 3, "geteilt": 2, "notional": 20000.0},
        ],
    },
    "matrix": {
        "cluster": "C-1",
        "wallets": [
            {"wallet": "0xa", "kurz": "0xa…1", "volumen": 10000.0},
            {"wallet": "0xb", "kurz": "0xb…2", "volumen": 12000.0},
        ],
        "maerkte": [
            {"label": "Ceasefire | Yes", "markt": "Ceasefire holds by July 31", "seite": "Yes", "wallets": 2},
            {"label": "Blockade | No", "markt": "Blockade ends by August", "seite": "No", "wallets": 2},
        ],
        "zellen": [[5000.0, 0.0], [3000.0, 2000.0]],
        "belegt": 3,
        "felder": 4,
    },
}


class SvgTests(unittest.TestCase):
    def test_ist_wohlgeformtes_xml(self):
        """Eine Abbildung, die kein Programm oeffnen kann, ist wertlos."""
        wurzel = ET.fromstring(fig.build_svg(PAYLOAD))
        # ElementTree zieht die Namensraum-Deklaration in den Tag.
        self.assertEqual(wurzel.tag, "{http://www.w3.org/2000/svg}svg")

    def test_ohne_rgba_farben(self):
        """SVG 1.1 kennt rgba() nicht.

        Der Browser zeigt es trotzdem, Word und Inkscape nicht zwingend.
        Diese Datei soll in einer schriftlichen Arbeit landen, also nur
        Volltonwerte plus die von SVG definierten Opazitaets-Attribute.
        """
        self.assertNotIn("rgba(", fig.build_svg(PAYLOAD))

    def test_traegt_regel_fenster_und_scope_im_bild(self):
        """Ein Screenshot trennt sich von jeder Bildunterschrift."""
        svg = fig.build_svg(PAYLOAD)
        self.assertIn("RULE ·", svg)
        self.assertIn("WINDOW ·", svg)
        self.assertIn("SCOPE ·", svg)
        self.assertIn("21.3 h", svg)

    def test_zeichnet_jeden_knoten_und_jede_kante(self):
        svg = fig.build_svg(PAYLOAD)
        self.assertEqual(len(re.findall(r"<circle ", svg)), len(PAYLOAD["graph"]["knoten"]))
        self.assertEqual(len(re.findall(r"<line ", svg)), len(PAYLOAD["graph"]["kanten"]))

    def test_cluster_legende_statt_beschriftung_im_graphen(self):
        svg = fig.build_svg(PAYLOAD)
        self.assertIn("C-1 · 3w · $30.0k", svg)
        self.assertIn("C-2 · 2w · $12.0k", svg)

    def test_matrix_zeigt_belegte_und_leere_felder(self):
        svg = fig.build_svg(PAYLOAD)
        # 2 Wallets x 2 Maerkte: drei belegt (lime), eines leer. Auf die
        # Zellform rx="2.5" gepruefft, sonst zaehlen Knoten in derselben
        # Clusterfarbe mit.
        belegt = re.findall(r'rx="2\.5" fill="#D9A648" fill-opacity', svg)
        leer = re.findall(r'rx="2\.5" fill="#EAE6DC" fill-opacity="0\.045"', svg)
        self.assertEqual(len(belegt), 3)
        self.assertEqual(len(leer), 1)

    def test_marktlegende_nennt_seite_und_wallets(self):
        svg = fig.build_svg(PAYLOAD)
        self.assertIn("Ceasefire holds by July 31", svg)
        self.assertIn("Yes · 2w", svg)

    def test_leerer_graph_bricht_nicht(self):
        svg = fig.build_svg({"graph": {}, "matrix": {}})
        ET.fromstring(svg)
        self.assertIn("no cluster in this window", svg)

    def test_sonderzeichen_werden_escaped(self):
        payload = {
            "graph": dict(PAYLOAD["graph"], regel='rule with <tag> & "quotes"'),
            "matrix": PAYLOAD["matrix"],
        }
        svg = fig.build_svg(payload)
        ET.fromstring(svg)
        self.assertIn("&lt;tag&gt;", svg)
        self.assertNotIn("<tag>", svg)

    def test_breite_wird_uebernommen(self):
        wurzel = ET.fromstring(fig.build_svg(PAYLOAD, breite=900))
        self.assertEqual(wurzel.get("width"), "900")


class KontextTests(unittest.TestCase):
    """Was die Figur ohne ihre Kontrolle und ihren Nenner behauptet."""

    def _mit(self, **graph_extra):
        payload = {"graph": dict(PAYLOAD["graph"], **graph_extra),
                   "matrix": PAYLOAD["matrix"]}
        return fig.build_svg(payload)

    def test_nullmodell_steht_im_bild(self):
        svg = self._mit(nullmodell={"runs": 2, "wallets": 63, "kanten": 846,
                                    "cluster": 4, "lift_median": 1.4})
        self.assertIn("CONTROL ·", svg)
        self.assertIn("4 clusters over 846 links", svg)
        self.assertIn("1.4x", svg)

    def test_nullmodell_ohne_treffer_wird_auch_gesagt(self):
        svg = self._mit(nullmodell={"runs": 3, "cluster": 0, "kanten": 0})
        self.assertIn("returns nothing", svg)

    def test_kopf_waechst_mit_seinen_zeilen(self):
        """Zwei Zusatzzeilen duerfen nicht in die Tafeln darunter laufen."""
        ohne = ET.fromstring(fig.build_svg(PAYLOAD))
        mit = ET.fromstring(self._mit(stand_utc="2026-08-28T09:00:00+00:00",
                                      nullmodell={"runs": 2, "cluster": 4, "kanten": 846}))
        self.assertGreater(int(mit.get("height")), int(ohne.get("height")))

    def test_wallets_chip_traegt_seinen_nenner(self):
        svg = self._mit(kennzahl=dict(PAYLOAD["graph"]["kennzahl"],
                                      wallets_im_tape=300, lift_median=2.8))
        self.assertIn("WALLETS 4 / 300", svg)
        self.assertIn("MEDIAN LIFT 2.8x", svg)

    def test_snapshot_steht_im_bild(self):
        self.assertIn("SNAPSHOT ·", self._mit(stand_utc="2026-08-28T09:00:00+00:00"))


if __name__ == "__main__":
    unittest.main()
