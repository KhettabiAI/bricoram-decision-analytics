-- 01 · Liquidity map: 24 h fill rate by wilaya × service category.
-- Window: 2026-09-01 → 2026-10-20 (Algiers time).
-- Fill = first quote within 24 h. Requests with no quote count as unfilled.
-- Small segments are flagged. Rank by the Wilson lower bound, never by the raw rate.
-- Grain of the output: wilaya × category (≤ 69 × 5 rows).

WITH first_quote AS (                              -- grain: request
    SELECT
        request_id,
        MIN(created_at_utc) AS first_quote_at
    FROM v_quotes
    GROUP BY request_id
),

requests_in_window AS (                            -- grain: request
    SELECT
        r.request_id,
        r.wilaya_code,
        s.category_slug,
        COALESCE(
            fq.first_quote_at <= r.created_at_utc + interval '24 hours', FALSE
        ) AS filled_24h
    FROM v_requests AS r
    INNER JOIN v_services AS s ON r.service_id = s.service_id
    LEFT JOIN first_quote AS fq ON r.request_id = fq.request_id
    WHERE
        r.created_at_dz >= timestamp '2026-09-01'
        AND r.created_at_dz < timestamp '2026-10-21'
),

segment AS (                                       -- grain: wilaya × category
    SELECT
        wilaya_code,
        category_slug,
        COUNT(*) AS n_requests,
        COUNT(*) FILTER (WHERE filled_24h) AS n_filled
    FROM requests_in_window
    GROUP BY wilaya_code, category_slug
),

wilson AS (                                        -- grain: wilaya × category
    SELECT
        wilaya_code,
        category_slug,
        n_requests,
        n_filled,
        n_filled::numeric / n_requests AS p,
        n_requests::numeric AS n,
        1.96::numeric AS z                         -- 95 % confidence
    FROM segment
)

SELECT
    w.wilaya_code,
    w.name_fr AS wilaya,
    ws.category_slug AS category,
    ws.n_requests,
    ws.n_filled,
    ROUND(ws.p, 3) AS fill_rate,
    -- Wilson score lower bound: (p + z²/2n − z·√(p(1−p)/n + z²/4n²)) / (1 + z²/n)
    ROUND(
        (ws.p + ws.z * ws.z / (2 * ws.n)
            - ws.z * SQRT(ws.p * (1 - ws.p) / ws.n + ws.z * ws.z / (4 * ws.n * ws.n)))
        / (1 + ws.z * ws.z / ws.n),
        3
    ) AS fill_rate_wilson_lb,
    ws.n_requests < 30 AS small_sample
FROM wilson AS ws
INNER JOIN v_wilayas AS w ON ws.wilaya_code = w.wilaya_code
ORDER BY ws.n_requests DESC, w.wilaya_code ASC, ws.category_slug ASC;
