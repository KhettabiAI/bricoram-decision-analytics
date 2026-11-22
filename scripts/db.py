"""Build the Bricoram simulation database.

    uv run python scripts/db.py init     # (re)create DB `bricoram`, schema, read-only role
    uv run python scripts/db.py url      # print admin and read-only connection URLs

Admin connection: DATABASE_URL if set (e.g. docker compose), otherwise an embedded
PostgreSQL (pgserver) whose data lives in .pgdata/ — no Docker needed.
"""
import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent
DB_NAME = "bricoram"
RO_ROLE = "claude_analytics_ro"


def load_dotenv():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def admin_url() -> str:
    """Admin URL to the maintenance database (postgres)."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    import pgserver

    _ensure_embedded_tzdata(Path(pgserver.__file__).parent)
    return pgserver.get_server(ROOT / ".pgdata", cleanup_mode=None).get_uri()


def _ensure_embedded_tzdata(pg_pkg: Path):
    """pgserver's Windows build ships without the IANA zone files, so
    'Africa/Algiers' is unknown. Copy them from Python's tzdata package (same
    TZif format). Docker/CI PostgreSQL images already include them."""
    import shutil

    import tzdata

    target = pg_pkg / "pginstall" / "share" / "postgresql" / "timezone"
    if not (target / "Africa" / "Algiers").exists():
        shutil.copytree(Path(tzdata.__file__).parent / "zoneinfo", target, dirs_exist_ok=True)


def with_db(url: str, dbname: str) -> str:
    info = psycopg.conninfo.conninfo_to_dict(url)
    info["dbname"] = dbname
    return psycopg.conninfo.make_conninfo(**info)


def ro_url(url: str, password: str) -> str:
    info = psycopg.conninfo.conninfo_to_dict(with_db(url, DB_NAME))
    info.update(user=RO_ROLE, password=password)
    return psycopg.conninfo.make_conninfo(**info)


def ro_password() -> str:
    pw = os.environ.get("BRICORAM_RO_PASSWORD", "")
    if not pw or pw == "change-me":
        sys.exit("Set BRICORAM_RO_PASSWORD in .env (see .env.example).")
    return pw


def init(password: str) -> str:
    base = admin_url()
    with psycopg.connect(base, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(DB_NAME)))
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))
    with psycopg.connect(with_db(base, DB_NAME), autocommit=True) as conn:
        conn.execute((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        load_geo(conn)
        conn.execute((ROOT / "db" / "ro_security.sql").read_text(encoding="utf-8"))
        conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(
            sql.Identifier(RO_ROLE), sql.Literal(password)))
    return base


def load_geo(conn: psycopg.Connection):
    """Load the 69 wilayas and 1,541 communes from data/ref (see NOTICE.md)."""
    ref = ROOT / "data" / "ref"
    with conn.transaction():
        with conn.cursor().copy(
            "COPY wilayas (code, name_fr, name_ar, parent_code_58) FROM STDIN"
        ) as cp:
            for r in _read_csv(ref / "wilayas_69.csv"):
                cp.write_row((r["code"], r["name_fr"], r["name_ar"], r["parent_code_58"] or None))
        with conn.cursor().copy(
            "COPY communes (id, wilaya_code, name_fr, name_ar, daira) FROM STDIN"
        ) as cp:
            for r in _read_csv(ref / "communes_1541.csv"):
                cp.write_row((r["id"], r["wilaya_code"], r["name_fr"], r["name_ar"], r["daira"]))


def _read_csv(path: Path):
    import csv

    with open(path, encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def main():
    load_dotenv()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "init"
    if cmd == "init":
        base = init(ro_password())
        print(f"Database '{DB_NAME}' ready. Admin: {with_db(base, DB_NAME)}")
    elif cmd == "url":
        base = admin_url()
        print("admin:", with_db(base, DB_NAME))
        print("ro:   ", ro_url(base, "<BRICORAM_RO_PASSWORD>"))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
