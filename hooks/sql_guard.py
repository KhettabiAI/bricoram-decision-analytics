"""PreToolUse hook — deterministic guard in front of the database and secrets.

Claude Code pipes the tool call as JSON on stdin. Exit 2 blocks the call and
feeds stderr back to the model so it can fix its query; exit 0 allows it.
CLAUDE.md asks; this enforces.

For mcp__bricoram-db__execute_sql (which accepts several `;`-separated statements),
every statement must be a read-only query against analytics_ro:
  * only SELECT / WITH … SELECT / set operations / EXPLAIN of those;
  * no DML or DDL anywhere in the tree (incl. data-modifying CTEs, SELECT INTO);
  * no SET / ALTER ROLE / set_config — PostgreSQL lets a role lift its own
    statement_timeout (tests/test_security.py), so this hook is what stops it;
  * no row locks, no side-effect functions (pg_sleep, dblink, file access…);
  * no raw `public.` tables;
  * no unaggregated, unlimited reads of large views (row cap would truncate silently).
Anything that does not parse is blocked: fail closed.

For Bash / Read / Grep: block access to .env and dbhub.toml (they hold secrets).
"""
import json
import logging
import re
import sys

import sqlglot
from sqlglot import exp

logging.getLogger("sqlglot").setLevel(logging.ERROR)

DB_TOOL = "mcp__bricoram-db__execute_sql"
MAX_ROWS = 500                                     # keep in sync with dbhub.toml.example
LARGE_VIEWS = {"v_requests", "v_quotes", "v_point_transactions", "v_users",
               "v_pro_services", "v_reviews", "v_pros"}
FORBIDDEN_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop,
                   exp.Alter, exp.Command, exp.Set, exp.Into, exp.Lock, exp.Grant,
                   exp.TruncateTable, exp.Copy, exp.Transaction, exp.Commit, exp.Rollback)
FORBIDDEN_FUNCS = re.compile(
    r"^(set_config|pg_sleep.*|pg_terminate_backend|pg_cancel_backend|pg_reload_conf|"
    r"dblink.*|lo_.*|pg_read_.*file|pg_ls_.*|pg_stat_file|pg_advisory.*|"
    r"pg_logical_emit_message|query_to_xml.*|nextval|setval)$", re.I)
SECRET_PATH = re.compile(r"(^|[\\/\s\"'=])(\.env|dbhub\.toml)(\b(?!\.example)|$)")
EXPLAIN = re.compile(r"^\s*EXPLAIN\b(\s*\([^)]*\)|\s+(ANALYZE|VERBOSE|COSTS|BUFFERS)\b)*", re.I)


def check_sql(text: str) -> str | None:
    """Return a reason to block, or None if every statement is allowed."""
    statements = [s for s in _split(text) if s.strip()]
    if not statements:
        return "Empty SQL."
    for stmt in statements:
        if m := EXPLAIN.match(stmt):          # EXPLAIN ANALYZE executes: judge the inner query
            stmt = stmt[m.end():]
        try:
            tree = sqlglot.parse_one(stmt, read="postgres")
        except sqlglot.errors.ParseError as e:
            return f"Could not parse SQL, so it is not allowed (fail closed): {e}".splitlines()[0]
        if reason := _check_tree(tree):
            return reason
    return None


def _split(text: str) -> list[str]:
    try:
        return [t.sql(dialect="postgres") for t in sqlglot.parse(text, read="postgres") if t]
    except sqlglot.errors.ParseError:
        return [text]                        # let parse_one report the error


def _check_tree(tree: exp.Expression) -> str | None:
    if not isinstance(tree, exp.Query):
        return f"Only read queries are allowed, got {type(tree).__name__.upper()}."
    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            return (f"{type(node).__name__.upper()} is not allowed: this connection is "
                    "read-only analytics (SELECT / WITH / EXPLAIN only).")
        if isinstance(node, exp.Func):
            name = node.sql_name() if not isinstance(node, exp.Anonymous) else node.name
            if FORBIDDEN_FUNCS.match(name or ""):
                return f"Function {name}() is not allowed (side effects or session changes)."
        if isinstance(node, exp.Table) and (node.db or "").lower() == "public":
            return (f"Raw table public.{node.name} is off-limits: use the analytics_ro views "
                    "(v_*), which decode status codes and drop PII.")
    return _check_row_cap(tree)


def _check_row_cap(tree: exp.Query) -> str | None:
    limit = tree.args.get("limit")
    if limit is not None:
        # DBHub truncates to MAX_ROWS without any error (smoke-tested: LIMIT 600 → 500 rows).
        value = limit.expression
        if isinstance(value, exp.Literal) and value.is_int and int(value.this) > MAX_ROWS:
            return (f"LIMIT {value.this} exceeds the {MAX_ROWS}-row cap: DBHub would silently "
                    f"return only {MAX_ROWS} rows. Aggregate in SQL instead.")
        return None
    if not isinstance(tree, exp.Select):
        return None
    if tree.args.get("group") or tree.find(exp.AggFunc):
        return None
    big = {t.name.lower() for t in tree.find_all(exp.Table)} & LARGE_VIEWS
    if big:
        return (f"Unaggregated read of {', '.join(sorted(big))} without LIMIT: results are "
                "capped at 500 rows and would be silently truncated. Aggregate in SQL "
                "(GROUP BY) or add an explicit LIMIT for a sample.")
    return None


def check_secrets(tool: str, tool_input: dict) -> str | None:
    fields = [str(tool_input.get(k, "")) for k in ("command", "file_path", "path", "pattern")]
    if any(SECRET_PATH.search(" " + f) for f in fields):
        return f"{tool} on .env / dbhub.toml is blocked: they contain credentials."
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("sql_guard: unreadable hook input, blocking (fail closed).", file=sys.stderr)
        return 2
    tool, tool_input = event.get("tool_name", ""), event.get("tool_input") or {}
    if tool == DB_TOOL:
        reason = check_sql(str(tool_input.get("sql", "")))
    elif tool in ("Bash", "Read", "Grep", "Glob"):
        reason = check_secrets(tool, tool_input)
    else:
        reason = None
    if reason:
        print(f"BLOCKED by hooks/sql_guard.py: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
