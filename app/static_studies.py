"""Eine eigene, statische HTML-Seite je eingefrorener Studie.

Die Weboberflaeche ist hash-geroutet: jede Studie liegt unter
``/#research/microstructure/<id>`` und damit fuer einen Crawler auf derselben
URL wie alles andere. ``web/sitemap.xml`` sagt das ausdruecklich und listet nur
die echten Dokumente. Fuer eine oeffentliche Seite ist das zu wenig: die zwoelf
Befunde sind der Inhalt, und keiner davon hat eine Adresse.

Dieses Modul baut je Studie ein kleines, in sich geschlossenes Dokument mit
eigenem Titel, eigener Beschreibung und OG-Angaben. Der Inhalt kommt
ausschliesslich aus der veroeffentlichten Nutzlast ``microstructure.json``:
Frage, Verdikt, die Erklaerung in einfachen Worten, die Kennzahlen mit ihrer
Einheit, die Basis mit n und Fenster, dazu der Stand der Datei. Nichts wird
hier formuliert, was nicht in der Nutzlast steht, ausser der Navigation und
dem registrierten Hinweis aus ``data/claims.yaml``.

Streamlit-frei und ohne Abhaengigkeiten; ``scripts/build_static_site.py``
schreibt das Ergebnis nach ``dist/study/<slug>/index.html``.
"""

from __future__ import annotations

import html
import re
from typing import Any

from app import claims

#: Basisadresse der veroeffentlichten Seite. Nur fuer canonical und OG noetig,
#: jeder Verweis im Dokument selbst ist relativ.
SITE_URL = "https://marketintel.dev"
REPO_URL = "https://github.com/Pablozh123/prediction-market-terminal"
#: Unter welchem Pfad die Seiten liegen. Ein Segment, damit ein Dateiserver
#: ohne Regeln auskommt: /study/<slug>/index.html.
STUDY_DIR = "study"


def study_slug(study: Any) -> str:
    """URL-Segment einer Studie, identisch zum Anker der Oberflaeche."""

    roh = str((study or {}).get("id") or "").strip().lower()
    return re.sub(r"[^a-z0-9_-]+", "-", roh).strip("-")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _esc(value: Any) -> str:
    return html.escape(_text(value), quote=True)


def _zahl(wert: Any) -> str:
    if isinstance(wert, bool) or wert is None:
        return _text(wert)
    if isinstance(wert, int):
        return f"{wert:,}"
    if isinstance(wert, float):
        # Ganze Zahlen ohne Nachkommastellen, sonst so viele wie noetig.
        if abs(wert - round(wert)) < 1e-9:
            return f"{int(round(wert)):,}"
        return f"{wert:,.4g}"
    return _text(wert)


#: Basisfelder der Nutzlast in Worten. Dieselbe Reihenfolge und dieselben
#: Woerter wie die Studienseite der Oberflaeche, damit beide dieselbe Zeile
#: lesen.
BASIS_LABELS = (
    ("beobachtungen", "observations"),
    ("snapshots", "book snapshots"),
    ("tokens", "tokens"),
    ("maerkte", "markets"),
    ("paare", "pairs"),
    ("tage", "days"),
)


def basis_satz(basis: Any) -> str:
    """n und Zeitfenster einer Studie als eine Zeile, oder leer."""

    if not isinstance(basis, dict):
        return ""
    teile = []
    for schluessel, wort in BASIS_LABELS:
        wert = basis.get(schluessel)
        if wert:
            teile.append(f"{_zahl(wert)} {wort}")
    fenster = _text(basis.get("fenster"))
    if fenster:
        teile.append(fenster)
    return " · ".join(teile)


def beschreibung(study: Any) -> str:
    """Meta-Description: das Verdikt, auf Suchmaschinenlaenge gekuerzt."""

    verdikt = _text((study or {}).get("verdikt"))
    basis = basis_satz((study or {}).get("basis"))
    text = verdikt if not basis else f"{verdikt} Measured on {basis}."
    if len(text) <= 300:
        return text
    return text[:297].rstrip() + "..."


def seiten_titel(study: Any) -> str:
    frage = _text((study or {}).get("frage")) or _text((study or {}).get("id"))
    return f"{frage} — Market Intel"


