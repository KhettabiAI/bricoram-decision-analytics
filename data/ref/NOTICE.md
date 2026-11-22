# Reference geography — provenance

`wilayas_69.csv` and `communes_1541.csv` are derived from the
[geoalgeria](https://www.npmjs.com/package/geoalgeria) dataset, version 2.4.0
(© 2025-2026 Yasser's studio), MIT-licensed for the compilation of codes and
bilingual names. Only that MIT part is used here; coordinates (partly ODbL,
© OpenStreetMap contributors) were deliberately dropped.

- 69 wilayas per Law 26-06 of 4 April 2026 (JO n° 25, 5 April 2026); wilayas
  59–69 carry `parent_code_58`, the wilaya they were split from.
- 1,541 communes. `id` is the national commune code; its leading digits are
  the wilaya code **before** the 2026 split (e.g. 319 → old wilaya 03), which
  lets historical data be re-mapped without loss.

Rebuild: `uv run python -I scripts/build_geo_ref.py <geoalgeria>/package/data`.
