"""Stop hook — Claude may not finish while an analysis fails its checks.

Runs only when analysis artefacts changed (sql/, memos/, tests/, scripts/), so
plain conversation stays instant. Exit 2 keeps Claude working and feeds the
failures back; exit 0 lets it stop.

Loop guard: when Claude is already continuing because of this hook,
`stop_hook_active` is true and we let it stop — otherwise a check that Claude
cannot fix would trap the session forever (documented in the hooks reference).
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WATCHED = ["sql", "memos", "tests", "scripts", "db"]
CHECKS = [
    ["uv", "run", "--quiet", "pytest", "-q", "-x", "--no-header",
     "tests/test_sql_files.py", "tests/test_price_audit.py"],
    ["uv", "run", "--quiet", "python", "-m", "sqlfluff", "lint", "sql", "db"],
]


def changed() -> bool:
    out = subprocess.run(["git", "status", "--porcelain", "--", *WATCHED],
                         cwd=ROOT, capture_output=True, text=True)
    return out.returncode != 0 or bool(out.stdout.strip())


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        event = {}
    if event.get("stop_hook_active") or not changed():
        return 0
    for cmd in CHECKS:
        res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        if res.returncode != 0:
            tail = "\n".join((res.stdout + res.stderr).strip().splitlines()[-25:])
            print(f"BLOCKED by hooks/verify_on_stop.py: `{' '.join(cmd[3:])}` failed. "
                  f"Fix the analysis before finishing.\n{tail}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
