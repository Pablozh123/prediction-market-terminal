"""Portable, source-backed additions to the frozen microstructure studies.

All figures come from the checked-in research snapshot. The original research
was run in the projects named there; this module only prepares display cards.
"""

from __future__ import annotations

import json
from pathlib import Path


SNAPSHOT = "docs/research/research_updates_2026-10-12.json"
ANALYSIS_TITLES = {
    "gemessen": "What was measured",
    "wie": "How",
    "daten": "On what data",
    "entscheidung": "What would change the decision",
}
INTERPRETATION_TITLES = {
    "lesart": "What it suggests",
    "gegenlesart": "What else fits the same numbers",
    "grenze": "What this cannot tell you",
}


def _money(value: float) -> str:
    return f"{value:+.2f}"


def _number(label: str, value: int | float, unit: str, note: str) -> dict:
    return {"label": label, "wert": value, "einheit": unit, "hinweis": note}


def _card(
    *, root: Path, id: str, question: str, verdict: str, verdict_type: str,
    analysis: tuple[str, str, str, str], simple: str,
    interpretation: tuple[str, str, str], report: str, module: str,
    window: str, base: dict, numbers: list[dict], chart: dict,
    details: dict, tags: list[str], published: str,
) -> dict:
    for path in (report, module, SNAPSHOT):
        if not (root / path).is_file():
            raise FileNotFoundError(root / path)
    return {
        "id": id, "frage": question, "verdikt": verdict,
        "verdikt_art": verdict_type,
        "analyse": [
            {"schluessel": key, "titel": ANALYSIS_TITLES[key], "text": text}
            for key, text in zip(ANALYSIS_TITLES, analysis, strict=True)
        ],
        "einfach": simple,
        "interpretation": [
            {"art": kind, "titel": INTERPRETATION_TITLES[kind], "text": text}
            for kind, text in zip(INTERPRETATION_TITLES, interpretation, strict=True)
        ],
        "report": report, "modul": module,
        "module_role": "publication" if module == "app/research_updates.py" else "analysis",
        "basis": {"fenster": window, **base},
        "zahlen": numbers, "diagramm": chart, "details": details,
        "schlagworte": tags,
        "daten": [{"format": "JSON", "path": SNAPSHOT}],
        "status": "recent", "published_at_utc": published,
    }


