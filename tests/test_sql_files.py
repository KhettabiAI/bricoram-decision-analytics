"""Every analysis in sql/ must (1) be allowed by the guard hook, so Claude Code can
run it as-is, and (2) reconcile against an independent single-table computation.
The Stop hook runs this file before Claude may finish."""
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hooks"))
import sql_guard  # noqa: E402  (path set above)

SQL_DIR = ROOT / "sql"
WINDOW = ("2026-09-01", "2026-10-21")


def run_file(conn, name):
    cur = conn.execute((SQL_DIR / name).read_text(encoding="utf-8"))
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def scalar(conn, q):
    return conn.execute(q).fetchone()[0]


@pytest.mark.parametrize("path", sorted(SQL_DIR.glob("*.sql")), ids=lambda p: p.name)
def test_guard_allows_every_analysis(path):
    assert sql_guard.check_sql(path.read_text(encoding="utf-8")) is None


def test_00_profiling(ro):
    rows = {r["view_name"]: r for r in run_file(ro, "00_profiling.sql")}
    assert len(rows) == 6
    assert all(r["n_rows"] > 0 for r in rows.values())
    assert all(r["unmapped_codes"] == 0 for r in rows.values())
    assert rows["v_requests"]["null_join_keys"] == 0
    # M:N fan-out made visible: far more rows than pros.
    assert rows["v_pro_services"]["null_join_keys"] > rows["v_pros"]["n_rows"]


def test_01_liquidity_reconciles(ro):
    rows = run_file(ro, "01_liquidity_geo.sql")
    assert 0 < len(rows) < 500                                  # under the MCP row cap
    total = scalar(ro, f"""SELECT COUNT(*) FROM v_requests
        WHERE created_at_dz >= '{WINDOW[0]}' AND created_at_dz < '{WINDOW[1]}'""")
    assert sum(r["n_requests"] for r in rows) == total           # no fan-out, nothing dropped
    for r in rows:
        assert 0 <= r["fill_rate_wilson_lb"] <= r["fill_rate"] <= 1
        assert r["small_sample"] == (r["n_requests"] < 30)
    # National rate rebuilt from the segments equals a direct single-pass computation.
    direct = scalar(ro, f"""
        SELECT AVG(COALESCE((SELECT MIN(q.created_at_utc) FROM v_quotes AS q
                             WHERE q.request_id = r.request_id)
                            <= r.created_at_utc + INTERVAL '24 hours', FALSE)::int::numeric)
        FROM v_requests AS r
        WHERE r.created_at_dz >= '{WINDOW[0]}' AND r.created_at_dz < '{WINDOW[1]}'""")
    rebuilt = Decimal(sum(r["n_filled"] for r in rows)) / total
    assert abs(rebuilt - direct) < Decimal("1e-9")


def test_03_mix_vs_rate_is_exact_and_finds_simpson(ro):
    rows = run_file(ro, "03_mix_vs_rate.sql")
    total = rows[0]
    assert total["segment"] == "TOTAL"
    parts = total["mix_effect"] + total["rate_effect"] + total["interaction"]
    assert abs(parts - total["total_change"]) < Decimal("1e-5")
    segs = rows[1:]
    assert abs(sum(r["mix_effect"] for r in segs) - total["mix_effect"]) < Decimal("1e-4")
    assert sum(r["n0"] for r in segs) == total["n0"]
    # The planted story: national fill fell, wilayas improved, mix explains the drop.
    assert total["total_change"] < 0
    assert total["rate_effect"] > 0
    assert total["mix_effect"] < total["total_change"]
