import os
import sys
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import db
import seed

TEST_DB = "bricoram_test"            # never the analysis database `bricoram`


def ro_password() -> str:
    """The RO role is cluster-wide: reuse the .env password so running the tests
    never breaks Claude Code's live connection to `bricoram`."""
    db.load_dotenv()
    return db.ro_password(required=False) or os.environ.setdefault(
        "BRICORAM_RO_PASSWORD", "test-only-ro-password")


@pytest.fixture(scope="session")
def admin_conn_url():
    """Fresh test database built from db/*.sql; returns the admin URL to it."""
    base = db.init(ro_password(), dbname=TEST_DB)
    return db.with_db(base, TEST_DB)


@pytest.fixture(scope="session")
def seeded(admin_conn_url):
    """The full deterministic synthetic dataset, planted traps included."""
    seed.write(admin_conn_url, seed.generate())
    return admin_conn_url


@pytest.fixture
def ro(seeded):
    """Connection as the read-only analytics role."""
    with psycopg.connect(db.ro_url(seeded, ro_password(), dbname=TEST_DB),
                         autocommit=True) as conn:
        yield conn
