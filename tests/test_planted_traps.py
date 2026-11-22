"""Each trap planted by scripts/seed.py must be present — otherwise the analyses
that claim to catch it prove nothing. Queries run as the read-only role, through
the same views an analyst (or Claude Code) would use."""
import hashlib

import seed

CORE = tuple(seed.CORE_WILAYAS)

FILL_BY_SEGMENT = f"""
WITH first_quote AS (                    -- grain: request
    SELECT request_id, MIN(created_at_utc) AS first_at
    FROM v_quotes GROUP BY request_id
)
SELECT
    EXTRACT(MONTH FROM r.created_at_dz)::int AS month,
    CASE WHEN r.wilaya_code IN {CORE} THEN 'core' ELSE 'interior' END AS seg,
    COUNT(*) AS n,
    -- COALESCE is load-bearing: with no quote the comparison is NULL and AVG would
    -- silently drop the request, inflating fill (0.85 instead of 0.71 for Sept).
    AVG(COALESCE(fq.first_at <= r.created_at_utc + INTERVAL '24 hours', FALSE)::int::numeric)
        AS fill
FROM v_requests AS r
LEFT JOIN first_quote AS fq ON r.request_id = fq.request_id
WHERE r.created_at_dz >= '2026-09-01' AND r.created_at_dz < '2026-10-21'
GROUP BY GROUPING SETS ((1, 2), (1))
"""


def test_simpson_fill_rate(ro):
    rows = ro.execute(FILL_BY_SEGMENT).fetchall()
    fill = {(m, s): float(f) for m, s, _, f in rows}
    share_interior = {m: n for m, s, n, _ in rows if s == "interior"}
    total = {m: n for m, s, n, _ in rows if s is None}
    # Both segments improve Sept → Oct …
    assert fill[(10, "core")] > fill[(9, "core")]
    assert fill[(10, "interior")] > fill[(9, "interior")]
    # … the national rate falls …
    assert fill[(10, None)] < fill[(9, None)] - 0.03
    # … because the mix shifted toward the low-liquidity segment.
    assert share_interior[10] / total[10] > 2 * share_interior[9] / total[9]


def test_fan_out_inflates_revenue(ro):
    naive = ro.execute("""
        SELECT -SUM(pt.amount_dzd)
        FROM v_requests AS r
        LEFT JOIN v_quotes AS q ON r.request_id = q.request_id
        LEFT JOIN v_point_transactions AS pt
            ON r.request_id = pt.request_id AND pt.transaction_type = 'lead_unlock'
    """).fetchone()[0]
    truth = ro.execute("""
        SELECT -SUM(amount_dzd) FROM v_point_transactions WHERE transaction_type = 'lead_unlock'
    """).fetchone()[0]
    assert naive > 3 * truth


def test_supply_fan_out_through_pro_services(ro):
    rows, pros = ro.execute(
        "SELECT COUNT(*), COUNT(DISTINCT pro_id) FROM v_pro_services").fetchone()
    assert rows > 10 * pros            # counting rows here overstates supply ~18×


def test_small_sample_pros_win_raw_ranking(ro):
    raw_top = ro.execute("""
        SELECT COUNT(*) AS n FROM v_reviews GROUP BY pro_id
        ORDER BY AVG(rating) DESC, COUNT(*) ASC LIMIT 20""").fetchall()
    assert all(n == 1 for (n,) in raw_top)
    trap = ro.execute("""
        SELECT COUNT(*) FROM (
            SELECT p.pro_id FROM v_pros AS p
            INNER JOIN v_reviews AS rv ON p.pro_id = rv.pro_id
            WHERE p.created_at_dz >= '2026-10-01'
            GROUP BY p.pro_id HAVING COUNT(*) = 1 AND MIN(rv.rating) = 5) AS t
    """).fetchone()[0]
    assert trap >= seed.N_TRAP_PROS


def test_points_price_tracks_competition_not_value(ro):
    core, interior = ro.execute(f"""
        SELECT AVG(points_price) FILTER (WHERE wilaya_code IN {CORE}),
               AVG(points_price) FILTER (WHERE wilaya_code NOT IN {CORE})
        FROM v_requests""").fetchone()
    assert core > 2 * interior


def test_seed_is_deterministic():
    a, b = seed.generate(), seed.generate()
    digest = [hashlib.sha256(repr(g.requests + g.quotes + g.txs).encode()).hexdigest()
              for g in (a, b)]
    assert digest[0] == digest[1]
