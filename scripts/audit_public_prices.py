"""Audit Bricoram's public price guide (min / mean / max per service item).

    uv run python scripts/audit_public_prices.py extract <raw_html_dir> <out_dir>
    uv run python scripts/audit_public_prices.py audit <prices.csv> [--fail-on-error]

`extract` parses saved pages into prices.csv; `audit` runs the deterministic
sanity rules and writes anomalies.csv next to it. With --fail-on-error the
audit exits 1 when an ERROR is found, so it can gate a publish step in CI.

Rules (each returns an Issue):
  ERROR    mean < min, mean > max, min > max   — arithmetically impossible
  WARNING  a bound lies more than OUTLIER_RATIO× away from the mean —
           a single extreme quote is likely driving min or max.
"""
import csv
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

OUTLIER_RATIO = 5
FIELDS = ["category", "item", "unit", "min_dzd", "mean_dzd", "max_dzd"]


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" | "warning"
    rule: str
    detail: str


def check_row(mn: int, mean: int, mx: int, ratio: float = OUTLIER_RATIO) -> list[Issue]:
    issues = []
    if mn > mx:
        issues.append(Issue("error", "min_gt_max", f"min exceeds max by {mn - mx}"))
    if mean < mn:
        issues.append(Issue("error", "mean_lt_min", f"mean below min by {mn - mean}"))
    if mean > mx:
        issues.append(Issue("error", "mean_gt_max", f"mean above max by {mean - mx}"))
    if issues:
        return issues
    if mean > 0 and mn > 0 and mean / mn > ratio:
        issues.append(Issue("warning", "min_outlier",
                            f"min is {mean / mn:.1f}x below mean"))
    if mean > 0 and mx / mean > ratio:
        issues.append(Issue("warning", "max_outlier",
                            f"max is {mx / mean:.1f}x above mean"))
    return issues


# ── extraction ─────────────────────────────────────────────────────────────
class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell, self._in_cell = [], None, [], False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._in_cell, self._cell = True, []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._in_cell:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._in_cell = False
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._in_cell:
            self._cell.append(data)


_PRICE_RE = re.compile(r"^([\d\s  ]+)\s*DA\s*/\s*(.+)$")


def parse_price(text: str) -> tuple[int | None, str | None]:
    m = _PRICE_RE.match(text)
    if not m:
        return None, None
    return int(re.sub(r"\D", "", m.group(1))), m.group(2).strip()


def extract_html(html: str, category: str) -> list[dict]:
    p = _TableParser()
    p.feed(html)
    records = []
    for row in p.rows:
        if len(row) != 4 or row[1] == "Minimum":
            continue
        (mn, unit), (mean, _), (mx, _) = (parse_price(c) for c in row[1:])
        if None in (mn, mean, mx):
            continue
        records.append({"category": category, "item": row[0], "unit": unit,
                        "min_dzd": mn, "mean_dzd": mean, "max_dzd": mx})
    return records


# ── audit ──────────────────────────────────────────────────────────────────
def audit(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        for i in check_row(int(r["min_dzd"]), int(r["mean_dzd"]), int(r["max_dzd"])):
            out.append({**r, "severity": i.severity, "rule": i.rule, "detail": i.detail})
    return out


def _write_csv(path: Path, rows: list[dict], fields: list[str]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "extract":
        raw_dir, out_dir = Path(argv[1]), Path(argv[2])
        out_dir.mkdir(parents=True, exist_ok=True)
        records = []
        for html in sorted(raw_dir.glob("*.html")):
            records += extract_html(html.read_text(encoding="utf-8"), html.stem)
        _write_csv(out_dir / "prices.csv", records, FIELDS)
        print(f"{len(records)} rows -> {out_dir / 'prices.csv'}")
        return 0
    if len(argv) >= 2 and argv[0] == "audit":
        prices = Path(argv[1])
        with open(prices, encoding="utf-8") as f:
            records = list(csv.DictReader(f))
        anomalies = audit(records)
        _write_csv(prices.with_name("anomalies.csv"), anomalies,
                   [*FIELDS, "severity", "rule", "detail"])
        for a in anomalies:
            print(f"[{a['severity']}] {a['category']} | {a['item']} | "
                  f"{a['min_dzd']}/{a['mean_dzd']}/{a['max_dzd']} DA/{a['unit']} | {a['detail']}")
        errors = sum(a["severity"] == "error" for a in anomalies)
        print(f"{len(records)} items audited: {errors} errors, {len(anomalies) - errors} warnings")
        return 1 if errors and "--fail-on-error" in argv else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    sys.exit(main(sys.argv[1:]))
