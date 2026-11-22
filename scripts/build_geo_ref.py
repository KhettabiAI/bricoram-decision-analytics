"""One-off: build data/ref/ from the geoalgeria npm package (v2.4.0).

    uv run python -I scripts/build_geo_ref.py <path/to/geoalgeria/package/data>

Keeps only the MIT-licensed part (codes and bilingual names). Coordinates are
dropped: part of them is ODbL (OpenStreetMap) and the analyses do not need them.
"""
import csv
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "ref"


def main(src: Path):
    OUT.mkdir(parents=True, exist_ok=True)
    meta = json.loads((src / "wilayas.json").read_text(encoding="utf-8"))
    wilayas = sorted(meta["wilayas"], key=lambda w: w["code"])
    with open(OUT / "wilayas_69.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["code", "name_fr", "name_ar", "parent_code_58", "law"])
        for x in wilayas:
            # Only the 2026 reform (59–69) split territory out of the 58-wilaya map;
            # 49–58 (Law 19-12) already existed in it, so they have no 58-parent.
            parent = x.get("mother_wilaya_code") if x.get("law") == "Law 26-06" else None
            w.writerow([x["code"], x["name_fr"], x["name_ar"], parent or "", x.get("law") or ""])

    with open(src / "csv" / "communes.csv", encoding="utf-8") as f:
        communes = sorted(csv.DictReader(f), key=lambda c: int(c["code_commune"]))
    with open(OUT / "communes_1541.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "wilaya_code", "name_fr", "name_ar", "daira"])
        for c in communes:
            w.writerow([c["code_commune"], c["wilaya_code"], c["name_fr"], c["name_ar"], c["daira"]])
    print(f"{len(wilayas)} wilayas, {len(communes)} communes -> {OUT}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
