"""
Test: Cross-bay virtual shelf merging with misaligned shelves.

Verifies that _build_virtual_shelves correctly handles bays where shelves
sit at different y-positions (different clearances per bay).
"""

from product_logic import _build_bay_groups, _build_virtual_shelves


def _make_shelf(num, width, height, y_pos):
    return {
        "shelf_number": num,
        "width_in": width,
        "height_in": height,
        "y_position": y_pos,
        "positions": [],
    }


def _make_bay(num, shelves, glued_right=False, width=48.0, height=72.0):
    return {
        "bay_number": num,
        "width_in": width,
        "height_in": height,
        "depth_in": 24.0,
        "shelves": shelves,
        "glued_right": glued_right,
    }


def test_aligned_shelves_still_work():
    """Identical shelf positions → merge normally."""
    bay1 = _make_bay(1, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
        _make_shelf(3, 48, 12, 32),
    ], glued_right=True)
    bay2 = _make_bay(2, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
        _make_shelf(3, 48, 12, 32),
    ])
    groups = _build_bay_groups([bay1, bay2])
    vs = _build_virtual_shelves(groups)

    assert len(vs) == 3, f"Expected 3 virtual shelves, got {len(vs)}"
    for v in vs:
        assert v["width"] == 96.0, f"Expected width 96, got {v['width']}"
        assert v["height"] == 12, f"Expected height 12, got {v['height']}"
        assert len(v["sources"]) == 2
    print("  PASS: aligned shelves merge correctly")


def test_misaligned_shelves_index_matching():
    """Shelves at different y-positions but same count → index-based merge."""
    bay1 = _make_bay(1, [
        _make_shelf(1, 48, 14, 6),
        _make_shelf(2, 48, 12, 21),
        _make_shelf(3, 48, 10, 34),
    ], glued_right=True)
    bay2 = _make_bay(2, [
        _make_shelf(1, 48, 10, 6),
        _make_shelf(2, 48, 14, 17),
        _make_shelf(3, 48, 12, 32),
    ])
    groups = _build_bay_groups([bay1, bay2])
    vs = _build_virtual_shelves(groups)

    assert len(vs) == 3, f"Expected 3 virtual shelves, got {len(vs)}"

    # Shelf 1: min(14, 10) = 10
    assert vs[0]["height"] == 10, f"VS[0] height should be min(14,10)=10, got {vs[0]['height']}"
    assert vs[0]["width"] == 96.0

    # Shelf 2: min(12, 14) = 12
    assert vs[1]["height"] == 12, f"VS[1] height should be min(12,14)=12, got {vs[1]['height']}"

    # Shelf 3: min(10, 12) = 10
    assert vs[2]["height"] == 10, f"VS[2] height should be min(10,12)=10, got {vs[2]['height']}"

    for v in vs:
        assert len(v["sources"]) == 2, "Each virtual shelf should span 2 bays"
    print("  PASS: misaligned shelves merge by index with min height")


def test_misaligned_three_bays():
    """Three glued bays with progressively different shelf heights."""
    bay1 = _make_bay(1, [
        _make_shelf(1, 48, 14, 6),
        _make_shelf(2, 48, 12, 21),
    ], glued_right=True)
    bay2 = _make_bay(2, [
        _make_shelf(1, 48, 10, 6),
        _make_shelf(2, 48, 16, 17),
    ], glued_right=True)
    bay3 = _make_bay(3, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 14, 19),
    ])
    groups = _build_bay_groups([bay1, bay2, bay3])
    vs = _build_virtual_shelves(groups)

    assert len(vs) == 2, f"Expected 2 virtual shelves, got {len(vs)}"
    assert vs[0]["width"] == 144.0  # 48 * 3
    assert vs[0]["height"] == 10    # min(14, 10, 12)
    assert vs[1]["height"] == 12    # min(12, 16, 14)
    for v in vs:
        assert len(v["sources"]) == 3
    print("  PASS: three misaligned glued bays merge correctly")


def test_different_shelf_counts_fallback():
    """Bays with different shelf counts → position-based fallback."""
    bay1 = _make_bay(1, [
        _make_shelf(1, 48, 14, 6),
        _make_shelf(2, 48, 12, 21),
        _make_shelf(3, 48, 10, 34),
    ], glued_right=True)
    bay2 = _make_bay(2, [
        _make_shelf(1, 48, 14, 6),
        _make_shelf(2, 48, 12, 21),
    ])
    groups = _build_bay_groups([bay1, bay2])
    vs = _build_virtual_shelves(groups)

    # Shelves 1 and 2 match by y_position; shelf 3 from bay1 is standalone
    merged_count = sum(1 for v in vs if len(v["sources"]) == 2)
    standalone_count = sum(1 for v in vs if len(v["sources"]) == 1)
    assert merged_count == 2, f"Expected 2 merged rows, got {merged_count}"
    assert standalone_count == 1, f"Expected 1 standalone, got {standalone_count}"
    print("  PASS: different shelf counts use position-based fallback")


def test_non_glued_bays_stay_separate():
    """Non-glued bays keep independent shelves."""
    bay1 = _make_bay(1, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
    ], glued_right=False)
    bay2 = _make_bay(2, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
    ])
    groups = _build_bay_groups([bay1, bay2])
    vs = _build_virtual_shelves(groups)

    assert len(vs) == 4, f"Expected 4 separate virtual shelves, got {len(vs)}"
    for v in vs:
        assert len(v["sources"]) == 1
    print("  PASS: non-glued bays stay separate")


def test_mixed_glued_and_separate():
    """Bays 1-2 glued (misaligned), bay 3 separate."""
    bay1 = _make_bay(1, [
        _make_shelf(1, 48, 14, 6),
        _make_shelf(2, 48, 10, 21),
    ], glued_right=True)
    bay2 = _make_bay(2, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 14, 19),
    ], glued_right=False)
    bay3 = _make_bay(3, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
    ])
    groups = _build_bay_groups([bay1, bay2, bay3])
    vs = _build_virtual_shelves(groups)

    assert len(vs) == 4, f"Expected 4 virtual shelves, got {len(vs)}"
    # First two are merged (bays 1-2), next two are separate (bay 3)
    assert len(vs[0]["sources"]) == 2  # bay1.S1 + bay2.S1
    assert len(vs[1]["sources"]) == 2  # bay1.S2 + bay2.S2
    assert len(vs[2]["sources"]) == 1  # bay3.S1
    assert len(vs[3]["sources"]) == 1  # bay3.S2
    print("  PASS: mixed glued + separate bays handled correctly")


if __name__ == "__main__":
    print("Testing virtual shelf merging with misaligned shelves...\n")
    test_aligned_shelves_still_work()
    test_misaligned_shelves_index_matching()
    test_misaligned_three_bays()
    test_different_shelf_counts_fallback()
    test_non_glued_bays_stay_separate()
    test_mixed_glued_and_separate()
    print("\nAll tests passed!")
