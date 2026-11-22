"""Credentials and personal material must never be committable, and the guard's
row cap must match DBHub's."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hooks"))
import sql_guard  # noqa: E402  (path set above)


@pytest.mark.parametrize("path", [
    ".env", "dbhub.toml", ".pgdata/x", "evidence/2026-11-22/raw/plomberie.html",
    "private/notes.md",
])
def test_secrets_and_private_files_are_ignored(path):
    res = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
    assert res.returncode == 0, f"{path} is not git-ignored"


def test_no_private_working_notes_in_published_files():
    """Published docs are analysis, not notes about how they will be received."""
    words = ["التقرير", "المقابلة", "التوظيف", "سيُظهر أنك", "إيميل", "interview"]
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                             text=True, encoding="utf-8").stdout.split()
    hits = []
    for rel in tracked:
        path = ROOT / rel
        if path.suffix not in {".md", ".py", ".sql", ".toml", ".json", ".yml"} or \
                path.name == Path(__file__).name or not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        hits += [f"{rel}: {w}" for w in words if w in text]
    assert not hits, hits


def test_guard_cap_matches_dbhub_config():
    cfg = (ROOT / "dbhub.toml.example").read_text(encoding="utf-8")
    assert int(re.search(r"^max_rows\s*=\s*(\d+)", cfg, re.M).group(1)) == sql_guard.MAX_ROWS


def test_dbhub_version_is_pinned():
    import json

    args = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"][
        "bricoram-db"]["args"]
    pkg = next(a for a in args if a.startswith("@bytebase/dbhub"))
    assert re.fullmatch(r"@bytebase/dbhub@\d+\.\d+\.\d+", pkg)
    assert "--readonly" not in args            # removed in DBHub 1.x: the server exits
