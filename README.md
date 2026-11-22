# bricoram-decision-analytics

> **بالعربية:** نموذج عملي لمحلل بيانات يوجّه Claude Code على قاعدة PostgreSQL ويغربل مخرجاته
> بضوابط حتمية (صلاحيات، خطافات، اختبارات مطابقة) قبل أن يصل أي رقم لصاحب القرار.
> يتضمن تدقيقاً حقيقياً لدليل أسعار بريكورام العلني. المذكرات بالعربية في `memos/`.

A working model of the Data Analyst role at Bricoram: **Claude Code writes the SQL,
deterministic checks decide whether a number may reach the founder.**

## What it found

| | Finding | Where |
|---|---|---|
| **Real data** | 2 arithmetically impossible rows in Bricoram's public plumbing price guide (mean outside [min, max]), 2 outlier warnings, 45/49 items clean | [memos/02](memos/02_price_guide_guardrails.md) · [evidence](evidence/2026-11-22/README.md) |
| Synthetic | National fill rate falls 71% → 65% while **every** segment improves: Simpson's paradox, caught by an exact mix-vs-rate decomposition | [sql/03](sql/03_mix_vs_rate.sql) |
| Synthetic | A naive 3-way join inflates lead revenue **×4.8**; counting `pro_services` rows inflates supply **×18** | [docs/planted-traps.md](docs/planted-traps.md) |
| Tooling | DBHub ≥ 1.x silently caps results (LIMIT 600 → 500 rows, no error) and no longer accepts `--readonly`; a PostgreSQL role can lift its own `statement_timeout` | [hooks/sql_guard.py](hooks/sql_guard.py) · [tests](tests/test_security.py) |

## How Claude Code is kept honest

| Layer | Mechanism | Deterministic? |
|---|---|---|
| 1. Database | `claude_analytics_ro`: SELECT on `analytics_ro` views only. No PII, no user free text (prompt-injection vector), status codes decoded | yes, GRANTs |
| 2. MCP | DBHub 1.6.0 pinned, read-only `execute_sql`, 500-row cap | yes |
| 3. PreToolUse hook | sqlglot parses **every** statement; fails closed on DML/DDL, `SET`/`set_config`, side-effect functions, raw tables, silent truncation | yes, exit 2 |
| 4. Stop hook | Claude cannot finish while SQL reconciliation, audit or lint fails (`stop_hook_active` loop guard) | yes, exit 2 |
| 5. CLAUDE.md + `qa-reviewer` | Grain-first SQL, Algiers time, Wilson / shrinkage, mix vs rate, `[query]` / `[assumption]` tags | guidance |

**See it work:** [docs/demo-session.md](docs/demo-session.md) is a real Claude Code
session in which the guard blocks a query that would be silently truncated, and Claude
recovers by exploring the columns and running one correct aggregate.

Every `sql/*.sql` file is tested twice: the guard must allow it, and its totals must
reconcile with an independent single-table query (`tests/test_sql_files.py`).
**100 tests**, run in CI against PostgreSQL 16.

## Run it

Requires [uv](https://docs.astral.sh/uv/), Node ≥ 22 (for DBHub), and PostgreSQL 16+.

```bash
cp .env.example .env        # set BRICORAM_RO_PASSWORD and DATABASE_URL (admin)
docker compose up -d        # or use a local PostgreSQL and point DATABASE_URL at it
uv run python scripts/db.py setup   # schema + 69 wilayas + seeded data + dbhub.toml
uv run pytest -q
claude                      # the project's .mcp.json, hooks and agents load automatically
```

**Windows:**
- Verified with the official PostgreSQL 17 service, Claude Code 2.1.330 and DBHub via plain `npx`; no `cmd /c` wrapper was needed.
- Leaving `DATABASE_URL` empty falls back to an embedded PostgreSQL (`pgserver`). Avoid it for the analysis database:
  - it picks a random port on every start, so `dbhub.toml` goes stale;
  - after a crash it can fail recovery on Windows (it keeps its log file open inside the data directory).

## Map

```
db/          schema (grain per table) · read-only role and views
sql/         analyses: 00 profiling · 01 liquidity map · 03 mix vs rate
hooks/       sql_guard.py (PreToolUse) · verify_on_stop.py (Stop)
scripts/     db.py · seed.py (planted traps) · audit_public_prices.py · build_geo_ref.py
memos/       one-page decision memos for the founder (Arabic)
evidence/    public price-guide capture, 2026-11-22 (CSV + SHA-256; raw pages kept local)
data/ref/    69 wilayas / 1,541 communes, Law 26-06 (MIT part of geoalgeria 2.4.0)
docs/        metric glossary · planted traps · public research on the points model
```

## Honest limits
- Except for `evidence/`, all data is **synthetic**. Its structure follows the founder's
  public description of the points model (2024), which may have changed.
- Status codes and column names are assumptions, documented as such.
- Not yet built: leakage proxy, supply cohorts, points-pricing calibration memo.
