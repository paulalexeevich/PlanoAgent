"""
Test: Cross-bay virtual shelf merging with misaligned shelves.

Verifies that _build_virtual_shelves correctly handles bays where shelves
sit at different y-positions (different clearances per bay) and bays with
different shelf counts.
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


def test_misaligned_shelves_same_count():
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
    assert vs[0]["height"] == 10, f"VS[0] height should be min(14,10)=10, got {vs[0]['height']}"
    assert vs[0]["width"] == 96.0
    assert vs[1]["height"] == 12, f"VS[1] height should be min(12,14)=12, got {vs[1]['height']}"
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


def test_different_shelf_counts_with_gap():
    """Bay 2 has fewer shelves → row 4 splits around the gap.

    Scenario: 5 bays glued, Bay 2 has 4 shelves, others have 5.
    Row 4 (5th shelf): Bay 1 standalone + Bays 3-5 merged.
    """
    bay1 = _make_bay(1, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
        _make_shelf(3, 48, 12, 32),
        _make_shelf(4, 48, 12, 45),
        _make_shelf(5, 48, 12, 58),
    ], glued_right=True)
    bay2 = _make_bay(2, [
        _make_shelf(1, 48, 15, 6),
        _make_shelf(2, 48, 15, 22),
        _make_shelf(3, 48, 15, 39),
        _make_shelf(4, 48, 15, 55),
    ], glued_right=True)
    bay3 = _make_bay(3, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
        _make_shelf(3, 48, 12, 32),
        _make_shelf(4, 48, 12, 45),
        _make_shelf(5, 48, 12, 58),
    ], glued_right=True)
    bay4 = _make_bay(4, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
        _make_shelf(3, 48, 12, 32),
        _make_shelf(4, 48, 12, 45),
        _make_shelf(5, 48, 12, 58),
    ], glued_right=True)
    bay5 = _make_bay(5, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
        _make_shelf(3, 48, 12, 32),
        _make_shelf(4, 48, 12, 45),
        _make_shelf(5, 48, 12, 58),
    ])

    groups = _build_bay_groups([bay1, bay2, bay3, bay4, bay5])
    assert len(groups) == 1, "All bays should form one group"

    vs = _build_virtual_shelves(groups)

    # Rows 0-3: all 5 bays → 4 virtual shelves spanning 5 bays
    full_rows = [v for v in vs if len(v["sources"]) == 5]
    assert len(full_rows) == 4, f"Expected 4 full-width rows, got {len(full_rows)}"
    for v in full_rows:
        assert v["width"] == 240.0  # 48 * 5
        assert v["height"] == 12    # min(12, 15) = 12

    # Row 4: Bay1 standalone (48") + Bays 3-5 (144")
    partial_rows = [v for v in vs if len(v["sources"]) < 5]
    assert len(partial_rows) == 2, f"Expected 2 partial rows for row 4, got {len(partial_rows)}"
    widths = sorted([v["width"] for v in partial_rows])
    assert widths == [48.0, 144.0], f"Expected [48, 144], got {widths}"

    print("  PASS: different shelf counts create gap-split virtual shelves")


def test_different_shelf_counts_two_bays():
    """Two glued bays with different shelf counts."""
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

    # Rows 0-1: merged (width 96)
    merged = [v for v in vs if len(v["sources"]) == 2]
    assert len(merged) == 2, f"Expected 2 merged rows, got {len(merged)}"

    # Row 2: Bay 1 standalone (width 48)
    standalone = [v for v in vs if len(v["sources"]) == 1]
    assert len(standalone) == 1, f"Expected 1 standalone, got {len(standalone)}"
    assert standalone[0]["width"] == 48.0

    print("  PASS: different shelf counts (2 bays) handled correctly")


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
    assert len(vs[0]["sources"]) == 2  # bay1.S1 + bay2.S1
    assert len(vs[1]["sources"]) == 2  # bay1.S2 + bay2.S2
    assert len(vs[2]["sources"]) == 1  # bay3.S1
    assert len(vs[3]["sources"]) == 1  # bay3.S2
    print("  PASS: mixed glued + separate bays handled correctly")


def test_real_scenario_5bays_bay2_has_4shelves():
    """Real-world: 5 bays all glued, Bay 2 has 4 shelves with different heights."""
    bay1 = _make_bay(1, [
        _make_shelf(1, 48, 12.2, 6.0),
        _make_shelf(2, 48, 12.2, 19.2),
        _make_shelf(3, 48, 12.2, 32.4),
        _make_shelf(4, 48, 12.2, 45.6),
        _make_shelf(5, 48, 12.2, 58.8),
    ], glued_right=True)
    bay2 = _make_bay(2, [
        _make_shelf(1, 48, 15.5, 6.0),
        _make_shelf(2, 48, 15.5, 22.5),
        _make_shelf(3, 48, 15.5, 39.0),
        _make_shelf(4, 48, 15.5, 55.5),
    ], glued_right=True)
    bay3 = _make_bay(3, [
        _make_shelf(1, 48, 12.2, 6.0),
        _make_shelf(2, 48, 12.2, 19.2),
        _make_shelf(3, 48, 12.2, 32.4),
        _make_shelf(4, 48, 12.2, 45.6),
        _make_shelf(5, 48, 12.2, 58.8),
    ], glued_right=True)
    bay4 = _make_bay(4, [
        _make_shelf(1, 48, 12.2, 6.0),
        _make_shelf(2, 48, 12.2, 19.2),
        _make_shelf(3, 48, 12.2, 32.4),
        _make_shelf(4, 48, 12.2, 45.6),
        _make_shelf(5, 48, 12.2, 58.8),
    ], glued_right=True)
    bay5 = _make_bay(5, [
        _make_shelf(1, 48, 12.2, 6.0),
        _make_shelf(2, 48, 12.2, 19.2),
        _make_shelf(3, 48, 12.2, 32.4),
        _make_shelf(4, 48, 12.2, 45.6),
        _make_shelf(5, 48, 12.2, 58.8),
    ])

    groups = _build_bay_groups([bay1, bay2, bay3, bay4, bay5])
    vs = _build_virtual_shelves(groups)

    # Rows 0-3: all 5 bays contribute
    full = [v for v in vs if len(v["sources"]) == 5]
    assert len(full) == 4, f"Expected 4 full rows, got {len(full)}"
    for v in full:
        assert v["width"] == 240.0
        assert v["height"] == 12.2  # min(12.2, 15.5) = 12.2

    # Row 4: Bay 2 missing → Bay 1 (48) + Bays 3-5 (144)
    partial = [v for v in vs if len(v["sources"]) < 5]
    assert len(partial) == 2, f"Expected 2 partial rows, got {len(partial)}"
    widths = sorted([v["width"] for v in partial])
    assert widths == [48.0, 144.0], f"Expected [48, 144], got {widths}"

    # Source order check for full rows
    for v in full:
        bay_nums = [b.get("bay_number") for b, _ in v["sources"]]
        assert bay_nums == [1, 2, 3, 4, 5], f"Bay order wrong: {bay_nums}"

    print("  PASS: real scenario (5 bays, Bay 2 has 4 shelves)")


if __name__ == "__main__":
    print("Testing virtual shelf merging with misaligned shelves...\n")
    test_aligned_shelves_still_work()
    test_misaligned_shelves_same_count()
    test_misaligned_three_bays()
    test_different_shelf_counts_with_gap()
    test_different_shelf_counts_two_bays()
    test_non_glued_bays_stay_separate()
    test_mixed_glued_and_separate()
    test_real_scenario_5bays_bay2_has_4shelves()
    print("\nAll tests passed!")
