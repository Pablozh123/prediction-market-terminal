# Polymarket Reddit Sentiment

**Kurs:** Data Wrangling & Engineering (FHNW)
**Thema:** Stimmungsanalyse von Reddit-Posts korreliert mit Polymarket-Vorhersagemärkten

---

## Was macht dieses Projekt?

- Lädt Polymarket-Märkte (z. B. „Will Bitcoin hit $150k?") via öffentlicher API
- Sucht passende Reddit-Posts (+ Kommentare) per Keyword-Extraktion
- Optional: filtert Posts semantisch nach Relevanz zur Markt-Frage (sentence-transformers)
- Analysiert Sentiment (VADER / FinBERT / Twitter-RoBERTa) und optional Stance Detection
- Korreliert Reddit-Stimmung mit Polymarket-Wahrscheinlichkeiten nach Kategorie
- Beantwortet F1, F1b, F2, F3 und F4 in Bericht und Analyse-Notebook
- Streamlit-Dashboard zur interaktiven Exploration

**Kein API-Key erforderlich** – Reddit wird über die öffentliche JSON-API oder optional PRAW abgefragt.

---

## Voraussetzungen

| Tool | Version |
|------|---------|
| Python | 3.10 oder neuer |
| pip | aktuell |

---

## Setup (Schritt für Schritt)

### 1. Projekt herunterladen / klonen

```bash
git clone https://github.com/Pablozh123/polymarket-reddit-sentiment.git
cd polymarket-reddit-sentiment
```

### 2. Virtuelle Umgebung erstellen und aktivieren

```bash
# Erstellen
python -m venv .venv

# Aktivieren – Windows (CMD)
.venv\Scripts\activate.bat

# Aktivieren – Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Aktivieren – macOS / Linux
source .venv/bin/activate
```

### 3. Pakete installieren

```bash
pip install -r requirements.txt
```

> **Hinweis:** `requirements.txt` enthält bereits `transformers`, `torch` und
> `sentence-transformers`. Der erste Aufruf der Transformer-Modelle lädt ca. 500–600 MB
> (einmalig, werden gecacht).

### 4. Jupyter-Kernel registrieren

Damit VS Code / Jupyter das richtige Python (aus der .venv) findet:

```bash
python -m ipykernel install --user --name polymarket --display-name "Python (polymarket)"
```

---

## Notebooks ausführen (Reihenfolge!)

Öffne VS Code → wähle Kernel `Python (polymarket)` → **Kernel → Restart & Run All**

| Notebook | Inhalt |
|----------|--------|
| `notebooks/01_EDA.ipynb` | Explorative Datenanalyse – Verteilungen, Sentiment, Zeitverlauf |
| `notebooks/02_Datenbereinigung.ipynb` | Missing Values (MCAR/MAR/MNAR), Duplikate, Winsorisierung → speichert `data/reddit_clean.csv` |
| `notebooks/03_Pipeline.ipynb` | `SentimentPipeline`-Klasse, Multi-Topic-Vergleich (2-Panel-Chart) |
| `notebooks/04_Analyse.ipynb` | F1-F4: Korrelation, Kategorie-Analyse, Subreddit-Test, Zeitmuster, Stance |

> **Tipp:** Notebook 02 muss vor 04 laufen, damit `data/reddit_clean.csv` existiert.

---

## Standalone-Scripts

Für Datenerhebung ohne Jupyter gibt es zwei direkt ausführbare Scripts:

### `run_bulk.py` — Schnelle Bulk-Analyse (empfohlen als Einstieg)

Analysiert bis zu 30 Märkte mit Twitter-RoBERTa, ohne Kommentare (ca. 5–10 Min.).
Schreibt `data/correlation_pairs_bulk.csv` und `data/posts_per_market.csv`.

```bash
.venv/Scripts/python.exe run_bulk.py        # Windows
python run_bulk.py                          # macOS / Linux
```

### `run_analysis.py` — Detailanalyse mit semantischer Filterung

Analysiert 20 Märkte mit Kommentaren und semantischem Post-Filter (ca. 15–30 Min.).
Schreibt `data/correlation_pairs.csv`.

```bash
.venv/Scripts/python.exe run_analysis.py   # Windows
python run_analysis.py                     # macOS / Linux
```

---

## Abgabe-Workflow für eine gute Note

Die benotete Abgabe soll im Bericht ohne Code verständlich sein. Deshalb gibt es zusätzlich zu
den Notebooks eine kompakte Berichtsschiene:

| Datei | Zweck |
|-------|-------|
| `docs/PROJEKTBERICHT.md` | Berichtsvorlage entlang der Bewertungskriterien A-G |
| `docs/DATA_DICTIONARY.md` | Erklärung der finalen CSV-Spalten |
| `docs/BEWERTUNGSCHECK.md` | Checkliste gegen das Bewertungsraster |
| `scripts/add_stance_scores.py` | Ergänzt `stance_score` fuer F4 auf Markt- und Post-Ebene |
| `scripts/generate_report_assets.py` | Erstellt druckreife Plots aus den CSV-Outputs |
| `scripts/render_final_report.py` | Rendert `reports/FINAL_REPORT.md` als HTML/PDF |

Empfohlene Reihenfolge für den finalen Run:

```bash
python run_bulk.py
python scripts/add_stance_scores.py
python scripts/compare_sentiment_models.py
python scripts/generate_report_assets.py
python scripts/audit_reddit_quality.py
python scripts/validate_outputs.py
python scripts/render_final_report.py
```

Der finale Abgabebericht liegt danach in `reports/FINAL_REPORT.pdf`. Demo-Daten sind nur ein
technischer Fallback; im finalen Hauptergebnis sollte `is_demo_market` überall `False` sein.

---

## Streamlit-App starten

```bash
python -m streamlit run app.py --server.headless=true
```

Öffne dann: [http://localhost:8501](http://localhost:8501)

---

## Projektstruktur

```
polymarket-reddit-sentiment/
├── app.py                    # Streamlit-Dashboard
├── run_bulk.py               # Bulk-Script: bis 30 Märkte, RoBERTa, schnell
├── run_analysis.py           # Detail-Script: 20 Märkte, Kommentare, Semantic Filter
├── requirements.txt          # Abhängigkeiten
├── src/
│   ├── reddit.py             # Reddit-Fetch (JSON-API + PRAW), Kommentare, Semantic Filter
│   ├── polymarket.py         # Polymarket API mit robustem Fallback
│   ├── market_metadata.py    # Taxonomie, Keywords, Polarity, stabile Felder
│   └── sentiment.py          # VADER / FinBERT / RoBERTa + semantic_filter() + Stance
├── notebooks/
│   ├── 01_EDA.ipynb          # EDA mit annotierten Histogrammen
│   ├── 02_Datenbereinigung.ipynb
│   ├── 03_Pipeline.ipynb     # 2-Panel-Themenvergleich
│   └── 04_Analyse.ipynb      # Kategorie-Korrelation, Zeitreihe nach Kategorie
└── data/                     # Wird zur Laufzeit erstellt (in .gitignore)
    ├── reddit_raw.csv
    ├── reddit_clean.csv
    ├── polymarket_clean.csv
    ├── correlation_pairs.csv         # run_analysis.py Output
    ├── correlation_pairs_bulk.csv    # run_bulk.py Output (Hauptlauf, RoBERTa)
    └── posts_per_market.csv          # run_bulk.py Output (Einzelposts, Stance nach Add-on)
```

---

## Sentiment-Modell wechseln

In `notebooks/04_Analyse.ipynb` → Cell 6 oder direkt in den Scripts:

```python
# Schnell (kein Download, VADER):
SENTIMENT_MODEL = sentiment.MODEL_VADER

# Finanztexte (~440 MB, einmalig):
SENTIMENT_MODEL = sentiment.MODEL_FINBERT

# Social Media / Reddit (~500 MB, einmalig) — Standard:
SENTIMENT_MODEL = sentiment.MODEL_ROBERTA
```

---

## Bekannte Einschränkungen

- **Polymarket API** ist von manchen Netzen nicht erreichbar → Demo-Datensatz wird automatisch als technischer Fallback markiert
- **Reddit Rate Limit:** Bei bis zu 30 Märkten × 25 Posts ca. 5–10 Min. Laufzeit (RoBERTa)
- **sentence-transformers** (`all-MiniLM-L6-v2`, ~80 MB) wird beim ersten `semantic_filter()`-Aufruf heruntergeladen
- **Plotly** rendert in VS Code Jupyter ohne Interactive-Widgets-Extension nicht → Notebooks nutzen Matplotlib
- **Kategorie-Daten:** Die Live-Polymarket-API liefert keine Kategorien zurück – Kategorien werden per Keyword-Matching aus dem Fragentext abgeleitet

## Aktueller finaler Run

Der zuletzt erzeugte Abgabe-Run basiert auf Live-Daten:

- 29 auswertbare Polymarket-Märkte aus 30 ausgewählten Live-Märkten
- 725 Reddit-Posts, 7 Subreddits, keine Demo-Märkte
- F1: Pearson r=+0.0791, Spearman rho=+0.1508
- F4: Stance Pearson r=-0.0855, Spearman rho=-0.1123
- Richtungsübereinstimmung: 44.8% (13 von 29 Märkten)
- Modellvergleich: VADER erreicht 27.6% Richtungstrefferquote, Twitter-RoBERTa 44.8%

Massgeblich fuer die Abgabe ist `reports/FINAL_REPORT.pdf`; die Notebooks sind reproduzierbare
Analyse- und Explorationsartefakte.
