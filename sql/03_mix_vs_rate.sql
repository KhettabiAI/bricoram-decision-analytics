-- 03 · Why did the national 24 h fill rate change?  Mix vs rate decomposition.
-- Period 0 = 2026-09-01 → 09-30, period 1 = 2026-10-01 → 10-20 (Algiers time).
-- Segment = wilaya. With shares w and rates r per segment:
--   Δ national = Σ (w1−w0)·r0          mix: demand moved between wilayas
--              + Σ w0·(r1−r0)          rate: wilayas got better or worse
--              + Σ (w1−w0)·(r1−r0)     interaction
-- The three effects add up to the total change exactly; tests/test_sql_files.py
-- checks it. A segment absent in a period has share 0, so its missing rate
-- (COALESCE 0) cancels out.
-- Grain of the output: wilaya, plus one 'TOTAL' row.

WITH first_quote AS (                              -- grain: request
    SELECT
        request_id,
        MIN(created_at_utc) AS first_quote_at
    FROM v_quotes
    GROUP BY request_id
),

req AS (                                           -- grain: request
    SELECT
        r.wilaya_code,
        CASE WHEN r.created_at_dz < timestamp '2026-10-01' THEN 0 ELSE 1 END AS period,
        COALESCE(
            fq.first_quote_at <= r.created_at_utc + interval '24 hours', FALSE
        )::int AS filled
    FROM v_requests AS r
    LEFT JOIN first_quote AS fq ON r.request_id = fq.request_id
    WHERE
        r.created_at_dz >= timestamp '2026-09-01'
        AND r.created_at_dz < timestamp '2026-10-21'
),

seg AS (                                           -- grain: wilaya × period
    SELECT
        wilaya_code,
        period,
        COUNT(*) AS n,
        AVG(filled::numeric) AS rate
    FROM req
    GROUP BY wilaya_code, period
),

tot AS (                                           -- grain: period
    SELECT
        period,
        COUNT(*) AS n
    FROM req
    GROUP BY period
),

wide AS (                                          -- grain: wilaya
    SELECT
        w.wilaya_code,
        COALESCE(s0.n, 0) AS n0,
        COALESCE(s1.n, 0) AS n1,
        COALESCE(s0.n, 0)::numeric / (SELECT t.n FROM tot AS t
WHERE t.period = 0) AS w0,
        COALESCE(s1.n, 0)::numeric / (SELECT t.n FROM tot AS t
WHERE t.period = 1) AS w1,
        COALESCE(s0.rate, 0) AS r0,
        COALESCE(s1.rate, 0) AS r1
    FROM v_wilayas AS w
    LEFT JOIN seg AS s0 ON w.wilaya_code = s0.wilaya_code AND s0.period = 0
    LEFT JOIN seg AS s1 ON w.wilaya_code = s1.wilaya_code AND s1.period = 1
    WHERE s0.n IS NOT NULL OR s1.n IS NOT NULL
),

effects AS (                                       -- grain: wilaya
    SELECT
        wilaya_code,
        n0,
        n1,
        w0,
        w1,
        r0,
        r1,
        (w1 - w0) * r0 AS mix_effect,
        w0 * (r1 - r0) AS rate_effect,
        (w1 - w0) * (r1 - r0) AS interaction
    FROM wide
)

SELECT * FROM (
SELECT
    'TOTAL' AS segment,
    SUM(n0) AS n0,
    SUM(n1) AS n1,
    1.0 AS share0,
    1.0 AS share1,
    ROUND(SUM(w0 * r0), 4) AS rate0,
    ROUND(SUM(w1 * r1), 4) AS rate1,
    ROUND(SUM(w1 * r1) - SUM(w0 * r0), 6) AS total_change,
    ROUND(SUM(mix_effect), 6) AS mix_effect,
    ROUND(SUM(rate_effect), 6) AS rate_effect,
    ROUND(SUM(interaction), 6) AS interaction
FROM effects
UNION ALL
SELECT
    wilaya_code::text,
    n0,
    n1,
    ROUND(w0, 4),
    ROUND(w1, 4),
    ROUND(r0, 4),
    ROUND(r1, 4),
    ROUND(w1 * r1 - w0 * r0, 6),
    ROUND(mix_effect, 6),
    ROUND(rate_effect, 6),
    ROUND(interaction, 6)
FROM effects
) AS result
-- TOTAL first, then the wilayas that pulled the national rate down the most.
ORDER BY segment = 'TOTAL' DESC, mix_effect;
