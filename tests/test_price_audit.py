"""Deterministic sanity rules for the public price guide, plus a regression
check on the 2026-11-22 capture of bricoram.com."""
import csv
from pathlib import Path

import pytest

from audit_public_prices import audit, check_row, extract_html, parse_price

CAPTURE = Path(__file__).resolve().parent.parent / "evidence" / "2026-11-22" / "prices.csv"


def rules(mn, mean, mx):
    return {i.rule for i in check_row(mn, mean, mx)}


@pytest.mark.parametrize(("mn", "mean", "mx", "expected"), [
    (2000, 2500, 3000, set()),                    # healthy
    (3000, 3000, 3000, set()),                    # degenerate but valid
    (10000, 1500, 25000, {"mean_lt_min"}),         # Installation chaudière (live)
    (5000, 10000, 8000, {"mean_gt_max"}),          # Installation radiateur (live)
    (9000, 5000, 4000, {"min_gt_max", "mean_lt_min", "mean_gt_max"}),
    (1200, 5000, 44400, {"max_outlier"}),          # Béton armé et coffrage (live)
    (3000, 40000, 45000, {"min_outlier"}),         # Installation électrique F3 (live)
    (600, 1500, 5000, set()),                      # wide but plausible (peinture déco)
])
def test_check_row(mn, mean, mx, expected):
    assert rules(mn, mean, mx) == expected


def test_errors_suppress_outlier_warnings():
    # An impossible row is an error; ratio warnings on it would be noise.
    assert all(i.severity == "error" for i in check_row(10000, 1500, 25000))


@pytest.mark.parametrize(("text", "expected"), [
    ("3 000 DA /Unité", (3000, "Unité")),
    ("44 400 DA /m³", (44400, "m³")),
    ("300 DA /M", (300, "M")),
    ("Sur devis", (None, None)),
])
def test_parse_price(text, expected):
    assert parse_price(text) == expected


def test_extract_skips_header_and_unparseable_rows():
    html = """<table>
      <tr><th></th><th>Minimum</th><th>Moyenne</th><th>Maximum</th></tr>
      <tr><td>Pose évier</td><td>2 000 DA /Unité</td><td>2 500 DA /Unité</td><td>3 000 DA /Unité</td></tr>
      <tr><td>Sur devis</td><td>-</td><td>-</td><td>-</td></tr>
    </table>"""
    assert extract_html(html, "plomberie") == [{
        "category": "plomberie", "item": "Pose évier", "unit": "Unité",
        "min_dzd": 2000, "mean_dzd": 2500, "max_dzd": 3000}]


def test_capture_regression():
    """The 2026-11-22 capture: 49 items, exactly these findings."""
    with open(CAPTURE, encoding="utf-8") as f:
        records = list(csv.DictReader(f))
    assert len(records) == 49
    found = {(a["item"], a["rule"]) for a in audit(records)}
    assert found == {
        ("Installation chaudière", "mean_lt_min"),
        ("Installation radiateur", "mean_gt_max"),
        ("Béton armé et coffrage", "max_outlier"),
        ("Installation electrique F3 globale", "min_outlier"),
    }
