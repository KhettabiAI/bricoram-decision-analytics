"""The read-only role must be safe even if every other layer (MCP flag, hooks,
CLAUDE.md) fails. Each test is an attack the GRANTs alone must stop."""
import psycopg
import pytest

VIEWS = ["v_wilayas", "v_communes", "v_services", "v_users", "v_pros", "v_pro_services",
         "v_requests", "v_quotes", "v_reviews", "v_point_transactions"]
PII_OR_FREE_TEXT = {"full_name", "phone", "email", "description", "comment"}


def fails(conn, stmt, exc=psycopg.errors.InsufficientPrivilege):
    with pytest.raises(exc):
        conn.execute(stmt)


@pytest.mark.parametrize("view", VIEWS)
def test_can_read_every_analytics_view(ro, view):
    ro.execute(f"SELECT * FROM analytics_ro.{view} LIMIT 1").fetchall()


def test_views_expose_no_pii_or_free_text(ro):
    cols = {r[0] for r in ro.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'analytics_ro'")}
    assert cols and not (cols & PII_OR_FREE_TEXT)


@pytest.mark.parametrize("table", ["users", "requests", "point_transactions"])
def test_cannot_read_raw_tables(ro, table):
    fails(ro, f"SELECT * FROM public.{table} LIMIT 1")


def test_cannot_write_even_after_disabling_read_only_mode(ro):
    ro.execute("SET default_transaction_read_only = off")
    fails(ro, "INSERT INTO public.wilayas VALUES (1, 'x', 'x', NULL)")
    fails(ro, "UPDATE public.pros SET points_balance = 999999")
    fails(ro, "DELETE FROM public.point_transactions")


def test_cannot_write_through_views(ro):
    ro.execute("SET default_transaction_read_only = off")
    fails(ro, "DELETE FROM analytics_ro.v_point_transactions")


@pytest.mark.parametrize("stmt", [
    "CREATE TABLE analytics_ro.x (id int)",
    "CREATE TABLE public.x (id int)",
    "CREATE TEMP TABLE x (id int)",
    "CREATE SCHEMA sneaky",
])
def test_cannot_create_objects(ro, stmt):
    ro.execute("SET default_transaction_read_only = off")
    fails(ro, stmt)


def test_cannot_escalate_privileges(ro):
    ro.execute("SET default_transaction_read_only = off")  # prove the GRANTs alone hold
    fails(ro, "SET ROLE postgres")
    fails(ro, "ALTER ROLE postgres SET statement_timeout = 0")
    fails(ro, "GRANT SELECT ON public.users TO claude_analytics_ro")


def test_known_limitation_role_can_relax_its_own_guardrails(seeded):
    """PostgreSQL lets any role change its OWN session defaults. So the timeout and
    read-only defaults are guardrails, not guarantees: data stays safe (GRANTs),
    but a runaway query is only stopped if SET/ALTER ROLE never reach the DB —
    enforced upstream by the PreToolUse SQL guard hook. Rolled back here."""
    import db

    with (psycopg.connect(db.ro_url(seeded, "test-only-ro-password")) as conn,
          conn.transaction(force_rollback=True)):
        conn.execute("SET LOCAL transaction_read_only = off")
        conn.execute("ALTER ROLE claude_analytics_ro SET statement_timeout = 0")  # succeeds


def test_session_guardrails(ro):
    assert ro.execute("SHOW statement_timeout").fetchone()[0] == "30s"
    assert ro.execute("SHOW default_transaction_read_only").fetchone()[0] == "on"
    assert ro.execute("SHOW search_path").fetchone()[0] == "analytics_ro"


def test_status_codes_are_decoded_not_guessed(ro, seeded):
    assert ro.execute("SELECT status FROM v_requests").fetchone()[0] == "hired"
    # A code with no label cannot even be stored: the FK to the lookup table rejects it.
    with (psycopg.connect(seeded, autocommit=True) as admin,
          pytest.raises(psycopg.errors.ForeignKeyViolation)):
        admin.execute("UPDATE requests SET status_code = 99")


def test_algiers_local_time_crosses_midnight(ro):
    # 23:30 UTC on the 21st is 00:30 on the 22nd in Algiers (UTC+1, no DST).
    utc, dz = ro.execute("SELECT created_at_utc, created_at_dz FROM v_requests").fetchone()
    assert utc.day == 21 and dz.day == 22
