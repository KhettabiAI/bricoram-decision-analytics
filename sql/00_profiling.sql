-- 00 · Profiling: run before any analysis.
-- One row per analytics view: row count, freshness (Algiers time), and the
-- data-quality signals the QA checklist asks for.
-- Grain of the output: view.

SELECT
    'v_requests' AS view_name,
    COUNT(*) AS n_rows,
    MIN(created_at_dz) AS first_at_dz,
    MAX(created_at_dz) AS last_at_dz,
    COUNT(*) FILTER (WHERE status LIKE 'UNMAPPED_%') AS unmapped_codes,
    COUNT(*) FILTER (WHERE commune_id IS NULL) AS null_join_keys
FROM v_requests
UNION ALL
SELECT
    'v_quotes',
    COUNT(*),
    MIN(created_at_dz),
    MAX(created_at_dz),
    COUNT(*) FILTER (WHERE status LIKE 'UNMAPPED_%'),
    COUNT(*) FILTER (WHERE request_id IS NULL OR pro_id IS NULL)
FROM v_quotes
UNION ALL
SELECT
    'v_point_transactions',
    COUNT(*),
    MIN(created_at_dz),
    MAX(created_at_dz),
    0,
    COUNT(*) FILTER (
        WHERE transaction_type = 'lead_unlock' AND (request_id IS NULL OR quote_id IS NULL)
    )
FROM v_point_transactions
UNION ALL
SELECT
    'v_reviews',
    COUNT(*),
    MIN(created_at_dz),
    MAX(created_at_dz),
    0,
    COUNT(*) FILTER (WHERE pro_id IS NULL)
FROM v_reviews
UNION ALL
SELECT
    'v_pros',
    COUNT(*),
    MIN(created_at_dz),
    MAX(created_at_dz),
    0,
    COUNT(*) FILTER (WHERE commune_id IS NULL)
FROM v_pros
UNION ALL
SELECT
    'v_pro_services',
    COUNT(*),
    NULL,
    NULL,
    0,
    COUNT(*) - COUNT(DISTINCT pro_id)        -- rows beyond one per pro = M:N fan-out
FROM v_pro_services
ORDER BY view_name;