def build_updates(root: Path) -> list[dict]:
    """Build six cards using only versioned files beneath *root*."""
    root = Path(root)
    source = json.loads((root / SNAPSHOT).read_text(encoding="utf-8"))
    published = source["published_at_utc"]
    f, e, m = source["cex_forward"], source["cex_execution"], source["mm_queue"]
    s, a, fed = source["source_speed"], source["arb_funnel"], source["fed"]
    f250 = f["baseline"]["250"]
    forward_rows = [
        [f"{delay} ms", row["assessable_blocks"], row["closed_trades"],
         row["open_positions"], _money(row["net_pnl"]), _money(row["floor_pnl"])]
        for delay, row in f["baseline"].items()
    ]
    exec_rows = [
        [f"{delay}/{delay} ms", row["closed_trades"], row["open_positions"],
         _money(row["realized_pnl"]), _money(row["floor_pnl"])]
        for delay, row in e["baseline"].items()
    ]
    mm_rows = [
        [name, f"{delay} ms", row["fills"], _money(row["sum_usd"]),
         _money(row["without_rebates_usd"]),
         f"{_money(row['daily_ci_usd'][0])} to {_money(row['daily_ci_usd'][1])}"]
        for name in ("queue_back", "queue_front")
        for delay, row in m[name].items()
    ]
    fed_rows = [
        [f"T-{days}", row["n"], f"{row['polymarket_brier']:.5f}",
         f"{row['fedwatch_brier']:.5f}"]
        for days, row in fed["evaluation"].items()
    ]
    return [
        _card(
            root=root, id="cex-leadlag-forward",
            question="Does a CEX impulse survive execution delay in a fresh paper window?",
            verdict="Open. The 250 ms replay is positive, but 500 ms and 1,000 ms replays are negative under assumed execution delays.",
            verdict_type="offen",
            analysis=(
                "The unchanged CEX lead and lag paper rule was replayed across completed hourly blocks at several assumed entry delays.",
                "Each block and variant restarts with 100 USD and 10 shares. Closed-trade net includes fees; the floor subtracts open-entry costs.",
                f"The frozen forward snapshot covers {f['completed_hour_blocks']} full hourly blocks and {f['qualified_impulses']} time-separated qualifying impulses.",
                "A practical yes needs independently measured order and fill timing and a further untouched window that survives those delays and open-position risk.",
            ),
            simple=(f"Across {f['completed_hour_blocks']} hourly blocks and {f['qualified_impulses']} qualifying impulses, "
                    f"the 250 ms baseline closed {f250['closed_trades']} trades for {_money(f250['net_pnl'])} USD net. "
                    f"Its open-position loss floor is {_money(f250['floor_pnl'])} USD. At 500 and 1,000 ms, "
                    f"closed-trade net falls to {_money(f['baseline']['500']['net_pnl'])} and "
                    f"{_money(f['baseline']['1000']['net_pnl'])} USD. These are separate paper scenarios, not one portfolio."),
            interpretation=(
                "The sign change across the assumed delays makes execution speed central to this signal's practical value.",
                "The positive 250 ms sum can still reflect optimistic fill assumptions and an unusually favourable short market window.",
                "No real order or fill times were observed, and open positions can change the eventual result after this snapshot.",
            ),
            report="docs/research/update_cex_leadlag_forward_2026-10-12.md", module="app/research_updates.py",
            window=f["window"], base={"stundenbloecke": f["completed_hour_blocks"], "impulse": f["qualified_impulses"]},
            numbers=[
                _number("250 ms closed-trade net", f250["net_pnl"], "USD", "Paper replay; closed trades after fees"),
                _number("250 ms open-risk floor", f250["floor_pnl"], "USD", "Subtracts open entry costs"),
                _number("Qualifying impulses", f["qualified_impulses"], "signals", "At least 60 seconds apart"),
            ],
            chart={"art": "vergleich", "titel": "Baseline closed-trade net by assumed entry delay", "einheit": "USD",
                   "punkte": [{"label": f"{delay} ms", "wert": row["net_pnl"]} for delay, row in f["baseline"].items()]},
            details={"titel": "Independent baseline replay scenarios", "spalten": ["Delay", "Blocks", "Closed", "Open", "Net USD", "Floor USD"],
                     "zeilen": forward_rows, "hinweis": "Each block and delay starts with separate 100 USD paper capital. No measured fills."},
            tags=["CEX", "lead-lag", "paper replay", "latency"], published=published,
        ),
        _card(
            root=root, id="cex-execution-latency",
            question="What happens when both entry and exit are delayed?",
            verdict="Open. The six-block baseline changes from positive at 350/350 ms to negative at 500/500 and 1,000/1,000 ms.",
            verdict_type="offen",
            analysis=(
                "A separate sensitivity replay delayed both the simulated entry and the intended exit of the existing CEX rules.",
                "The original six completed hours were replayed with fixed 350/350, 500/500 and 1,000/1,000 ms scenarios; rules and budgets stayed fixed.",
                f"These {e['completed_hour_blocks']} hours were already seen, and the unchanged 250 ms arm had only {e['qualified_impulses_250ms']} qualifying impulses.",
                "An independent test with measured order and fill times, enough qualifying impulses and accounted open positions would be needed for a practical claim.",
            ),
            simple=(f"With entry and exit each delayed 350 ms, the baseline earned "
                    f"{_money(e['baseline']['350']['realized_pnl'])} USD on closed trades across six blocks. "
                    f"At 500/500 ms it returned {_money(e['baseline']['500']['realized_pnl'])} USD; "
                    f"at 1,000/1,000 ms it returned {_money(e['baseline']['1000']['realized_pnl'])} USD. "
                    "All three are assumptions on previously seen data, with separate 100 USD resets per block."),
            interpretation=(
                "Adding exit latency can erase a paper advantage even when the entry rule and recorded books are unchanged.",
                "Different delays also alter which later signals remain executable, so the change is not solely the exit price of identical trades.",
                "Fixed delays are not measured order times; the six reused hours and open positions do not establish live profitability.",
            ),
            report="docs/research/update_cex_execution_latency_2026-10-12.md", module="app/research_updates.py",
            window=e["window"], base={"stundenbloecke": e["completed_hour_blocks"], "impulse": e["qualified_impulses_250ms"]},
            numbers=[_number(f"{d}/{d} ms closed-trade net", row["realized_pnl"], "USD", "Six reused paper blocks") for d, row in e["baseline"].items()],
            chart={"art": "vergleich", "titel": "Baseline net with assumed entry and exit delay", "einheit": "USD",
                   "punkte": [{"label": f"{d}/{d} ms", "wert": row["realized_pnl"]} for d, row in e["baseline"].items()]},
            details={"titel": "Baseline replay with delayed exit", "spalten": ["Entry/exit", "Closed", "Open", "Net USD", "Floor USD"],
                     "zeilen": exec_rows, "hinweis": "Already seen hours; delays are scenarios, not observed fills."},
            tags=["CEX", "execution", "exit delay", "paper replay"], published=published,
        ),
        _card(
            root=root, id="mm-queue-forward",
            question="Does the market-making quote rule survive queue and refresh delay in the September test window?",
            verdict="No for practical execution: the registered zero-delay simulation is positive, while both 250 ms queue scenarios are strongly negative.",
            verdict_type="nein",
            analysis=(
                "A frozen quote rule was tested on fourteen days under queue-front and queue-back fill models, with zero and 250 ms refresh delay.",
                "The original market-making study simulated daily inventories and reported sums, fill counts and bootstrap intervals for the daily mean.",
                f"The {m['days_with_data']} dates from the separate market-making project include a {m['gap_hours']:.3f}-hour recording gap.",
                "The zero-delay primary threshold was met internally, but a practical yes would require funded limits and verified latency, queue position and fills.",
            ),
            simple=(f"In the conservative queue-back model, zero delay gave "
                    f"{_money(m['queue_back']['0']['sum_usd'])} USD over {m['queue_back']['0']['fills']} simulated fills. "
                    f"At 250 ms, it gave {_money(m['queue_back']['250']['sum_usd'])} USD over "
                    f"{m['queue_back']['250']['fills']} simulated fills. The front-of-queue model also flips sign. "
                    "These are model sums with daily inventory resets and no shared capital budget, not account returns."),
            interpretation=(
                "The large sign reversal is consistent with stale quotes being selected after the market moves.",
                "The zero-delay result may be inflated by unverified queue priority, assumed rebates and marking leftover inventory at the mid.",
                "A 29.746-hour data gap and no hard portfolio budget limit prevent treating the sums as an executable return.",
            ),
            report="docs/research/update_mm_queue_forward_2026-10-12.md", module="app/research_updates.py",
            window=m["window"], base={"tage": m["days_with_data"], "datenluecke_stunden": m["gap_hours"]},
            numbers=[
                _number("Queue back, 0 ms", m["queue_back"]["0"]["sum_usd"], "USD", "Simulated sum including assumed rebates"),
                _number("Queue back, 250 ms", m["queue_back"]["250"]["sum_usd"], "USD", "Simulated sum including assumed rebates"),
                _number("Largest between-file gap", m["gap_hours"], "hours", "Recorded book coverage gap"),
            ],
            chart={"art": "vergleich", "titel": "Queue-back simulated sums by refresh delay", "einheit": "USD",
                   "punkte": [{"label": f"{d} ms", "wert": row["sum_usd"]} for d, row in m["queue_back"].items()]},
            details={"titel": "Frozen quote rule across queue and delay models", "spalten": ["Queue", "Delay", "Fills", "Sum incl. rebates USD", "Without rebates USD", "95% daily-mean CI USD"],
                     "zeilen": mm_rows, "hinweis": "Independent daily resets, midpoint marks and no common portfolio budget. The module link is this publication adapter, not the original simulator."},
            tags=["market making", "queue", "latency", "simulation"], published=published,
        ),
        _card(
            root=root, id="source-speed-depth",
            question="Did faster ISW or DeepState detection reveal a tradeable information edge?",
            verdict="No verified speed edge. One Bilytske quote was tiny, and the 100 USD depth simulation was negative.",
            verdict_type="nein",
            analysis=(
                "The source study compared detection times, public trades and recorded bid-ask depth for matched Ukraine event markets.",
                "Historical books were aligned with each signal and later trades; a size-aware 100 USD entry and observed exit were simulated.",
                f"Of {s['rows']} event-market rows, {s['rows_with_book']} had a usable book at detection between late September and 11 October.",
                "A yes needs repeated qualifying market events, depth for realistic size and observed fills before a later public reaction.",
            ),
            simple=(f"The Bilytske source was detected {s['bilytske_lead_seconds']} seconds before a related Telegram post, "
                    f"but its best ask showed only {s['best_ask_shares']} shares costing {s['best_ask_usd']:.2f} USD. "
                    f"A 100 USD depth-aware entry would have returned {_money(s['simulated_100usd_pnl_24h'])} USD "
                    f"after 24 hours. Only {s['rows_with_book']} of {s['rows']} event-market rows had a usable initial book."),
            interpretation=(
                "A faster source timestamp did not translate into enough displayed depth for the tested 100 USD size.",
                "The later buy could have unrelated causes, and the same small ask had appeared earlier; timing alone does not prove causation.",
                "Displayed book depth is not an own fill, and an event matched by place name may fail the market's actual resolution rule.",
            ),
            report="docs/research/update_source_speed_depth_2026-10-12.md", module="app/research_updates.py",
            window=s["window"], base={"ereignis_markt_zeilen": s["rows"], "mit_buch": s["rows_with_book"]},
            numbers=[
                _number("Lead over Telegram", s["bilytske_lead_seconds"], "seconds", "One Bilytske case"),
                _number("Displayed best-ask cost", s["best_ask_usd"], "USD", "Only five shares"),
                _number("100 USD simulated 24h result", s["simulated_100usd_pnl_24h"], "USD", "Depth-aware, not a filled trade"),
            ],
            chart={"art": "vergleich", "titel": "Rows with an initial usable book", "einheit": "event-market rows",
                   "punkte": [{"label": "All rows", "wert": s["rows"]}, {"label": "Usable book", "wert": s["rows_with_book"]}]},
            details={"titel": "Bilytske case and coverage", "spalten": ["Measure", "Value", "Meaning"],
                     "zeilen": [["Source lead", f"{s['bilytske_lead_seconds']} s", "Against related Telegram post"],
                                ["Best ask", f"{s['best_ask_shares']} shares / {s['best_ask_usd']:.2f} USD", "Displayed depth, not own fill"],
                                ["100 USD after 24 h", f"{_money(s['simulated_100usd_pnl_24h'])} USD", "Depth-aware simulation"]],
                     "hinweis": "The module link is this publication adapter; the original source research was run in another project."},
            tags=["source speed", "order book", "market depth", "Ukraine"], published=published,
        ),
        _card(
            root=root, id="arb-validation-funnel",
            question="How many raw arbitrage scans survived validation and reached paper trading?",
            verdict="No validated opportunity reached paper trading in this 24-hour scan window.",
            verdict_type="nein",
            analysis=(
                "A daily bot report counted scan cycles, raw scanner candidates, validation outcomes and paper fires for three arbitrage families.",
                "The scanner's raw counts were compared with its validated and paper stages; counts are repeated scan occurrences, not independent trades.",
                f"The 24-hour report records {a['scan_ok']} successful cycles of {a['scan_total']} attempted, with {a['scan_failed']} failed cycles.",
                "A tradeable claim would require a validated, rules-equivalent candidate, executable quotes and a controlled paper fill before any PnL statement.",
            ),
            simple=(f"The bot completed {a['scan_ok']} of {a['scan_total']} scan cycles; {a['scan_failed']} failed. "
                    f"It saw {a['cross_raw']} raw cross-venue, {a['neg_risk_raw']} raw negative-risk and "
                    f"{a['within_raw']} raw within-market candidates. Zero passed validation and zero became a paper trade. "
                    "These are repeated scan counts, not separate available opportunities or realised profit."),
            interpretation=(
                "The validation funnel rejected every raw candidate, so the observed scan output does not support an executable arbitrage claim.",
                "The high raw count can mostly reflect repeated quotes and rule mismatches; it is not a count of unique chances.",
                "Failed scan cycles limit coverage, and forward quote replay does not establish realised PnL or actual fills.",
            ),
            report="docs/research/update_arb_validation_funnel_2026-10-12.md", module="app/research_updates.py",
            window=a["window"], base={"scanzyklen": a["scan_total"], "erfolgreich": a["scan_ok"]},
            numbers=[
                _number("Cross-venue raw", a["cross_raw"], "scan hits", "Repeated scanner occurrences"),
                _number("Negative-risk raw", a["neg_risk_raw"], "scan hits", "Repeated scanner occurrences"),
                _number("Validated", a["validated"], "candidates", "Across the three listed families"),
            ],
            chart={"art": "vergleich", "titel": "Raw scanner hits and validated output", "einheit": "scan occurrences",
                   "punkte": [{"label": "Cross raw", "wert": a["cross_raw"]},
                              {"label": "Neg-risk raw", "wert": a["neg_risk_raw"]},
                              {"label": "Within raw", "wert": a["within_raw"]},
                              {"label": "Validated", "wert": a["validated"]}]},
            details={"titel": "Daily validation funnel", "spalten": ["Family", "Raw scan hits", "Validated", "Paper"],
                     "zeilen": [["Cross venue", a["cross_raw"], 0, 0], ["Negative risk", a["neg_risk_raw"], 0, 0],
                                ["Within market", a["within_raw"], 0, 0]],
                     "hinweis": "Raw hits are scan occurrences; the module link is this publication adapter, not the original bot."},
            tags=["arbitrage", "validation", "paper trading"], published=published,
        ),
        _card(
            root=root, id="fed-forecast-comparison",
            question="Did Polymarket or FedWatch forecast FOMC decisions more accurately at fixed horizons?",
            verdict="Open. The lower Brier score switches by horizon across only five meetings, so there is no overall winner.",
            verdict_type="offen",
            analysis=(
                "Polymarket and archived FedWatch probability distributions were compared with the realised FOMC decision at three fixed horizons.",
                "For each meeting and horizon, the published comparison calculates multiclass Brier scores from the stored probabilities.",
                f"The checked-in dataset contains {fed['n_meetings']} meetings, from 18 March through 16 September 2026.",
                "A broad ranking needs more settled meetings and aligned observation times and execution-aware market prices across horizons.",
            ),
            simple=(f"Across {fed['n_meetings']} meetings, mean Brier scores at T-30 were "
                    f"{fed['evaluation']['30']['polymarket_brier']:.3f} for Polymarket and "
                    f"{fed['evaluation']['30']['fedwatch_brier']:.3f} for FedWatch. At T-7 they were "
                    f"{fed['evaluation']['7']['polymarket_brier']:.3f} and "
                    f"{fed['evaluation']['7']['fedwatch_brier']:.3f}; at T-1, "
                    f"{fed['evaluation']['1']['polymarket_brier']:.3f} and "
                    f"{fed['evaluation']['1']['fedwatch_brier']:.3f}. Lower is better, and the ordering changes with the horizon."),
            interpretation=(
                "FedWatch scores lower at the earlier horizons in this sample, while Polymarket scores lower one day before the decision.",
                "A single September rate hike and different timestamp conventions can materially shift a five-meeting average.",
                "Polymarket observations are hourly market prices rather than executable bid-ask quotes, and five meetings cannot settle a general ranking.",
            ),
            report="docs/research/fed_comparison_2026-09-24.md", module="app/fed_comparison.py",
            window=fed["window"], base={"sitzungen": fed["n_meetings"]},
            numbers=[
                _number("Polymarket Brier, T-30", fed["evaluation"]["30"]["polymarket_brier"], "score", "Lower is better"),
                _number("FedWatch Brier, T-30", fed["evaluation"]["30"]["fedwatch_brier"], "score", "Lower is better"),
                _number("Meetings", fed["n_meetings"], "decisions", "Same five at each horizon"),
            ],
            chart={"art": "vergleich", "titel": "Mean Brier score by horizon and source", "einheit": "Brier score",
                   "punkte": [{"label": f"T-{d} Polymarket", "wert": row["polymarket_brier"]} for d, row in fed["evaluation"].items()]
                   + [{"label": f"T-{d} FedWatch", "wert": row["fedwatch_brier"]} for d, row in fed["evaluation"].items()]},
            details={"titel": "Same five meetings at three horizons", "spalten": ["Horizon", "Meetings", "Polymarket Brier", "FedWatch Brier"],
                     "zeilen": fed_rows, "hinweis": "Lower is better. The source dataset is public/data/fed_comparison.json; neither series is a realised trading return."},
            tags=["Federal Reserve", "forecast", "calibration", "Brier score"], published=published,
        ),
    ]
