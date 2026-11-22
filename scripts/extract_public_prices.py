"""Extract Bricoram public price-guide tables from saved HTML and flag anomalies.

Usage: python -I scripts/extract_public_prices.py <raw_html_dir> <out_dir>
Writes prices.csv and anomalies.csv to <out_dir>.
"""
import csv
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


class TableParser(HTMLParser):
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


PRICE_RE = re.compile(r"^([\d\s  ]+)\s*DA\s*/\s*(.+)$")


def parse_price(text):
    m = PRICE_RE.match(text)
    if not m:
        return None, None
    return int(re.sub(r"\D", "", m.group(1))), m.group(2).strip()


def main(raw_dir, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    records, anomalies = [], []
    for html in sorted(raw_dir.glob("*.html")):
        p = TableParser()
        p.feed(html.read_text(encoding="utf-8"))
        for row in p.rows:
            if len(row) != 4 or row[1] == "Minimum":
                continue
            (mn, unit), (avg, _), (mx, _) = (parse_price(c) for c in row[1:])
            if None in (mn, avg, mx):
                continue
            rec = {"category": html.stem, "item": row[0], "unit": unit,
                   "min_dzd": mn, "mean_dzd": avg, "max_dzd": mx}
            records.append(rec)
            issues = []
            if avg < mn:
                issues.append(f"mean < min (gap {mn - avg})")
            if avg > mx:
                issues.append(f"mean > max (gap {avg - mx})")
            if mn > mx:
                issues.append("min > max")
            # Mean sits in the bottom/top 10% of a wide range: strong skew worth a look.
            if not issues and mx > mn and mx / mn >= 5:
                pos = (avg - mn) / (mx - mn)
                if pos <= 0.1 or pos >= 0.9:
                    issues.append(f"extreme skew (max/min={mx / mn:.1f}, mean at {pos:.0%} of range)")
            for i in issues:
                anomalies.append({**rec, "issue": i,
                                  "severity": "error" if "skew" not in i else "warning"})
    fields = ["category", "item", "unit", "min_dzd", "mean_dzd", "max_dzd"]
    with open(out_dir / "prices.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(records)
    with open(out_dir / "anomalies.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields + ["severity", "issue"])
        w.writeheader()
        w.writerows(anomalies)
    print(f"{len(records)} rows, {len(anomalies)} anomalies")
    for a in anomalies:
        print(f"[{a['severity']}] {a['category']} | {a['item']} | "
              f"{a['min_dzd']}/{a['mean_dzd']}/{a['max_dzd']} DA/{a['unit']} | {a['issue']}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
