# Metric glossary

One definition per metric. If a query disagrees with this file, the query is wrong.

## View grains (analytics_ro)

| View | One row per | Join key(s) | Fan-out risk |
|---|---|---|---|
| `v_wilayas` | wilaya (69) | `wilaya_code` | — |
| `v_communes` | commune (1,541) | `commune_id` | — |
| `v_services` | service item (49) | `service_id` | — |
| `v_users` | account | `user_id` | — |
| `v_pros` | pro profile | `pro_id`, `user_id` | — |
| `v_pro_services` | pro × service | `pro_id`, `service_id` | **M:N: ~18 rows per pro** |
| `v_requests` | published request | `request_id` | hub |
| `v_quotes` | pro response to a request | `quote_id`, `request_id`, `pro_id` | **1:N per request (~2.3)** |
| `v_reviews` | review (≤1 per request) | `request_id`, `pro_id` | 1:N per pro |
| `v_point_transactions` | points movement | `request_id`, `quote_id`, `pro_id` | **1:N per request and pro** |

## Demand side

**Fill rate (24 h)**
- Definition: the share of requests whose first quote arrives within 24 h of publication.
- Denominator: all requests in the window, including those that got no quote.
- SQL: `AVG(COALESCE(first_quote_at <= created_at_utc + INTERVAL '24 hours', FALSE)::int)`.

**Time to first quote (TTFQ)**
- Definition: minutes from publication to the first quote.
- Report p50 and p90, over filled requests only, and always next to the zero-quote rate, which is the share of requests that never got a quote. Without it, the median hides unserved demand.

## Supply side

**Active pros**
- Definition: the number of distinct pros with at least one quote in the window.
- Never count rows in `v_pro_services`.

**Win rate**
- Definition: accepted quotes divided by quotes sent, per pro.

**Pro points ROI**
- Definition: points spent on `lead_unlock` per accepted quote.
- Why it matters: a high value means pros pay without winning, which is the main reason they churn.

## Monetization

**Lead revenue (DZD)**
- SQL: `-SUM(amount_dzd)` over `transaction_type = 'lead_unlock'`.
- Always compute it from `v_point_transactions` alone, or pre-aggregated to `request_id`.

**Top-ups (DZD)**
- SQL: `SUM(amount_dzd)` over `transaction_type = 'topup'`.
- This is cash in, not revenue.

**Points price**
- Definition: `v_requests.points_price`, the price for one response (0–20 points), fixed at publication.

## Quality

**Pro rating (ranking)**
- Never rank by the raw average.
- Shrink each pro's average toward the global mean `m` with `k = 10`: `(sum_ratings + k·m) / (n + k)`.

**Rates by segment**
- For any proportion compared across small segments, use the Wilson lower bound (95 %, z = 1.96).

## Conventions
- **Time:** bucket on `*_dz` (Africa/Algiers, UTC+1, no DST).
- **Geography:**
  - Use `wilaya_code` for the 69-wilaya map.
  - Use `wilaya_code_58` for series that must stay comparable with pre-2026 data.
- **Comparisons:** comparing periods requires a mix vs rate decomposition (`sql/03_mix_vs_rate.sql`).
