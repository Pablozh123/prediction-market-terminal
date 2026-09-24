"""Side-by-side source and paper positions, without network work on page reads."""
from datetime import datetime, timezone


def comparison(conn, profiles):
    source = {(r["wallet"], r["asset"]): dict(r) for r in conn.execute(
        "SELECT * FROM source_positions WHERE shares>0")}
    for row in source.values():
        row.update(stale=True, mark_source="last observed source trade / baseline")
    for wallet, profile in profiles.items():
        if "positions" not in profile or "positions" in profile.get("errors", {}):
            continue
        source = {key: row for key, row in source.items() if key[0] != wallet}
        for row in profile["positions"]:
            source[(wallet, str(row["asset"]))] = {
                **row, "shares": row.get("size"), "last_price": row.get("current_price"),
                "updated_at": profile.get("snapshot_at"),
                "stale": profile.get("stale", False) or not profile.get("snapshot_at") or (datetime.now(timezone.utc)-datetime.fromisoformat(profile["snapshot_at"].replace("Z", "+00:00"))).total_seconds() > 600,
                "mark_source": "source wallet position snapshot",
            }
    paper = {(r["trader_wallet"], r["asset"]): dict(r) for r in conn.execute(
        "SELECT * FROM positions WHERE shares>0")}
    executions = {}
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='copy_executions'").fetchone():
        for row in conn.execute("""SELECT o.source_wallet, o.asset, o.source_price, o.copy_price, o.source_side, o.reason, e.observed_at, e.filled_at,
            e.latency_seconds, e.desired_size, e.filled_size FROM copy_executions e
            JOIN paper_orders o USING(dedup_key)
            WHERE e.rowid = (SELECT x.rowid FROM copy_executions x
                WHERE x.wallet=e.wallet AND x.asset=e.asset ORDER BY x.observed_at DESC, x.rowid DESC LIMIT 1)"""):
            executions.setdefault((row["source_wallet"], row["asset"]), dict(row))
    output = {}
    for wallet, asset in sorted(source.keys() | paper.keys()):
        original, copied = source.get((wallet, asset), {}), paper.get((wallet, asset), {})
        last = executions.get((wallet, asset), {})
        mark = original.get("last_price")
        if mark is None:
            mark = copied.get("last_price")
        mark_at = original.get("updated_at") or copied.get("updated_at")
        mark_source = original.get("mark_source", "last paper observation")
        if original.get("stale", True) and copied.get("updated_at", "") > original.get("updated_at", ""):
            mark = copied.get("last_price")
            mark_at = copied.get("updated_at")
            mark_source = "last paper observation"
        source_size, copy_size = original.get("shares", 0), copied.get("shares", 0)
        source_entry, copy_entry = original.get("avg_price"), copied.get("avg_price")
        output.setdefault(wallet, []).append({
            "asset": asset, "title": original.get("title") or copied.get("title") or asset,
            "outcome": original.get("outcome") or copied.get("outcome"),
            "source_size": source_size, "copy_size": copy_size,
            "source_entry": source_entry, "copy_entry": copy_entry, "mark": mark,
            "source_pnl": (mark-source_entry)*source_size if mark is not None and source_entry is not None else None,
            "copy_pnl": mark*copy_size-copied["cost_basis"] if mark is not None and copied else None,
            "mark_at": mark_at,
            "source_stale": original.get("stale", True),
            "mark_source": mark_source,
            "last_execution": last or None,
        })
    return output
