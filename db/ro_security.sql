-- Read-only analytics access for Claude Code (defence in depth, layer 1 of 4).
--
-- The guarantee comes from GRANTs, not from default_transaction_read_only
-- (a session can switch that off) and not from the MCP server's --readonly flag
-- (DBHub < 0.22.6 did not enforce it: CVE-2026-61788).
--
-- The role sees ONLY the analytics_ro schema:
--   * no PII (names, phones, emails are dropped);
--   * no free text written by users (descriptions, review comments) — that text
--     is a prompt-injection vector for an AI agent reading query results;
--   * status codes decoded through lookup tables; unknown codes surface as
--     'UNMAPPED_<code>' instead of being guessed;
--   * timestamps exposed both in UTC and in Africa/Algiers.
-- The password is set by scripts/db.py from BRICORAM_RO_PASSWORD (never stored here).

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'claude_analytics_ro') THEN
        CREATE ROLE claude_analytics_ro LOGIN NOINHERIT;
    END IF;
END $$;

-- Lock down defaults that every role inherits through PUBLIC.
REVOKE ALL ON SCHEMA public FROM PUBLIC; -- noqa: CP02
DO $$
BEGIN
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO claude_analytics_ro', current_database());
END $$;

DROP SCHEMA IF EXISTS analytics_ro CASCADE;
CREATE SCHEMA analytics_ro;

CREATE VIEW analytics_ro.v_wilayas AS
SELECT code AS wilaya_code, name_fr, name_ar, parent_code_58
FROM public.wilayas;

-- wilaya_code_58: the commune's wilaya before the 2026 split, for time series
-- that must stay comparable across the reform.
CREATE VIEW analytics_ro.v_communes AS
SELECT
    id AS commune_id, wilaya_code, id / 100 AS wilaya_code_58,
    name_fr, name_ar, daira
FROM public.communes;

CREATE VIEW analytics_ro.v_services AS
SELECT id AS service_id, slug, category_slug, name_fr, pricing_unit
FROM public.services;

-- PII removed: full_name, phone, email.
CREATE VIEW analytics_ro.v_users AS
SELECT id AS user_id, role, commune_id,
       created_at AS created_at_utc,
       created_at AT TIME ZONE 'Africa/Algiers' AS created_at_dz
FROM public.users;

CREATE VIEW analytics_ro.v_pros AS
SELECT p.id AS pro_id, p.user_id, u.commune_id, p.is_id_verified, p.points_balance,
       p.created_at AS created_at_utc,
       p.created_at AT TIME ZONE 'Africa/Algiers' AS created_at_dz
FROM public.pros AS p
INNER JOIN public.users AS u ON p.user_id = u.id;

CREATE VIEW analytics_ro.v_pro_services AS
SELECT pro_id, service_id, base_price_dzd
FROM public.pro_services;

-- description removed (untrusted free text).
CREATE VIEW analytics_ro.v_requests AS
SELECT r.id AS request_id, r.client_id, r.service_id, r.commune_id,
       c.wilaya_code,
       r.status_code,
       COALESCE(s.label, 'UNMAPPED_' || r.status_code) AS status,
       r.is_urgent, r.points_price, r.budget_dzd,
       r.created_at AS created_at_utc,
       r.created_at AT TIME ZONE 'Africa/Algiers' AS created_at_dz
FROM public.requests AS r
INNER JOIN public.communes AS c ON r.commune_id = c.id
LEFT JOIN public.request_statuses AS s ON r.status_code = s.code;

CREATE VIEW analytics_ro.v_quotes AS
SELECT q.id AS quote_id, q.request_id, q.pro_id,
       q.status_code,
       COALESCE(s.label, 'UNMAPPED_' || q.status_code) AS status,
       q.quoted_price_dzd,
       q.created_at AS created_at_utc,
       q.created_at AT TIME ZONE 'Africa/Algiers' AS created_at_dz
FROM public.quotes AS q
LEFT JOIN public.quote_statuses AS s ON q.status_code = s.code;

-- comment removed (untrusted free text).
CREATE VIEW analytics_ro.v_reviews AS
SELECT id AS review_id, request_id, pro_id, rating, paid_price_dzd,
       created_at AS created_at_utc,
       created_at AT TIME ZONE 'Africa/Algiers' AS created_at_dz
FROM public.reviews;

CREATE VIEW analytics_ro.v_point_transactions AS
SELECT id AS transaction_id, pro_id, transaction_type, payment_method,
       request_id, quote_id, points_delta, amount_dzd,
       created_at AS created_at_utc,
       created_at AT TIME ZONE 'Africa/Algiers' AS created_at_dz
FROM public.point_transactions;

-- Least privilege: USAGE on the analytics schema, SELECT on its views, nothing else.
GRANT USAGE ON SCHEMA analytics_ro TO claude_analytics_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics_ro TO claude_analytics_ro;

-- Session guardrails (layer 2: secondary to the GRANTs above).
-- KNOWN LIMITATION: any role may ALTER ROLE <itself> SET … or SET in-session, so
-- these are defaults, not guarantees (see tests/test_security.py). Data safety
-- rests on the GRANTs; runaway-query protection also needs the PreToolUse SQL
-- guard hook, which rejects SET / ALTER / any non-SELECT before it reaches here.
ALTER ROLE claude_analytics_ro SET default_transaction_read_only = on;
ALTER ROLE claude_analytics_ro SET statement_timeout = '30s';
ALTER ROLE claude_analytics_ro SET idle_in_transaction_session_timeout = '60s';
ALTER ROLE claude_analytics_ro SET search_path = analytics_ro;
ALTER ROLE claude_analytics_ro CONNECTION LIMIT 5;

COMMIT;