def _zahlen_liste(study: Any) -> str:
    zahlen = (study or {}).get("zahlen")
    if not isinstance(zahlen, list) or not zahlen:
        return ""
    zeilen = []
    for eintrag in zahlen:
        if not isinstance(eintrag, dict):
            continue
        label = _esc(eintrag.get("label"))
        if not label:
            continue
        wert = _esc(_zahl(eintrag.get("wert")))
        einheit = _esc(eintrag.get("einheit"))
        hinweis = _esc(eintrag.get("hinweis"))
        zeilen.append(
            '<tr><th scope="row">' + label
            + (f'<span class="hint">{hinweis}</span>' if hinweis else "")
            + "</th><td>" + wert
            + (f" {einheit}" if einheit else "")
            + "</td></tr>"
        )
    if not zeilen:
        return ""
    return ('<table class="figures"><caption>Figures as published</caption><tbody>'
            + "".join(zeilen) + "</tbody></table>")


def _quellen(study: Any) -> str:
    links = []
    for feld, wort in (("report", "Full report"), ("modul", "Source module")):
        pfad = _text((study or {}).get(feld))
        if pfad:
            links.append(f'<a href="{REPO_URL}/blob/main/{_esc(pfad)}">{wort} ({_esc(pfad)})</a>')
    if not links:
        return ""
    return '<p class="sources">' + " · ".join(links) + "</p>\n"


#: Das Stylesheet der Seiten. Bewusst klein und ohne Abhaengigkeit: ein
#: Dokument, das ein Crawler und ein Mensch ohne JavaScript lesen koennen,
#: in hell und dunkel.
STYLE = (
    ":root{color-scheme:light dark;--bg:#F4F1EA;--fg:#141310;--muted:#4a463d;"
    "--line:#d9d4c7;--accent:#7a5c15}\n"
    "@media (prefers-color-scheme:dark){:root{--bg:#0B0B0A;--fg:#EAE6DC;"
    "--muted:#a5a094;--line:#2a2825;--accent:#D9A648}}\n"
    "*{box-sizing:border-box}\n"
    "body{margin:0;background:var(--bg);color:var(--fg);"
    "font:16px/1.6 system-ui,-apple-system,'Segoe UI',sans-serif}\n"
    "main{max-width:44rem;margin:0 auto;padding:3rem 1.25rem 4rem}\n"
    ".eyebrow{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.72rem;"
    "letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:0}\n"
    "h1{font-size:1.6rem;line-height:1.25;margin:.6rem 0 0;font-weight:600}\n"
    ".verdict{font-size:1.1rem;font-weight:600;margin:1.2rem 0 0}\n"
    ".plain{color:var(--muted);margin:1rem 0 0}\n"
    ".basis,.stamp,.sources,.note{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;"
    "font-size:.78rem;color:var(--muted)}\n"
    ".basis{margin:1.4rem 0 0}\n"
    "table.figures{width:100%;border-collapse:collapse;margin:1.6rem 0 0;font-size:.9rem}\n"
    "table.figures caption{text-align:left;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;"
    "font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);"
    "padding-bottom:.5rem}\n"
    "table.figures th,table.figures td{border-top:1px solid var(--line);padding:.5rem 0;"
    "text-align:left;font-weight:400}\n"
    "table.figures td{text-align:right;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}\n"
    ".hint{display:block;font-size:.75rem;color:var(--muted)}\n"
    "a{color:var(--accent)}\n"
    "hr{border:0;border-top:1px solid var(--line);margin:2.4rem 0 1.2rem}\n"
    "nav a{margin-right:1rem}"
)


