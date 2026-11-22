"""Reference geography must match the 2026 territorial law exactly."""


def one(conn, q):
    return conn.execute(q).fetchone()


def test_counts_match_law_26_06(ro):
    assert one(ro, "SELECT COUNT(*) FROM v_wilayas")[0] == 69
    assert one(ro, "SELECT COUNT(*) FROM v_communes")[0] == 1541


def test_every_wilaya_has_communes(ro):
    assert one(ro, """
        SELECT COUNT(*) FROM v_wilayas AS w
        WHERE NOT EXISTS (SELECT 1 FROM v_communes AS c WHERE c.wilaya_code = w.wilaya_code)
    """)[0] == 0


def test_only_new_wilayas_have_a_58_parent(ro):
    rows = ro.execute(
        "SELECT wilaya_code FROM v_wilayas WHERE parent_code_58 IS NOT NULL ORDER BY 1"
    ).fetchall()
    assert [r[0] for r in rows] == list(range(59, 70))


def test_commune_code_prefix_matches_58_map(ro):
    """id / 100 must equal the wilaya on the 58-map: the wilaya itself for 1–58,
    the parent for 59–69. This is what keeps pre-2026 time series comparable."""
    assert one(ro, """
        SELECT COUNT(*) FROM v_communes AS c
        INNER JOIN v_wilayas AS w ON c.wilaya_code = w.wilaya_code
        WHERE c.wilaya_code_58 <> COALESCE(w.parent_code_58, w.wilaya_code)
    """)[0] == 0


def test_58_map_rollup_has_58_wilayas(ro):
    assert one(ro, "SELECT COUNT(DISTINCT wilaya_code_58) FROM v_communes")[0] == 58


def test_known_examples(ro):
    assert one(ro, "SELECT name_fr, parent_code_58 FROM v_wilayas WHERE wilaya_code = 59") \
        == ("Aflou", 3)
    assert one(ro, "SELECT wilaya_code FROM v_communes WHERE commune_id = 1601")[0] == 16
