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

## geoalgeria license (MIT part, reproduced as required)

```
MIT License

Copyright (c) 2025-2026 Yasser's studio (https://yasser.studio)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
