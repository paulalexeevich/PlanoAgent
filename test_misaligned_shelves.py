"""
Test: Cross-bay virtual shelf merging with alignment-aware runs.

Verifies that _build_virtual_shelves only merges shelves across bay
boundaries when they are physically aligned (y_position and height within
tolerance).  Misaligned boundaries break the run — products NEVER span
across a misaligned bay boundary.
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


def test_aligned_shelves_merge():
    """Identical shelf positions → merge into wide virtual shelves."""
    bay1 = _make_bay(1, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
    ], glued_right=True)
    bay2 = _make_bay(2, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
    ])
    groups = _build_bay_groups([bay1, bay2])
    vs = _build_virtual_shelves(groups)

    assert len(vs) == 2, f"Expected 2 virtual shelves, got {len(vs)}"
    for v in vs:
        assert v["width"] == 96.0
        assert len(v["sources"]) == 2
    print("  PASS: aligned shelves merge correctly")


def test_misaligned_shelves_stay_separate():
    """Different y-positions → each bay's shelf is a separate virtual shelf."""
    bay1 = _make_bay(1, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
    ], glued_right=True)
    bay2 = _make_bay(2, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 15, 22),   # y=22 vs y=19, diff=3 > 1.0 tolerance
    ])
    groups = _build_bay_groups([bay1, bay2])
    vs = _build_virtual_shelves(groups)

    # Row 0: aligned → 1 merged virtual shelf
    # Row 1: misaligned → 2 separate virtual shelves
    assert len(vs) == 3, f"Expected 3 virtual shelves, got {len(vs)}"
    merged = [v for v in vs if len(v["sources"]) == 2]
    separate = [v for v in vs if len(v["sources"]) == 1]
    assert len(merged) == 1, f"Expected 1 merged, got {len(merged)}"
    assert len(separate) == 2, f"Expected 2 separate, got {len(separate)}"
    print("  PASS: misaligned shelves stay separate (no product splitting)")


def test_real_scenario_5bays_bay2_misaligned():
    """Real-world: 5 bays glued, Bay 2 has different shelf heights.
    
    Bay 1,3,4,5: 5 shelves at y=6, 19.2, 32.4, 45.6, 58.8 (h=12.2)
    Bay 2:       4 shelves at y=6, 22.5, 39.0, 55.5      (h=15.5)
    
    Expected:
    - Row 0: all 5 bays (y=6 aligned everywhere)
    - Row 1: [Bay1] + [Bay2] + [Bay3,4,5] (misaligned at Bay1→2 and Bay2→3)
    - Row 2: [Bay1] + [Bay2] + [Bay3,4,5]
    - Row 3: [Bay1] + [Bay2] + [Bay3,4,5]
    - Row 4: [Bay1] + [Bay3,4,5] (Bay 2 has no row 4)
    """
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
    assert len(groups) == 1
    vs = _build_virtual_shelves(groups)

    # Row 0: all 5 aligned at y=6 → 1 merged (240")
    row0 = [v for v in vs if v["width"] == 240.0]
    assert len(row0) == 1, f"Expected 1 full-width row, got {len(row0)}"

    # Rows 1-3: [Bay1](48) + [Bay2](48) + [Bay3,4,5](144) = 3 VS per row × 3 rows = 9
    bay1_alone = [v for v in vs if v["width"] == 48.0 and len(v["sources"]) == 1]
    bay345_merged = [v for v in vs if v["width"] == 144.0 and len(v["sources"]) == 3]

    # Bay1 standalone: rows 1,2,3,4 = 4
    # Bay2 standalone: rows 1,2,3 = 3
    # Bay345 merged: rows 1,2,3,4 = 4
    assert len(bay1_alone) + len([v for v in vs if v["width"] == 48.0 and len(v["sources"]) == 1]) >= 4

    # Total virtual shelves: 1 (row0) + 3×3 (rows 1-3) + 2 (row 4) = 12
    assert len(vs) == 12, f"Expected 12 virtual shelves, got {len(vs)}"

    # Verify no phantom splitting: every virtual shelf's sources have same y_pos (within tolerance)
    for v in vs:
        if len(v["sources"]) > 1:
            y_positions = [s.get("y_position", 0) for _, s in v["sources"]]
            for i in range(len(y_positions) - 1):
                assert abs(y_positions[i] - y_positions[i+1]) <= 1.0, \
                    f"Misaligned shelves merged! y={y_positions}"

    print("  PASS: real 5-bay scenario — physically compliant, no splitting")


def test_three_bays_middle_misaligned():
    """Bay 1 and 3 aligned, Bay 2 misaligned → products flow Bay1 only, Bay2 only, Bay3 only."""
    bay1 = _make_bay(1, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
    ], glued_right=True)
    bay2 = _make_bay(2, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 15, 22),  # misaligned
    ], glued_right=True)
    bay3 = _make_bay(3, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
    ])
    groups = _build_bay_groups([bay1, bay2, bay3])
    vs = _build_virtual_shelves(groups)

    # Row 0: all 3 aligned at y=6 → 1 merged (144")
    # Row 1: Bay1(y=19) misaligned with Bay2(y=22) → [Bay1]
    #         Bay2(y=22) misaligned with Bay3(y=19) → [Bay2]
    #         Bay3 standalone → [Bay3]
    assert len(vs) == 4, f"Expected 4, got {len(vs)}"
    full_row = [v for v in vs if v["width"] == 144.0]
    assert len(full_row) == 1
    standalone = [v for v in vs if v["width"] == 48.0]
    assert len(standalone) == 3
    print("  PASS: middle bay misaligned — no cross-bay products through Bay 2")


def test_non_glued_bays():
    """Non-glued bays always stay separate."""
    bay1 = _make_bay(1, [
        _make_shelf(1, 48, 12, 6),
    ], glued_right=False)
    bay2 = _make_bay(2, [
        _make_shelf(1, 48, 12, 6),
    ])
    groups = _build_bay_groups([bay1, bay2])
    vs = _build_virtual_shelves(groups)

    assert len(vs) == 2
    for v in vs:
        assert len(v["sources"]) == 1
    print("  PASS: non-glued bays stay separate")


def test_partial_alignment():
    """Bay 1-2 aligned, Bay 2-3 misaligned → Bay1+2 merge, Bay3 separate."""
    bay1 = _make_bay(1, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
    ], glued_right=True)
    bay2 = _make_bay(2, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 12, 19),
    ], glued_right=True)
    bay3 = _make_bay(3, [
        _make_shelf(1, 48, 12, 6),
        _make_shelf(2, 48, 15, 22),  # misaligned with Bay2
    ])
    groups = _build_bay_groups([bay1, bay2, bay3])
    vs = _build_virtual_shelves(groups)

    # Row 0: all aligned → [Bay1, Bay2, Bay3] = 144"
    # Row 1: Bay1+Bay2 aligned (y=19) → [Bay1, Bay2] = 96"
    #         Bay3 misaligned (y=22) → [Bay3] = 48"
    assert len(vs) == 3, f"Expected 3, got {len(vs)}"
    widths = sorted([v["width"] for v in vs])
    assert widths == [48.0, 96.0, 144.0], f"Expected [48, 96, 144], got {widths}"
    print("  PASS: partial alignment — Bay1+2 merge, Bay3 separate")


if __name__ == "__main__":
    print("Testing alignment-aware virtual shelf merging...\n")
    test_aligned_shelves_merge()
    test_misaligned_shelves_stay_separate()
    test_real_scenario_5bays_bay2_misaligned()
    test_three_bays_middle_misaligned()
    test_non_glued_bays()
    test_partial_alignment()
    print("\nAll tests passed!")
