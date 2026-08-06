"""Die Co-Trading-Figur als eigenstaendige SVG.

Die Seite zeichnet dieselben zwei Bilder fuer den Bildschirm. Fuer eine
schriftliche Arbeit taugt ein Screenshot davon schlecht: er ist an eine
Fenstergroesse gebunden, wird beim Vergroessern unscharf und traegt die
Bildunterschrift nicht mit sich. Dieses Modul schreibt stattdessen eine
Vektordatei, die in jeder Groesse scharf bleibt und Regel, Fenster und
Stichprobe im Bild selbst nennt.

Gezeichnet wird aus derselben Nutzlast wie im Frontend
(`api_views.network_graph` und `api_views.overlap_matrix`), damit Figur
und Seite nicht auseinanderlaufen koennen.

Streamlit-frei nach Projektkonvention.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

BG = "#0A0D0F"
PANEL = "#10151A"
TEXT = "#ffffff"
AKZENT = "#4F8EF7"
# Volltonwerte statt rgba(): SVG 1.1 kennt rgba() nicht. Browser schlucken
# es, Word und Inkscape nicht zwingend, und diese Datei soll in einer
# schriftlichen Arbeit landen. Die Werte entsprechen Weiss bei 55 bzw. 38
# Prozent ueber dem Panelton.
RAHMEN = "#2A3138"
GEDAEMPFT = "#9AA0A6"
LEISE = "#6E757C"
MONO = "JetBrains Mono, DejaVu Sans Mono, monospace"
SANS = "Inter, Segoe UI, Helvetica, Arial, sans-serif"

CLUSTER_FARBEN = (
    "#C8F542", "#4F8EF7", "#F5A623", "#FF7A7A", "#7DE2D1",
    "#C792EA", "#FFD166", "#8FD694", "#F78FB3", "#9AB0FF",
)


def _farbe(index: int) -> str:
    return CLUSTER_FARBEN[index % len(CLUSTER_FARBEN)]


def _esc(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _text(x: float, y: float, inhalt: Any, *, groesse: float = 11.0,
          farbe: str = TEXT, familie: str = MONO, anker: str = "start",
          gewicht: str = "normal", opazitaet: float = 1.0) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{groesse}" font-family="{familie}" '
        f'fill="{farbe}" text-anchor="{anker}" font-weight="{gewicht}" '
        f'fill-opacity="{opazitaet}">{_esc(inhalt)}</text>'
    )


def _kasten(x: float, y: float, w: float, h: float, *, fuellung: str = PANEL,
            radius: float = 10.0) -> str:
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{radius}" '
        f'fill="{fuellung}" stroke="{RAHMEN}" stroke-width="1" />'
    )


def _geld(wert: float) -> str:
    wert = float(wert or 0.0)
    if abs(wert) >= 1_000_000:
        return f"${wert / 1_000_000:.1f}m"
    if abs(wert) >= 1_000:
        return f"${wert / 1_000:.1f}k"
    return f"${wert:.0f}"


def _netzwerk(graph: Mapping[str, Any], x0: float, y0: float, w: float, h: float) -> str:
    knoten = graph.get("knoten") or []
    kanten = graph.get("kanten") or []
    if not knoten:
        return _text(x0 + w / 2, y0 + h / 2, "no cluster in this window",
                     farbe=GEDAEMPFT, anker="middle")

    pad = 34.0
    spanne = graph.get("spanne") or {}
    sx = spanne.get("x") or [0.0, 1.0]
    sy = spanne.get("y") or [0.0, 1.0]
    span_x = max(float(sx[1]) - float(sx[0]), 1e-6)
    span_y = max(float(sy[1]) - float(sy[0]), 1e-6)
    # Gleicher Massstab auf beiden Achsen, sonst verzerrt die Inselform.
    skala = min((w - 2 * pad) / span_x, (h - 2 * pad) / span_y)
    mx = x0 + (w - span_x * skala) / 2
    my = y0 + (h - span_y * skala) / 2

    def X(v: float) -> float:
        return mx + (float(v) - float(sx[0])) * skala

    def Y(v: float) -> float:
        return my + (float(v) - float(sy[0])) * skala

    cluster_index = {c["id"]: i for i, c in enumerate(graph.get("cluster") or [])}
    max_vol = max((float(n.get("volumen") or 0.0) for n in knoten), default=1.0) or 1.0
    max_geteilt = max((int(e.get("geteilt") or 0) for e in kanten), default=1) or 1

    teile: list[str] = []
    for e in kanten:
        a, b = knoten[e["a"]], knoten[e["b"]]
        gleich = a.get("cluster") == b.get("cluster")
        farbe = _farbe(cluster_index.get(a.get("cluster"), 0)) if gleich else "#ffffff"
        breite = 0.8 + 2.2 * (int(e.get("geteilt") or 1) / max_geteilt)
        teile.append(
            f'<line x1="{X(a["x"]):.1f}" y1="{Y(a["y"]):.1f}" x2="{X(b["x"]):.1f}" '
            f'y2="{Y(b["y"]):.1f}" stroke="{farbe}" stroke-opacity="'
            f'{0.5 if gleich else 0.22}" stroke-width="{breite:.2f}" />'
        )
    for n in knoten:
        farbe = _farbe(cluster_index.get(n.get("cluster"), 0))
        r = 3.4 + 7.6 * math.sqrt(float(n.get("volumen") or 0.0) / max_vol)
        teile.append(
            f'<circle cx="{X(n["x"]):.1f}" cy="{Y(n["y"]):.1f}" r="{r:.1f}" fill="{farbe}" '
            f'fill-opacity="0.85" stroke="{BG}" stroke-width="1.2" />'
        )
    # Bewusst keine Beschriftung im Graphen: in den dichten Inseln liegt sie
    # ueber den Knoten und verdeckt genau das, was gezeigt werden soll. Die
    # Zuordnung uebernimmt die Legende unter dem Bild.
    return "".join(teile)


def _cluster_legende(graph: Mapping[str, Any], x0: float, y0: float,
                     breite: float, spalten: int = 3) -> tuple[str, float]:
    """Farbschluessel unter dem Graphen. Meldet die benoetigte Hoehe zurueck."""
    cluster = [c for c in (graph.get("cluster") or []) if int(c.get("groesse") or 0) >= 2]
    if not cluster:
        return "", 0.0
    spalten_breite = breite / spalten
    zeilen = math.ceil(len(cluster) / spalten)
    teile: list[str] = []
    for i, c in enumerate(cluster):
        spalte, zeile = i % spalten, i // spalten
        x = x0 + spalte * spalten_breite
        y = y0 + zeile * 16
        teile.append(
            f'<rect x="{x:.1f}" y="{y - 7:.1f}" width="8" height="8" rx="2" '
            f'fill="{_farbe(i)}" />')
        teile.append(_text(
            x + 14, y, f'{c["name"]} · {c["groesse"]}w · {c.get("volumen_label", "")}',
            groesse=9.5, farbe=GEDAEMPFT))
    return "".join(teile), zeilen * 16 + 8


def _matrix(matrix: Mapping[str, Any], x0: float, y0: float, w: float) -> tuple[str, float]:
    """Zeichnet das Raster und meldet zurueck, wie hoch es geworden ist."""
    wallets = matrix.get("wallets") or []
    maerkte = matrix.get("maerkte") or []
    zellen = matrix.get("zellen") or []
    if not wallets or not maerkte:
        return _text(x0, y0 + 20, "no shared markets to show", farbe=GEDAEMPFT), 40.0

    label_w = 118.0
    kopf_h = 24.0
    luecke = 2.5
    verfuegbar = w - label_w - 8
    zell_b = max(16.0, min(30.0, verfuegbar / len(maerkte) - luecke))
    zell_h = 20.0
    max_wert = max((v for reihe in zellen for v in reihe if v > 0), default=1.0) or 1.0

    teile: list[str] = []
    for j in range(len(maerkte)):
        cx = x0 + label_w + j * (zell_b + luecke) + zell_b / 2
        teile.append(_text(cx, y0 + kopf_h - 8, f"M{j + 1}", groesse=9.5,
                           farbe=LEISE, anker="middle"))
    for i, wallet in enumerate(wallets):
        y = y0 + kopf_h + i * (zell_h + luecke)
        teile.append(_text(x0 + label_w - 10, y + zell_h / 2 + 3.5, wallet.get("kurz", ""),
                           groesse=10, farbe=GEDAEMPFT, anker="end"))
        for j in range(len(maerkte)):
            wert = (zellen[i] or [])[j] if i < len(zellen) and j < len(zellen[i]) else 0
            x = x0 + label_w + j * (zell_b + luecke)
            if wert and wert > 0:
                # Wurzel-Skala, sonst verschwinden kleine Beruehrungen ganz.
                deckung = 0.28 + 0.72 * math.sqrt(float(wert) / max_wert)
                teile.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{zell_b:.1f}" height="{zell_h}" '
                    f'rx="2.5" fill="#C8F542" fill-opacity="{deckung:.2f}" />')
            else:
                teile.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{zell_b:.1f}" height="{zell_h}" '
                    f'rx="2.5" fill="#ffffff" fill-opacity="0.045" />')
    hoehe = kopf_h + len(wallets) * (zell_h + luecke) + 6
    teile.append(_text(x0 + label_w, y0 + hoehe + 12,
                       "filled = wallet took that side · shade = notional",
                       groesse=9.5, farbe=LEISE))
    return "".join(teile), hoehe + 20


def build_svg(payload: Mapping[str, Any], *, breite: int = 1400) -> str:
    """Baut die vollstaendige Figur aus einem Risk-Payload."""
    graph = payload.get("graph") or {}
    matrix = payload.get("matrix") or {}
    kennzahl = graph.get("kennzahl") or {}

    rand = 26.0
    kopf_h = 128.0
    spalte_w = (breite - 3 * rand) / 2
    panel_kopf = 62.0
    netz_h = 420.0

    matrix_svg, matrix_h = _matrix(matrix, rand + spalte_w + rand + 18,
                                   rand + kopf_h + panel_kopf, spalte_w - 36)
    legende = matrix.get("maerkte") or []
    legende_h = len(legende) * 15.0 + 14 if legende else 0.0
    panel_h = max(netz_h, matrix_h + legende_h) + panel_kopf
    hoehe = int(rand + kopf_h + panel_h + rand)

    t: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{breite}" height="{hoehe}" '
        f'viewBox="0 0 {breite} {hoehe}" font-family="{SANS}">',
        f'<rect width="{breite}" height="{hoehe}" fill="{BG}" />',
    ]

    # Kopf
    t.append(_text(rand, rand + 16, "CO-TRADING STRUCTURE", groesse=10.5,
                   farbe=AKZENT, familie=MONO))
    t.append(_text(rand, rand + 44, "Wallets that keep meeting in the same markets",
                   groesse=21, farbe=TEXT, familie=SANS, gewicht="600"))

    chips = [("WALLETS", kennzahl.get("wallets")), ("LINKS", kennzahl.get("kanten")),
             ("CLUSTERS", kennzahl.get("cluster"))]
    if kennzahl.get("modularitaet") is not None:
        chips.append(("MODULARITY", kennzahl["modularitaet"]))
    if matrix.get("cluster"):
        chips.append(("MATRIX", matrix["cluster"]))
    cx = rand
    for label, wert in chips:
        beschriftung = f"{label} {wert if wert is not None else '—'}"
        w = 11 + len(beschriftung) * 6.2
        t.append(f'<rect x="{cx:.1f}" y="{rand + 56}" width="{w:.1f}" height="22" rx="5" '
                 f'fill="none" stroke="{RAHMEN}" />')
        t.append(_text(cx + 6, rand + 71, beschriftung, groesse=10, farbe=GEDAEMPFT))
        cx += w + 7

    zeilen = [f'RULE · {graph.get("regel", "not stated")}']
    if graph.get("fenster"):
        zeilen.append(f'WINDOW · {graph["fenster"]}')
    zeilen.append("SCOPE · insider-prone markets only, sports crypto and weather excluded")
    for i, zeile in enumerate(zeilen):
        t.append(_text(rand, rand + 96 + i * 14, zeile, groesse=10, farbe=LEISE))

    # Linke Tafel
    lx, ly = rand, rand + kopf_h
    t.append(_kasten(lx, ly, spalte_w, panel_h))
    t.append(_text(lx + 18, ly + 22, "WHO MOVES WITH WHOM", groesse=10, farbe=AKZENT))
    t.append(_text(lx + 18, ly + 42,
                   "Dot = wallet, sized by money moved. Line = same side of the same markets.",
                   groesse=11, farbe=GEDAEMPFT, familie=SANS))
    cluster_anzahl = len([c for c in (graph.get("cluster") or []) if int(c.get("groesse") or 0) >= 2])
    legende_hoehe = math.ceil(cluster_anzahl / 3) * 16 + 8 if cluster_anzahl else 0
    t.append(_netzwerk(graph, lx, ly + panel_kopf, spalte_w,
                       panel_h - panel_kopf - legende_hoehe))
    if legende_hoehe:
        schluessel, _ = _cluster_legende(
            graph, lx + 18, ly + panel_h - legende_hoehe + 6, spalte_w - 36)
        t.append(schluessel)

    # Rechte Tafel
    rx = rand + spalte_w + rand
    t.append(_kasten(rx, ly, spalte_w, panel_h))
    t.append(_text(rx + 18, ly + 22, "WHY THEY ARE LINKED", groesse=10, farbe=AKZENT))
    t.append(_text(rx + 18, ly + 42,
                   "The same wallets against the markets they actually share.",
                   groesse=11, farbe=GEDAEMPFT, familie=SANS))
    t.append(matrix_svg)

    ly_leg = ly + panel_kopf + matrix_h + 6
    for j, mk in enumerate(legende):
        titel = str(mk.get("markt", ""))
        if len(titel) > 58:
            titel = titel[:57] + "…"
        t.append(_text(rx + 18, ly_leg + j * 15, f"M{j + 1}", groesse=9.5, farbe=LEISE))
        t.append(_text(rx + 46, ly_leg + j * 15, titel, groesse=10,
                       farbe=GEDAEMPFT, familie=SANS))
        t.append(_text(rx + spalte_w - 60, ly_leg + j * 15,
                       f'{mk.get("seite", "")} · {mk.get("wallets", "")}w',
                       groesse=9.5, farbe="#C8F542"))

    t.append("</svg>")
    return "".join(t)
