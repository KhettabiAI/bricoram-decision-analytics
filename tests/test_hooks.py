"""The hooks are the deterministic layer, so they get adversarial tests. Each case
runs the hook exactly as Claude Code does: JSON on stdin, decision by exit code."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "hooks" / "sql_guard.py"
STOP = ROOT / "hooks" / "verify_on_stop.py"


def run(script, payload):
    res = subprocess.run([sys.executable, str(script)], input=json.dumps(payload),
                         capture_output=True, text=True, cwd=ROOT)
    return res.returncode, res.stderr


def sql_call(sql):
    return {"hook_event_name": "PreToolUse", "tool_name": "mcp__bricoram-db__execute_sql",
            "tool_input": {"sql": sql}}


@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) FROM v_requests",
    "WITH q AS (SELECT request_id, COUNT(*) AS n FROM v_quotes GROUP BY request_id) "
    "SELECT AVG(n) FROM q",
    "SELECT status, COUNT(*) FROM v_requests GROUP BY status",
    "SELECT * FROM v_requests LIMIT 20",
    "SELECT * FROM v_wilayas",                                   # small reference view
    "EXPLAIN (ANALYZE, BUFFERS) SELECT COUNT(*) FROM v_quotes",
    "SELECT 1; SELECT COUNT(*) FROM v_reviews",
    "SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY points_price) FROM v_requests",
])
def test_allows_read_queries(sql):
    code, err = run(GUARD, sql_call(sql))
    assert code == 0, err


@pytest.mark.parametrize(("sql", "why"), [
    ("DELETE FROM v_requests", "DELETE"),
    ("UPDATE pros SET points_balance = 0", "UPDATE"),
    ("SELECT 1; DROP TABLE requests", "DROP"),                   # smuggled 2nd statement
    ("WITH d AS (DELETE FROM quotes RETURNING *) SELECT * FROM d", "DELETE"),
    ("SELECT * INTO tmp FROM v_quotes", "INTO"),
    ("EXPLAIN ANALYZE DELETE FROM quotes", "DELETE"),            # EXPLAIN ANALYZE executes
    ("SET statement_timeout = 0", "SET"),
    ("SELECT set_config('statement_timeout', '0', false)", "set_config"),
    ("ALTER ROLE claude_analytics_ro SET statement_timeout = 0", "read queries"),
    ("SELECT pg_sleep(600)", "pg_sleep"),
    ("SELECT * FROM v_requests FOR UPDATE", "LOCK"),
    ("SELECT phone FROM public.users", "public.users"),
    ("SELECT * FROM v_quotes", "LIMIT"),                         # silent 500-row truncation
    ("SELECT request_id FROM v_requests LIMIT 600", "cap"),      # smoke test: returned 500
    ("COPY (SELECT 1) TO '/tmp/x'", "COPY"),
    ("SELEC broken", "read queries"),                            # fail closed
    ("", "Empty"),
])
def test_blocks_unsafe_sql(sql, why):
    code, err = run(GUARD, sql_call(sql))
    assert code == 2
    assert why.lower() in err.lower()


@pytest.mark.parametrize(("tool", "tool_input", "blocked"), [
    ("Bash", {"command": "cat .env"}, True),
    ("Bash", {"command": "type D:\\Bricoram\\dbhub.toml"}, True),
    ("Read", {"file_path": "D:/Bricoram/.env"}, True),
    ("Grep", {"pattern": "PASSWORD", "path": ".env"}, True),
    ("Read", {"file_path": "D:/Bricoram/.env.example"}, False),
    ("Read", {"file_path": "D:/Bricoram/dbhub.toml.example"}, False),
    ("Bash", {"command": "uv run pytest -q"}, False),
    ("Write", {"file_path": "memos/01.md"}, False),
])
def test_secret_files(tool, tool_input, blocked):
    code, _ = run(GUARD, {"tool_name": tool, "tool_input": tool_input})
    assert (code == 2) is blocked


def test_unreadable_input_fails_closed():
    res = subprocess.run([sys.executable, str(GUARD)], input="not json",
                         capture_output=True, text=True)
    assert res.returncode == 2


def test_stop_hook_never_loops():
    code, _ = run(STOP, {"hook_event_name": "Stop", "stop_hook_active": True})
    assert code == 0
