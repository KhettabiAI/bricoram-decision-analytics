# Planted traps in the synthetic dataset

`scripts/seed.py` builds ~180k rows (seed `20261122`, May–Oct 2026) and hides
traps that a careless query — human or AI — falls into silently.
`tests/test_planted_traps.py` proves each one is present.

| # | Trap | How it is planted | What the naive answer says | What is true |
|---|---|---|---|---|
| 1 | **Fan-out (revenue)** | Each pro response = one `quote` + one `lead_unlock` | Joining requests → quotes → point_transactions: revenue **×4.8** | Sum the ledger alone, or pre-aggregate each 1:N branch to `request_id` |
| 2 | **Fan-out (supply)** | `pro_services` is M:N; a pro in 2 categories has ~25 rows | Counting rows: supply **×18** | `COUNT(DISTINCT pro_id)` |
| 3 | **Simpson's paradox** | Oct campaign raises interior share of demand 22% → 52% | "Fill rate fell 71% → 65%: the product got worse" | Fill rose in **both** segments (core 80→84%, interior 41→47%); the drop is pure mix |
| 4 | **Small-sample ranking** | 40 pros joined Oct 2026 with exactly one 5★ review; reviews are heavy-tailed (1 → 50 per pro) | Raw average: top 20 are all single-review pros | Bayesian shrinkage / Wilson lower bound |
| 5 | **Time zone** | Evening-heavy activity; ~300 requests straddle midnight | Daily counts on UTC dates shift late-evening activity to the previous day | Bucket on `created_at_dz` (Africa/Algiers, UTC+1, no DST) |
| 6 | **NULL in AVG** | Requests with no quote have no `first_quote_at` | `AVG(first_at <= created + 24h)` skips them: fill **85%** | `COALESCE(…, FALSE)`: fill **71%** |

Trap 6 was not planted on purpose: the test suite's own first query fell into it.

## Grounding of the simulation
- Points: 0–20 per response, set by competition (core wilayas ≈ 12.7 avg, interior ≈ 3.5, often 0); 1 point = 10 DZD; top-ups mostly CCP and BaridiMob (`docs/research/monetization.md`).
- Quote prices: log-normal around the public price guide's mean, clamped near its min/max. Where the guide itself is impossible (mean outside [min, max]), the geometric mean of min and max is used.
- Not modelled yet: off-platform leakage (planned), seasonality, cancellations after hire.