def study_page_html(study: Any, stand_utc: str = "", site_url: str = SITE_URL) -> str:
    """Das vollstaendige Dokument einer Studie."""

    slug = study_slug(study)
    titel = seiten_titel(study)
    besch = beschreibung(study)
    basis = basis_satz((study or {}).get("basis"))
    basis_url = site_url.rstrip("/")
    kanonisch = f"{basis_url}/{STUDY_DIR}/{slug}/"
    hinweis = claims.disclaimer("research_tool_only", "en")
    einfach = _text((study or {}).get("einfach"))
    verdikt = _text((study or {}).get("verdikt"))
    frage = _text((study or {}).get("frage"))
    stand = _text(stand_utc)
    kopf = (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(titel)}</title>\n"
        f'<meta name="description" content="{_esc(besch)}">\n'
        '<meta name="robots" content="index,follow">\n'
        f'<link rel="canonical" href="{_esc(kanonisch)}">\n'
        '<meta property="og:type" content="article">\n'
        '<meta property="og:site_name" content="Market Intel">\n'
        f'<meta property="og:title" content="{_esc(titel)}">\n'
        f'<meta property="og:description" content="{_esc(besch)}">\n'
        f'<meta property="og:url" content="{_esc(kanonisch)}">\n'
        f'<meta property="og:image" content="{_esc(basis_url)}/icon-512.png">\n'
        '<meta name="twitter:card" content="summary">\n'
        f'<meta name="twitter:title" content="{_esc(titel)}">\n'
        f'<meta name="twitter:description" content="{_esc(besch)}">\n'
        f"<style>{STYLE}</style>\n"
        "</head>\n"
    )
    rumpf = (
        "<body>\n<main>\n"
        '<p class="eyebrow">Frozen study</p>\n'
        f"<h1>{_esc(frage)}</h1>\n"
        f'<p class="verdict">{_esc(verdikt)}</p>\n'
        + (f'<p class="plain">{_esc(einfach)}</p>\n' if einfach else "")
        + (f'<p class="basis">Data · {_esc(basis)}</p>\n' if basis else "")
        + _zahlen_liste(study)
        + "\n<hr>\n"
        + (f'<p class="stamp">Payload snapshot {_esc(stand)}. These figures are frozen; '
           "the interactive page reads the same file.</p>\n" if stand else "")
        + _quellen(study)
        + "<nav>\n"
        f'<a href="../../#research/microstructure/{_esc(slug)}">Open in the terminal</a>\n'
        '<a href="../../">All studies</a>\n'
        "</nav>\n"
        f'<p class="note">{_esc(hinweis)}</p>\n'
        "</main>\n</body>\n</html>\n"
    )
    return kopf + rumpf


def study_pages(payload: Any, site_url: str = SITE_URL) -> dict[str, str]:
    """Slug auf Dokument, fuer jede Studie der Nutzlast mit einer id."""

    if not isinstance(payload, dict):
        return {}
    studien = payload.get("studien")
    if not isinstance(studien, list):
        return {}
    stand = _text(payload.get("stand_utc"))[:10]
    seiten: dict[str, str] = {}
    for studie in studien:
        if not isinstance(studie, dict):
            continue
        slug = study_slug(studie)
        if not slug or slug in seiten:
            continue
        seiten[slug] = study_page_html(studie, stand, site_url)
    return seiten


def sitemap_mit_studien(sitemap_xml: str, slugs: list[str], lastmod: str,
                        site_url: str = SITE_URL) -> str:
    """Die Studien-URLs in eine vorhandene sitemap.xml einhaengen.

    Die Datei im Repo listet nur die echten Dokumente, weil die Hash-Routen
    keine eigenen URLs sind. Die Studienseiten sind welche, also gehoeren sie
    hinein. Eingehaengt wird vor dem schliessenden ``</urlset>``; steht ein
    Eintrag schon drin, kommt er nicht ein zweites Mal.
    """

    if "</urlset>" not in sitemap_xml:
        return sitemap_xml
    basis_url = site_url.rstrip("/")
    neue = []
    for slug in slugs:
        loc = f"{basis_url}/{STUDY_DIR}/{slug}/"
        if loc in sitemap_xml:
            continue
        neue.append(
            "  <url>\n"
            f"    <loc>{loc}</loc>\n"
            f"    <lastmod>{html.escape(lastmod)}</lastmod>\n"
            "    <changefreq>yearly</changefreq>\n"
            "    <priority>0.6</priority>\n"
            "  </url>\n"
        )
    if not neue:
        return sitemap_xml
    return sitemap_xml.replace("</urlset>", "".join(neue) + "</urlset>")
