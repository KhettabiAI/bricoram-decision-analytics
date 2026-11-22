import sys
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import db
import seed

TEST_RO_PASSWORD = "test-only-ro-password"


@pytest.fixture(scope="session")
def admin_conn_url():
    """Fresh database built from db/*.sql; returns the admin URL to it."""
    db.load_dotenv()
    base = db.init(TEST_RO_PASSWORD)
    return db.with_db(base, db.DB_NAME)


@pytest.fixture(scope="session")
def seeded(admin_conn_url):
    """The full deterministic synthetic dataset, planted traps included."""
    seed.write(admin_conn_url, seed.generate())
    return admin_conn_url


@pytest.fixture
def ro(seeded):
    """Connection as the read-only analytics role."""
    url = db.ro_url(seeded, TEST_RO_PASSWORD)
    with psycopg.connect(url, autocommit=True) as conn:
        yield conn
