# Copy wallet research separate from the paper ledger

Date: 2026-09-16. Status: implemented locally.

## Context and decision

Source-wallet success and paper-copy results measure different things. The
existing paper API loads the full order ledger, which has over 640,000 local
rows. Source-profile reads must also continue while a paper sync waits on
network requests with an open SQLite transaction.

`app/copy_intelligence.py` therefore stores watchlist source links, public
snapshots and up to 100 notices in a sibling `*.intelligence.sqlite` database.
The existing authenticated backup includes this file. `/api/copy/research`
reads only trader identities plus this snapshot, under the same private-desk
access policy as `/api/copy`. The existing full desk also includes intelligence.
No new dependencies or changes to execution/budget controls were needed.

## Import and operation

Run `python scripts/import_copy_watchlist.py <local-json-file> --refresh`.
The JSON is a list of objects with `wallet` and optional `sources` (HTTPS
X/Twitter status URLs). `--db` selects a non-default paper database. Each new
wallet receives the existing default paper account; existing labels, notes,
cash and pause states survive repeated imports. Personal selections belong
in ignored `data/`, not in a public seed file.

The copy daemon starts an independent research monitor. It checks scheduling
every 30 seconds. A completed read is refreshed after 300 seconds. The public
research route can also schedule a read. A SQLite lease prevents concurrent
API/daemon refreshes and expires after 15 minutes if the worker crashes.
Three HTTP workers use the existing public data clients and their timeouts.
The monitor runs only while the local host/daemon is running. No email,
browser push subscription, remote deployment or live trade is involved.

Start the web interface with `python api/server.py`, then open
`http://localhost:8787/#copy`. Wallet research is the default tab; Shared
markets holds current observations and the durable notification history.
Paper accounts remain under Traders and the other existing tabs.

## Definitions and limits

- Profiles: public Gamma `/public-profile?address=...`, following the
  [official endpoint](https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address).
- Performance: the canonical `wallet_scorecard`, including sample counts,
  resolution hit-rate interval and closed-position coverage warnings.
  Profitable-event winrate and resolution hit rate are distinct. Capped
  winner/loser tails cannot establish full-history performance.
- Sharpe is unavailable without a complete daily source-equity return series
  adjusted for deposits and withdrawals. No trade-PnL proxy is labelled Sharpe.
- Categories: existing title/category classifier, league event slugs and a
  labelled geopolitics keyword heuristic. Missing sports metadata uses the
  existing Gamma event-slug fallback. Unclassifiable data remains unknown.
- Entry style: purchase-dollar share at prices <=20% (longshot) or >=80%
  (favorite), using up to 500 recent activity rows. A >=60% share receives
  the corresponding style label; other profiles are mixed.
- Timing: observed buys >=7 days / <=24 hours before the scheduled Gamma
  endDate, with the available-observation denominator. This is not the actual
  resolution timestamp or a claim about the wallet's first lifetime entry.
- Overlap: at least two distinct watched wallets with positive net purchased
  shares within 24 hours in the same conditionId. Sells in that window offset
  buys; multiple outcomes are explicitly mixed/possible hedge. It is flow,
  not a current-holdings claim. Up to 500 activity rows can truncate that window.
- Notices: first observation, changed wallet/outcome membership, or return
  after disappearance. Repeated unchanged scans do not notify again. Partial
  failures preserve visibly stale prior observations and cannot create a
  spurious membership-change notice from a failed wallet read.

## Verification

Unit tests cover style denominators, sports fallback classification, distinct
wallets, opposing outcomes, sells, the 24-hour window, source validation,
idempotent import, JSON-safe canonical metrics, leases and ledger lock
isolation. API tests verify private access and forbid a full ledger read.
The Node rendering check covers escaping, unsafe URLs and missing metrics.
Browser checks exercise both new tabs, live data, source links and notices.
