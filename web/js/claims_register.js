// GENERATED FILE. Do not edit, and do not write caveat wording here.
//
// Source of record: data/claims.yaml. Regenerate with
//
//     python scripts/publish_claims.py
//
// and scripts/lint_claims.py fails when this file and the register disagree.
//
// The register is compiled into the bundle rather than fetched because a
// caveat that arrives with a response is a caveat that is missing while the
// response is on its way, and absent entirely on a static file host with no
// API behind it. web/js/claims.js reads this object and merges a newer
// register from /api/claims when one answers.

export const REGISTER = {
  "version": 1,
  "updated": "2026-08-28",
  "disclaimers": {
    "score_generic": {
      "de": "Kennzahl aus oeffentlichen On-Chain-Daten. Information, keine Anlageberatung.",
      "en": "Metric from public on-chain data. Information, not investment advice."
    },
    "diagnostic_not_advice": {
      "de": "Diagnose des bisherigen Records, keine Handlungsempfehlung.",
      "en": "A diagnostic of the past record, not a recommendation to act."
    },
    "past_not_forecast": {
      "de": "Beschreibt abgeschlossene Trades, keine Prognose kuenftiger Ergebnisse.",
      "en": "Describes settled trades; it does not project future results."
    },
    "thin_sample": {
      "de": "Stichprobe zu klein fuer ein Urteil. Die Zahl bleibt sichtbar, ist aber nur ein Hinweis.",
      "en": "Sample too small for a verdict. The number stays visible but reads as a hint only."
    },
    "modeled_not_realized": {
      "de": "Modellierter Wert, zum Emit-Zeitpunkt eingefroren; kein realisierter Gewinn.",
      "en": "Modeled value frozen at emit time; not realized profit."
    },
    "wallet_reader_caveat": {
      "de": "Liest ausschliesslich oeffentliche, aufgeloeste Polymarket-Positionen, nur lesend: es wird nichts platziert. Diagnose des bisherigen Records, keine Anlageberatung.",
      "en": "Reads public resolved Polymarket positions only, read-only: nothing is placed. A diagnostic of the past record, not investment advice."
    },
    "leaderboard_caveat": {
      "de": "Rohe PnL-Raenge fuehren in die Irre: Legs blaehen Win-Rates auf, Winner-only-Feeds verstecken Verluste. Der Skill-Read je Wallet korrigiert beides.",
      "en": "Raw PnL ranks mislead: legs inflate win rates and winner-only feeds hide losses. The per-wallet skill read corrects both."
    },
    "screen_not_proof": {
      "de": "Verhaltens-Screen nach bestem Bemuehen ueber oeffentliche Handelsdaten: Rechercheanlaesse, keine juristischen Feststellungen. Ein Flag ist ein Pruefsignal, kein Beweis fuer Fehlverhalten.",
      "en": "A best-effort behavioural screen on public trade data: research leads, not legal findings. A flag is a review signal, not proof of wrongdoing."
    },
    "backtest_modeled": {
      "de": "Simulation zu historischen Preisen mit Fee- und Slippage-Annahmen. Modellierte Werte, keine realisierten Ergebnisse.",
      "en": "A simulation at historical prices with fee and slippage assumptions. Modeled values, not realized results."
    },
    "signal_ledger_caveat": {
      "de": "Deskriptiver Record der emittierten Alerts mit eingefrorenem Modell-PnL. Kein Qualitaetsversprechen fuer kuenftige Signale.",
      "en": "A descriptive record of emitted alerts with modeled PnL frozen at emit price. Not a quality promise for future signals."
    },
    "research_tool_only": {
      "de": "Nur ein Forschungswerkzeug: keine Anlageberatung, keine Orderausfuehrung, keine Verbindung zu einer Venue. Oeffentliche Polymarket- und Kalshi-Daten, ohne Gewaehr.",
      "en": "Research tool only: no investment advice, no order placement, no venue affiliation. Public Polymarket and Kalshi data, provided as-is."
    },
    "no_signup_no_orders": {
      "de": "Keine Anmeldung, keine Orders, reine Recherche.",
      "en": "No signup, no orders placed, pure research."
    },
    "site_footer_readonly": {
      "de": "Nur lesend. Keine Orders. Oeffentliche Polymarket- & Kalshi-Daten.",
      "en": "Read-only. No orders placed. Public Polymarket & Kalshi data."
    },
    "paper_desk_only": {
      "de": "Papierkonto: jede Order wird lokal zum gedruckten Preis gebucht. Nichts geht an eine Venue.",
      "en": "Paper desk: every order is booked in a local paper book at the printed price. Nothing is sent to a venue."
    },
    "paper_log_no_return_claim": {
      "de": "Nur Entscheidungen und beste Buchpreise: keine Fills, keine Wallet-Daten, keine Renditebehauptung.",
      "en": "Decisions and best book prices only: no fills, no wallet data, no return claim."
    },
    "parity_not_arbitrage": {
      "de": "Preisluecken sind Rechercheanlaesse, nicht zwangslaeufig Arbitrage. Aufloesungsregeln, Gebuehren, Settlement-Zeitpunkte und Zugangsbeschraenkungen koennen eine scheinbare Paritaet brechen.",
      "en": "Price gaps are research leads, not guaranteed arbitrage. Resolution rules, fees, settlement timing, and access restrictions can break apparent parity."
    },
    "verification_not_signal": {
      "de": "Empfehlungen sind Pruefschritte (beobachten, Quelle pruefen, an einen Menschen eskalieren), keine Kauf- oder Verkaufssignale.",
      "en": "Recommendations are verification steps (watch, check the source, escalate to a human), not buy or sell signals."
    },
    "daily_run_descriptive": {
      "de": "Deskriptive Forschungsartefakte aus einem taeglichen, deterministischen Review-Lauf ueber oeffentliche Marktdaten.",
      "en": "Descriptive research artifacts from a daily, deterministic review run over public market data."
    },
    "daily_run_no_advice": {
      "de": "Keine Finanz- oder Anlageberatung. Keine Renditebehauptung. Pipeline-Eintraege sind beobachtend/Papier.",
      "en": "No financial or investment advice. No return claim. Pipeline entries are observing/paper."
    },
    "daily_run_privacy": {
      "de": "Keine Wallet-Adressen, keine Schluessel, keine Prompts. Audit nur als Hashes und Zaehler.",
      "en": "No wallet addresses, no keys, no prompts. Audit as hashes and counters only."
    }
  }
};
