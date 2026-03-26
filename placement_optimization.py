"""Placement Optimization — Proposed Planogram Engine.

This module is intentionally decoupled from realogram-building logic.

Input:  realogram_positions  (list of dicts from `realogram_positions` table)
        product_map_rows     (list of dicts from `test_coffee_product_map`)
        planogram_rows       (list of dicts from `test_coffee_planogram_positions`)
        sales_rows           (list of dicts from `source_data_617533`)
        actions              (list of dicts from `planogram_actions`)

Output: run_optimization()   → ProposedResult dataclass
"""

from __future__ import annotations

import copy
import hashlib
import re as _re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── Types ──────────────────────────────────────────────────────────────────────

ShelfKey = Tuple[int, int]  # (bay_number, shelf_number)
TREE_LEVEL_KEYS = [
    "category_l0",
    "category_l1",
    "category_l2",
    "category_l3",
    "package_type",
    "brand_name",
]
TREE_SCORE_MAX = len(TREE_LEVEL_KEYS)

# Canonical category normalization used for scoring/placement only.
# This protects decision-tree matching from taxonomy label variants.
L0_NORMALIZATION = {
    "Какао, горячий шоколад": "Кофе, какао",
}


def merge_product_map_images(
    product_attrs: Dict[str, dict],
    product_map_rows: list,
) -> None:
    """Fill image_url / image_no_bg_url / recognition_id for every product_code in the map.

    Out-of-shelf actions reference SKUs that may not appear on the realogram yet; those
    codes would otherwise have no image in proposed-planogram visuals.
    """
    for r in product_map_rows:
        code = r.get("product_code")
        if not code:
            continue
        no_bg = (r.get("image_no_bg_url") or "").strip()
        mini = (r.get("miniature_url") or "").strip()
        if not no_bg and not mini:
            continue
        attrs = product_attrs.setdefault(code, {})
        rid = (r.get("recognition_id") or "").strip()
        if rid:
            attrs.setdefault("recognition_id", rid)
        if no_bg:
            attrs["image_no_bg_url"] = no_bg
        # Display URL: prefer transparent no-bg, else miniature (with background)
        attrs["image_url"] = no_bg or attrs.get("image_url") or mini


@dataclass
class ProposedResult:
    """Full output of one optimization run."""
    strategy: str
    combined_score: float
    summary: dict
    actions: List[dict]       # merged list: installed + unplaced, each with tree detail
    bays: List[dict]          # visual bay/shelf/product structure for the frontend
    all_runs: List[dict]      # scores for all 4 strategies (for comparison)


# ── Step 1: Build shelf state from realogram ───────────────────────────────────

def build_shelf_state_from_realogram(
    realogram_positions: list,
    product_map_rows: list,
    planogram_rows: list,
    sales_rows: list,
) -> Tuple[Dict[ShelfKey, dict], dict, dict]:
    """Convert realogram position rows into a shelf_state dict for optimisation.

    Args:
        realogram_positions: rows from `realogram_positions` table.
            Required fields: bay_number, shelf_number, position_index,
            product_id, product_name, brand, category, facings_wide,
            width_in, shelf_width_in.
        product_map_rows: rows from `test_coffee_product_map`.
            Required fields: product_code, recognition_id, tiny_name,
            product_name, width_cm, height_cm, image_no_bg_url, miniature_url.
        planogram_rows: rows from `test_coffee_planogram_positions`.
            Required fields: external_product_id, eq_num_in_scene_group,
            shelf_number, faces_width, store_id.
        sales_rows: rows from `source_data_617533`.
            Required fields: product_code, sale_amount.

    Returns:
        (shelf_state, planogram_target, product_attrs)

        shelf_state:     {(bay, shelf) → shelf dict} — mutable working copy
        planogram_target:{product_code → (bay, shelf)} — where product SHOULD be
        product_attrs:   {product_code → {name, brand, image_url, …}}
    """
    # ── Product map ────────────────────────────────────────────────────────────
    size_map: Dict[str, dict] = {}      # product_code → dims
    recog_to_code: Dict[str, str] = {}  # recognition_id → product_code
    no_bg_by_code: Dict[str, str] = {}  # product_code | recognition_id → image url

    for r in product_map_rows:
        code = r.get("product_code")
        rid = r.get("recognition_id")
        if code:
            size_map[code] = {
                "width_cm": float(r.get("width_cm") or 8.5),
                "height_cm": float(r.get("height_cm") or 20.0),
                "tiny_name": r.get("tiny_name") or "",
                "name": r.get("product_name") or "",
                "category_l0": r.get("category_l0") or "",
                "category_l1": r.get("category_l1") or "",
                "category_l2": r.get("category_l2") or "",
                "category_l3": r.get("category_l3") or "",
                "package_type": r.get("package_type") or "",
                "brand": r.get("brand") or "",
            }
            img = (r.get("image_no_bg_url") or r.get("miniature_url") or "").strip()
            if img:
                no_bg_by_code[code] = img
                if rid:
                    no_bg_by_code[rid] = img
        if rid and code:
            recog_to_code[rid] = code

    # ── Sales aggregation (avg sale per tiny_name) ─────────────────────────────
    sales_agg: Dict[str, list] = defaultdict(list)
    for r in sales_rows:
        code = r.get("product_code", "")
        tiny = size_map.get(code, {}).get("tiny_name", "")
        if tiny and r.get("sale_amount") is not None:
            sales_agg[tiny].append(float(r["sale_amount"]))
    sales_map: Dict[str, float] = {
        tiny: round(sum(vals) / len(vals), 2)
        for tiny, vals in sales_agg.items() if vals
    }

    # ── Planogram target (where each product SHOULD go) ────────────────────────
    # Two granularities:
    #   planogram_facings_by_shelf — (code, bay, shelf) → facings  (precise)
    #   planogram_facings_global   — code → total facings across all shelves
    #
    # Excess detection uses per-shelf first (e.g. product IS on same shelf in
    # planogram).  When a product is on a DIFFERENT shelf in the planogram we
    # fall back to the global total so we still catch genuine over-facing cases
    # (e.g. Jardin on realogram S6 with 6 facings vs planogram S2 with 3 → 3 excess).
    planogram_target: Dict[str, ShelfKey] = {}
    planogram_facings_by_shelf: Dict[Tuple[str, int, int], int] = {}
    planogram_facings_global:   Dict[str, int] = {}
    for row in planogram_rows:
        eid = row["external_product_id"]
        bay = int(row["eq_num_in_scene_group"])
        sh  = int(row["shelf_number"])
        key: ShelfKey = (bay, sh)
        if eid not in planogram_target:
            planogram_target[eid] = key
        triple = (eid, bay, sh)
        f = max(1, int(row.get("faces_width") or 1))
        planogram_facings_by_shelf[triple] = planogram_facings_by_shelf.get(triple, 0) + f
        planogram_facings_global[eid]      = planogram_facings_global.get(eid, 0) + f

    # Build category scope from planogram assortment.
    # Realogram products outside this scope are treated as out-of-category noise
    # and excluded before optimization so their shelf space becomes available.
    allowed_l0: set = set()
    allowed_l1: set = set()
    for eid in planogram_target.keys():
        sz = size_map.get(eid, {})
        l0 = (sz.get("category_l0") or "").strip()
        if l0 in L0_NORMALIZATION:
            l0 = L0_NORMALIZATION[l0]
        l1 = (sz.get("category_l1") or "").strip()
        if l0:
            allowed_l0.add(l0)
        if l1:
            allowed_l1.add(l1)

    # Also index by recognition_id so products map cleanly
    for rid, code in recog_to_code.items():
        if rid not in planogram_target and code in planogram_target:
            planogram_target[rid] = planogram_target[code]

    # ── Pre-aggregate photo facings per (product_code, bay, shelf) ────────────
    # A product can appear in several realogram rows on the same shelf (separate
    # detection groups).  We must sum them before comparing to the planogram.
    PhotoKey = Tuple[str, int, int]  # (product_code, bay, shelf)
    photo_facings_agg: Dict[PhotoKey, int] = defaultdict(int)
    photo_width_agg:   Dict[PhotoKey, float] = {}   # first observed width
    photo_pid_agg:     Dict[PhotoKey, str] = {}     # first pid for attrs
    photo_row_agg:     Dict[PhotoKey, dict] = {}    # first row for attrs
    shelf_width_map:   Dict[ShelfKey, float] = {}   # (bay, shelf) → cm

    for row in realogram_positions:
        bay_num  = int(row["bay_number"])
        shelf_num = int(row["shelf_number"])
        pid = row["product_id"]
        product_code = recog_to_code.get(pid, pid)
        sz = size_map.get(product_code, {})
        # Pre-filter: keep only products within planogram category scope.
        # This removes unrelated categories (e.g. cosmetics/alcohol) from the
        # proposed-planogram baseline and frees space for real installations.
        row_l0 = (sz.get("category_l0") or "").strip()
        if row_l0 in L0_NORMALIZATION:
            row_l0 = L0_NORMALIZATION[row_l0]
        row_l1 = (sz.get("category_l1") or row.get("category", "") or "").strip()
        if allowed_l0 and row_l0 and row_l0 not in allowed_l0:
            continue
        if allowed_l1 and row_l1 and row_l1 not in allowed_l1:
            continue
        width_cm = round(row.get("width_in", 0) * 2.54, 2) or max(1.0, float(sz.get("width_cm") or 8.5))
        pk: PhotoKey = (product_code, bay_num, shelf_num)
        photo_facings_agg[pk] += max(1, int(row.get("facings_wide", 1)))
        if pk not in photo_width_agg:
            photo_width_agg[pk] = width_cm
            photo_pid_agg[pk]   = pid
            photo_row_agg[pk]   = row
        sk: ShelfKey = (bay_num, shelf_num)
        if sk not in shelf_width_map:
            shelf_width_map[sk] = round(row.get("shelf_width_in", 48.0) * 2.54, 1)

    # ── Build shelf_state from aggregated photo data ───────────────────────────
    shelves: Dict[ShelfKey, dict] = {}
    product_attrs: Dict[str, dict] = {}

    for (product_code, bay_num, shelf_num), photo_facings in photo_facings_agg.items():
        key: ShelfKey = (bay_num, shelf_num)
        pid     = photo_pid_agg[(product_code, bay_num, shelf_num)]
        row     = photo_row_agg[(product_code, bay_num, shelf_num)]
        width_cm = photo_width_agg[(product_code, bay_num, shelf_num)]
        sz = size_map.get(product_code, {})
        tiny_name = sz.get("tiny_name") or row.get("product_name", "") or pid
        avg_sale  = float(sales_map.get(tiny_name, 0))

        # Per-shelf planogram facings first; fall back to global total when the
        # product sits on a different shelf in the planogram (e.g. realogram S6
        # but planogram S2).  This catches genuine over-facing cases regardless
        # of shelf mismatch.
        planogram_f = planogram_facings_by_shelf.get(
            (product_code, bay_num, shelf_num),
            planogram_facings_by_shelf.get((pid, bay_num, shelf_num), 0),
        )
        if planogram_f == 0:
            planogram_f = planogram_facings_global.get(
                product_code, planogram_facings_global.get(pid, 0)
            )

        if key not in shelves:
            shelves[key] = {
                "eq_num": bay_num,
                "shelf_number": shelf_num,
                "total_width_cm": shelf_width_map.get(key, 121.9),
                "used_cm": 0.0,
                "free_cm": 0.0,
                "total_freeable_cm": 0.0,
                "products": [],
                "reduction_candidates": [],
                "tree_groups": [],
            }

        shelves[key]["used_cm"] += width_cm * photo_facings
        shelves[key]["products"].append({
            "product_code": product_code,
            "tiny_name": tiny_name,
            "planogram_facings": planogram_f if planogram_f > 0 else photo_facings,
            "photo_facings": photo_facings,
            "width_cm": width_cm,
            "avg_sale_amount": avg_sale,
        })

        excess = photo_facings - planogram_f if planogram_f > 0 else 0
        if excess > 0:
            shelves[key]["reduction_candidates"].append({
                "product_code": product_code,
                "tiny_name": tiny_name,
                "photo_facings": photo_facings,
                "planogram_facings": planogram_f,
                "excess_facings": excess,
                "width_cm": width_cm,
                "freeable_cm": round(excess * width_cm, 1),
                "avg_sale_amount": avg_sale,
            })

        if product_code not in product_attrs:
            image_url = no_bg_by_code.get(product_code) or no_bg_by_code.get(pid) or ""
            category_l0 = sz.get("category_l0") or ""
            category_l1 = sz.get("category_l1") or row.get("category", "")
            category_l2 = sz.get("category_l2") or category_l1
            category_l3 = sz.get("category_l3") or ""
            package_type = sz.get("package_type") or ""
            brand_name = sz.get("brand") or row.get("brand", "")
            product_attrs[product_code] = {
                "category_l0": category_l0,
                "category_l1": category_l1,
                "category_l2": category_l2,
                "category_l3": category_l3,
                "category_name": category_l2,
                "package_type": package_type,
                "brand_name": brand_name,
                "brand_owner_name": brand_name,
                "image_url": image_url,
                "product_name": sz.get("name") or row.get("product_name", "") or tiny_name,
                "recognition_id": pid,
            }
            _normalize_attrs_inplace(product_attrs[product_code])

    # ── Finalise shelf metrics ─────────────────────────────────────────────────
    for key, shelf in shelves.items():
        shelf["used_cm"] = round(shelf["used_cm"], 1)
        shelf["free_cm"] = max(0.0, round(shelf["total_width_cm"] - shelf["used_cm"], 1))
        shelf["pre_overflow_cm"] = max(0.0, round(shelf["used_cm"] - shelf["total_width_cm"], 1))
        shelf["reduction_candidates"].sort(key=lambda x: x["avg_sale_amount"])
        reducible = round(sum(c["freeable_cm"] for c in shelf["reduction_candidates"]), 1)
        shelf["total_freeable_cm"] = round(shelf["free_cm"] + reducible, 1)
        shelf["net_available_cm"] = round(
            shelf["total_width_cm"] - shelf["used_cm"] + reducible, 1
        )
        # Populate tree_groups from existing realogram products so the placement
        # algorithm knows what categories are already on each shelf.
        for prod in shelf["products"]:
            attrs = product_attrs.get(prod["product_code"], {})
            grp = _group_for_attrs(attrs)
            if any(g for g in grp) and grp not in shelf["tree_groups"]:
                shelf["tree_groups"].append(grp)

    return shelves, planogram_target, product_attrs


# ── Step 2: Tree scoring ────────────────────────────────────────────────────────

def _score_tree_insertion(prod_groups: tuple, shelf_tree_groups: list) -> int:
    """Score how well a product fits a shelf from a decision tree perspective.

    Returns:
        0..N where N=len(TREE_LEVEL_KEYS), using progressive level fallback.
        Match tries from L0 first; if it conflicts, retries from L1, then L2, etc.
        Deeper matched chain wins.
    """
    if not shelf_tree_groups:
        return 1  # empty shelf is category-compatible baseline
    return max(_fallback_level_depth(prod_groups, grp) for grp in shelf_tree_groups)


def _group_for_attrs(attrs: dict) -> tuple:
    """Build a fixed-depth decision-tree tuple from product attrs."""
    _normalize_attrs_inplace(attrs)
    return (
        attrs.get("category_l0", ""),
        attrs.get("category_l1", ""),
        attrs.get("category_l2", "") or attrs.get("category_name", ""),
        attrs.get("category_l3", ""),
        attrs.get("package_type", ""),
        attrs.get("brand_name", ""),
    )


def _normalize_attrs_inplace(attrs: dict) -> None:
    """Normalize taxonomy aliases in-place for consistent tree scoring."""
    l0 = (attrs.get("category_l0") or "").strip()
    l1 = (attrs.get("category_l1") or "").strip()
    l2 = (attrs.get("category_l2") or "").strip()
    if l0 in L0_NORMALIZATION:
        attrs["category_l0"] = L0_NORMALIZATION[l0]
    # If L0 missing/variant but L1/L2 clearly belongs to cocoa/hot chocolate,
    # map to the canonical mixed root used by shelf products.
    if not attrs.get("category_l0") and (
        l1 == "Какао, горячий шоколад" or l2 == "Какао, горячий шоколад"
    ):
        attrs["category_l0"] = "Кофе, какао"


def _fallback_level_depth(a: tuple, b: tuple) -> int:
    """Compute best hierarchical match depth with explicit level fallback.

    For each start level i (L0..LN), try matching from i downward:
      - both present + equal => count
      - both present + different => stop this chain (keep depth so far)
      - missing on either side => skip (unknown)
    Returns the maximum matched depth across all starts.
    """
    n = min(len(a), len(b))
    best = 0
    for start in range(n):
        depth = 0
        compared = 0
        for idx in range(start, n):
            av = a[idx]
            bv = b[idx]
            if av and bv:
                compared += 1
                if av != bv:
                    break
                depth += 1
        if compared > 0 and depth > best:
            best = depth
    return best


# ── Step 3: Fit computation (non-mutating) ─────────────────────────────────────

def _compute_fit(shelf: dict, needed_cm: float) -> Optional[dict]:
    """Evaluate whether a product fits on a shelf WITHOUT mutating shelf state.

    Returns a fit dict or None if no space is available even after reductions.
    """
    if shelf["free_cm"] >= needed_cm:
        return {"space_source": "free_space", "reductions": [], "time_min": 1}

    if shelf["net_available_cm"] < needed_cm:
        return None

    reductions = []
    time_min = 1
    still_needed = round(needed_cm - shelf["free_cm"], 2)
    simulated: Dict[str, int] = {}

    for cand in shelf["reduction_candidates"]:
        if still_needed <= 0:
            break
        already = simulated.get(cand["product_code"], 0)
        available = cand["excess_facings"] - already
        if available <= 0:
            continue
        take = min(available, max(1, -(-int(still_needed / cand["width_cm"]))))
        freed = round(take * cand["width_cm"], 1)
        reductions.append({
            "product_code": cand["product_code"],
            "tiny_name": cand["tiny_name"],
            "reduce_from": cand["photo_facings"] - already,
            "reduce_to": cand["photo_facings"] - already - take,
            "freed_cm": freed,
            "time_min": take * 1,
        })
        time_min += take * 1
        simulated[cand["product_code"]] = already + take
        still_needed = round(still_needed - freed, 2)

    return {"space_source": "excess_facings", "reductions": reductions, "time_min": time_min}


def _apply_fit(shelf: dict, fit: dict, needed_cm: float) -> None:
    """Apply a computed fit to the real shelf state (mutates in place)."""
    if fit["space_source"] == "free_space":
        shelf["free_cm"] = round(shelf["free_cm"] - needed_cm, 2)
        shelf["used_cm"] = round(shelf["used_cm"] + needed_cm, 2)
        shelf["total_freeable_cm"] = round(shelf["total_freeable_cm"] - needed_cm, 2)
        shelf["net_available_cm"] = round(shelf["net_available_cm"] - needed_cm, 2)
    else:
        still_needed = round(needed_cm - shelf["free_cm"], 2)
        shelf["used_cm"] = round(shelf["used_cm"] + shelf["free_cm"], 2)
        shelf["free_cm"] = 0.0
        for red in fit["reductions"]:
            take = red["reduce_from"] - red["reduce_to"]
            for cand in shelf["reduction_candidates"]:
                if cand["product_code"] == red["product_code"]:
                    cand["photo_facings"] -= take
                    cand["excess_facings"] -= take
                    cand["freeable_cm"] = round(cand["freeable_cm"] - red["freed_cm"], 1)
                    break
        total_freed = sum(r["freed_cm"] for r in fit["reductions"])
        shelf["free_cm"] = max(0.0, round(total_freed - still_needed, 2))
        shelf["used_cm"] = round(shelf["used_cm"] + needed_cm, 2)
        remaining = round(sum(c["freeable_cm"] for c in shelf["reduction_candidates"]), 1)
        shelf["total_freeable_cm"] = round(shelf["free_cm"] + remaining, 1)
        shelf["net_available_cm"] = round(
            shelf["total_width_cm"] - shelf["used_cm"] + remaining, 1
        )
        shelf["pre_overflow_cm"] = max(0.0, round(shelf["used_cm"] - shelf["total_width_cm"], 1))


def _try_relocation_fit(
    shelves: Dict[ShelfKey, dict],
    source_key: ShelfKey,
    needed_cm: float,
    product_attrs: Dict[str, dict],
) -> Optional[dict]:
    """Try to free space by moving one facing to another bay on same shelf number.

    Returns a fit dict compatible with placement options when relocation succeeds.
    """
    source = shelves.get(source_key)
    if not source:
        return None

    if source.get("free_cm", 0) >= needed_cm:
        return {"space_source": "free_space", "reductions": [], "time_min": 1, "relocations": []}

    # Prefer moving lowest-sales products first.
    movable = sorted(
        [p for p in source.get("products", []) if p.get("photo_facings", 0) > 0],
        key=lambda p: float(p.get("avg_sale_amount") or 0),
    )
    if not movable:
        return None

    relocations = []
    same_shelf_dest = sorted(
        [k for k in shelves.keys() if k[1] == source_key[1] and k[0] != source_key[0]],
        key=lambda k: abs(k[0] - source_key[0]),
    )

    for prod in movable:
        width_cm = float(prod.get("width_cm") or 0)
        if width_cm <= 0:
            continue

        # Find destination bay on same shelf with enough free space.
        dest_key = next(
            (k for k in same_shelf_dest if shelves[k].get("free_cm", 0) >= width_cm),
            None,
        )
        if not dest_key:
            continue

        dest = shelves[dest_key]
        code = prod.get("product_code")
        if not code:
            continue

        # Move exactly one facing.
        prod["photo_facings"] -= 1
        source["used_cm"] = round(source.get("used_cm", 0) - width_cm, 2)
        source["free_cm"] = round(source.get("free_cm", 0) + width_cm, 2)

        existing = next((p for p in dest.get("products", []) if p.get("product_code") == code), None)
        if existing:
            existing["photo_facings"] = int(existing.get("photo_facings", 0)) + 1
        else:
            moved = copy.deepcopy(prod)
            moved["photo_facings"] = 1
            dest.setdefault("products", []).append(moved)
            attrs = product_attrs.get(code, {})
            grp = _group_for_attrs(attrs)
            if any(g for g in grp) and grp not in dest.get("tree_groups", []):
                dest.setdefault("tree_groups", []).append(grp)

        dest["used_cm"] = round(dest.get("used_cm", 0) + width_cm, 2)
        dest["free_cm"] = round(dest.get("free_cm", 0) - width_cm, 2)

        relocations.append({
            "product_code": code,
            "from_shelf": f"Bay {source_key[0]}, Shelf {source_key[1]}",
            "to_shelf": f"Bay {dest_key[0]}, Shelf {dest_key[1]}",
            "moved_facings": 1,
        })

        if source.get("free_cm", 0) >= needed_cm:
            return {
                "space_source": "relocation",
                "reductions": [],
                "time_min": 2 + len(relocations),  # move + install overhead
                "relocations": relocations,
            }

    return None


# ── Step 4: Single strategy run ────────────────────────────────────────────────

def _run_strategy(
    actions: list,
    shelf_state: Dict[ShelfKey, dict],
    planogram_target: Dict[str, ShelfKey],
    product_attrs: Dict[str, dict],
    strategy: str,
) -> dict:
    """Run one placement strategy and return placed/unplaced lists + summary.

    Strategies
    ----------
    sales_first_strict   — highest sales first, best realogram tree shelf
    sales_first_flexible — highest sales first, best realogram tree shelf
    tree_first           — group by category/brand for tree compliance, then sales
    min_time             — prefer free-space slots (no reductions needed) first
    """
    shelves = copy.deepcopy(shelf_state)

    if strategy in ("sales_first_strict", "sales_first_flexible"):
        sorted_actions = sorted(actions, key=lambda x: float(x.get("avg_sale_amount") or 0), reverse=True)
    elif strategy == "tree_first":
        sorted_actions = sorted(
            actions,
            key=lambda x: (
                product_attrs.get(x.get("product_code", ""), {}).get("category_l0", "zzz"),
                product_attrs.get(x.get("product_code", ""), {}).get("category_l1", "zzz"),
                product_attrs.get(x.get("product_code", ""), {}).get("category_l2", "zzz"),
                product_attrs.get(x.get("product_code", ""), {}).get("category_l3", "zzz"),
                product_attrs.get(x.get("product_code", ""), {}).get("package_type", "zzz"),
                product_attrs.get(x.get("product_code", ""), {}).get("brand_name", "zzz"),
                -float(x.get("avg_sale_amount") or 0),
            ),
        )
    elif strategy == "min_time":
        def _min_time_key(a):
            code = a.get("product_code", "")
            needed = max(1.0, float(a.get("width_cm") or 8.5)) * max(
                1, int(a.get("planogram_facings") or 1)
            )
            prod_groups = _group_for_attrs(product_attrs.get(code, {}))
            scored = [
                (k, _score_tree_insertion(prod_groups, shelf["tree_groups"]))
                for k, shelf in shelves.items()
            ]
            best_depth = max((d for _, d in scored), default=0)
            if best_depth > 0:
                candidate_keys = [k for k, d in scored if d == best_depth]
            else:
                candidate_keys = list(shelves.keys())
            if any(shelves[k].get("free_cm", 0) >= needed for k in candidate_keys):
                return (0, -float(a.get("avg_sale_amount") or 0))
            return (1, -float(a.get("avg_sale_amount") or 0))
        sorted_actions = sorted(actions, key=_min_time_key)
    else:
        sorted_actions = list(actions)

    placed: list = []
    unplaced: list = []
    deferred_for_opportunistic: list = []

    for action in sorted_actions:
        product_code = action.get("product_code", "")
        tiny_name = action.get("tiny_name", "")
        unit_width_cm = max(1.0, float(action.get("width_cm") or 8.5))
        install_facings = max(1, int(action.get("planogram_facings") or 1))
        needed_cm = round(unit_width_cm * install_facings, 1)
        avg_sale = float(action.get("avg_sale_amount") or 0)

        target_key = planogram_target.get(product_code)
        eq_num, shelf_num = target_key if target_key else (None, None)

        attrs = product_attrs.get(product_code, {})
        prod_groups = _group_for_attrs(attrs)

        # Candidate shelves are selected from REALOGRAM only:
        # choose shelves with the deepest decision-tree match. If no match exists,
        # allow all shelves as a fallback.
        scored_all = sorted(
            ((k, _score_tree_insertion(prod_groups, s["tree_groups"])) for k, s in shelves.items()),
            key=lambda x: (x[1], -x[0][0], -x[0][1]),
            reverse=True,
        )
        best_depth = max((d for _, d in scored_all), default=0)
        if best_depth > 0:
            candidate_keys = [k for k, d in scored_all if d == best_depth]
        else:
            candidate_keys = [k for k, _ in scored_all]

        options = []
        for shelf_key in candidate_keys:
            shelf = shelves[shelf_key]
            fit = None
            # For low-priority / zero-sales installs, prefer relocation first:
            # it preserves on-shelf category blocks better than aggressive reductions.
            if avg_sale <= 0:
                fit = _try_relocation_fit(shelves, shelf_key, needed_cm, product_attrs)
            if fit is None:
                fit = _compute_fit(shelf, needed_cm)
            if fit is None:
                fit = _try_relocation_fit(shelves, shelf_key, needed_cm, product_attrs)
            if fit is None:
                continue
            tree_score = _score_tree_insertion(prod_groups, shelf["tree_groups"])
            shelf_delta = abs(shelf_key[1] - shelf_num) if shelf_num is not None else 0
            options.append({"shelf_key": shelf_key, "shelf_delta": shelf_delta,
                            "tree_score": tree_score, **fit})

        if not options:
            row = {"product_code": product_code, "tiny_name": tiny_name,
                   "avg_sale_amount": avg_sale,
                   "reason": "Insufficient space after all excess facing reductions exhausted"}
            unplaced.append(row)
            deferred_for_opportunistic.append(action)
            continue

        best = max(options, key=lambda o: (o["tree_score"], -o["time_min"]))
        shelf_key = best["shelf_key"]
        shelf = shelves[shelf_key]
        shelf_groups_before = list(shelf["tree_groups"])

        # Recalculate time: 1 min per facing installed + reduction removal time
        reduction_time = sum(r.get("time_min", 1) for r in best.get("reductions", []))
        best["time_min"] = reduction_time + 1 * install_facings

        _apply_fit(shelf, best, needed_cm)

        if prod_groups not in shelf["tree_groups"]:
            shelf["tree_groups"].append(prod_groups)

        ts = best["tree_score"]
        ts_max = TREE_SCORE_MAX
        if not shelf_groups_before:
            tree_reason = "Empty shelf — no conflict"
        elif ts == ts_max:
            tree_reason = "Exact full-tree match on shelf"
        elif ts > 0:
            tree_reason = f"Matched {ts} decision-tree level(s) with fallback"
        else:
            shelf_roots = ", ".join(sorted({g[0] for g in shelf_groups_before if g and g[0]})) or "other"
            tree_reason = f"Category break at root — shelf has: {shelf_roots}"

        placed.append({
            "product_code": product_code,
            "tiny_name": tiny_name,
            "avg_sale_amount": avg_sale,
            "planogram_shelf": (f"Bay {eq_num}, Shelf {shelf_num}" if eq_num is not None else ""),
            "actual_shelf": f"Bay {shelf_key[0]}, Shelf {shelf_key[1]}",
            "shelf_delta": best["shelf_delta"],
            "needed_cm": round(needed_cm, 1),
            "install_facings": install_facings,
            "unit_width_cm": round(unit_width_cm, 1),
            "space_source": best["space_source"],
            "tree_score": ts,
            "tree_score_max": ts_max,
            "tree_group": " > ".join(g for g in prod_groups if g) or "(unknown category)",
            "tree_follows_dt": ts >= 1,
            "tree_reason": tree_reason,
            "shelf_groups_before": "; ".join(
                " > ".join(g for g in grp if g) for grp in shelf_groups_before
            ) or "—",
            "time_min": best["time_min"],
            "reductions_required": best["reductions"],
            "relocations_required": best.get("relocations", []),
            "opportunistic": False,
        })

    # ── Opportunistic fill pass: retry unplaced products with relaxed constraints ──
    # Goal: use visible free space even for weaker tree matches.
    opportunistic_added = 0
    for action in sorted(deferred_for_opportunistic, key=lambda x: float(x.get("avg_sale_amount") or 0), reverse=True):
        product_code = action.get("product_code", "")
        tiny_name = action.get("tiny_name", "")
        unit_width_cm = max(1.0, float(action.get("width_cm") or 8.5))
        install_facings = max(1, int(action.get("planogram_facings") or 1))
        needed_cm = round(unit_width_cm * install_facings, 1)
        avg_sale = float(action.get("avg_sale_amount") or 0)

        attrs = product_attrs.get(product_code, {})
        prod_groups = _group_for_attrs(attrs)

        options = []
        for shelf_key, shelf in shelves.items():
            fit = _compute_fit(shelf, needed_cm)
            if fit is None:
                fit = _try_relocation_fit(shelves, shelf_key, needed_cm, product_attrs)
            if fit is None:
                continue
            tree_score = _score_tree_insertion(prod_groups, shelf["tree_groups"])
            options.append({
                "shelf_key": shelf_key,
                "tree_score": tree_score,
                **fit,
            })

        if not options:
            continue

        best = max(options, key=lambda o: (o["tree_score"], -o["time_min"]))
        shelf_key = best["shelf_key"]
        shelf = shelves[shelf_key]
        shelf_groups_before = list(shelf["tree_groups"])
        reduction_time = sum(r.get("time_min", 1) for r in best.get("reductions", []))
        best["time_min"] = reduction_time + 1 * install_facings
        _apply_fit(shelf, best, needed_cm)

        if prod_groups not in shelf["tree_groups"]:
            shelf["tree_groups"].append(prod_groups)

        ts = best["tree_score"]
        ts_max = TREE_SCORE_MAX
        if not shelf_groups_before:
            tree_reason = "Opportunistic fill on empty shelf"
        elif ts > 0:
            tree_reason = f"Opportunistic fill, matched {ts} level(s)"
        else:
            tree_reason = "Opportunistic fill despite weak tree match"

        target_key = planogram_target.get(product_code)
        eq_num, shelf_num = target_key if target_key else (None, None)

        placed.append({
            "product_code": product_code,
            "tiny_name": tiny_name,
            "avg_sale_amount": avg_sale,
            "planogram_shelf": (f"Bay {eq_num}, Shelf {shelf_num}" if eq_num is not None else ""),
            "actual_shelf": f"Bay {shelf_key[0]}, Shelf {shelf_key[1]}",
            "shelf_delta": abs(shelf_key[1] - shelf_num) if shelf_num is not None else 0,
            "needed_cm": round(needed_cm, 1),
            "install_facings": install_facings,
            "unit_width_cm": round(unit_width_cm, 1),
            "space_source": "opportunistic_" + best["space_source"],
            "tree_score": ts,
            "tree_score_max": ts_max,
            "tree_group": " > ".join(g for g in prod_groups if g) or "(unknown category)",
            "tree_follows_dt": ts >= 1,
            "tree_reason": tree_reason,
            "shelf_groups_before": "; ".join(
                " > ".join(g for g in grp if g) for grp in shelf_groups_before
            ) or "—",
            "time_min": best["time_min"],
            "reductions_required": best["reductions"],
            "relocations_required": best.get("relocations", []),
            "opportunistic": True,
        })
        opportunistic_added += 1
        unplaced = [u for u in unplaced if u.get("product_code") != product_code]

    tree_scores = [p["tree_score"] for p in placed]
    installed_sales = sum(p["avg_sale_amount"] for p in placed)
    total_time = sum(p["time_min"] for p in placed)
    follows_dt = sum(1 for p in placed if p["tree_follows_dt"])

    return {
        "placed": placed,
        "unplaced": unplaced,
        "summary": {
            "total_out_of_shelf": len(actions),
            "placed_count": len(placed),
            "unplaced_count": len(unplaced),
            "placed_via_free_space": sum(1 for p in placed if p["space_source"] == "free_space"),
            "placed_via_reduction": sum(1 for p in placed if p["space_source"] == "excess_facings"),
            "total_facings_removed": sum(
                sum(r["reduce_from"] - r["reduce_to"] for r in p["reductions_required"])
                for p in placed
            ),
            "total_time_min": total_time,
            "installed_sales_value": round(installed_sales, 1),
            "tree_compliance_pct": round(
                sum(tree_scores) / max(len(tree_scores) * TREE_SCORE_MAX, 1) * 100, 1
            ),
            "follows_dt_count": follows_dt,
            "violates_dt_count": len(placed) - follows_dt,
            "tree_score_max": TREE_SCORE_MAX,
            "tree_depth_levels": TREE_LEVEL_KEYS,
            "opportunistic_added_count": opportunistic_added,
        },
    }


# ── Step 5: Run all strategies and pick best ───────────────────────────────────

STRATEGIES = [
    ("sales_first_strict",   "Sales-First (Strict Shelf)"),
    ("sales_first_flexible", "Sales-First (±1 Shelf)"),
    ("tree_first",           "Tree-Compliance First"),
    ("min_time",             "Minimum Time"),
]

# Scoring weights for the combined score used to rank strategies.
# Adjust here without touching other modules.
WEIGHT_REVENUE = 0.4
WEIGHT_TREE    = 0.3
WEIGHT_TIME    = 0.3


def run_all_strategies(
    actions: list,
    shelf_state: Dict[ShelfKey, dict],
    planogram_target: Dict[str, ShelfKey],
    product_attrs: Dict[str, dict],
) -> List[dict]:
    """Run all placement strategies and return them ranked by combined score.

    Combined score = WEIGHT_REVENUE * revenue_ratio
                   + WEIGHT_TREE    * tree_compliance_ratio
                   + WEIGHT_TIME    * time_efficiency_ratio
    """
    max_possible_sales = max(sum(float(a.get("avg_sale_amount") or 0) for a in actions), 1)
    max_possible_time = max(len(actions) * (5 * 2 + 2), 1)

    results = []
    for strategy_key, strategy_name in STRATEGIES:
        result = _run_strategy(actions, shelf_state, planogram_target, product_attrs, strategy_key)
        s = result["summary"]
        combined_score = round(
            WEIGHT_REVENUE * s["installed_sales_value"] / max_possible_sales
            + WEIGHT_TREE   * s["tree_compliance_pct"] / 100
            + WEIGHT_TIME   * max(0.0, 1.0 - s["total_time_min"] / max_possible_time),
            3,
        )
        results.append({
            "strategy": strategy_key,
            "strategy_name": strategy_name,
            "combined_score": combined_score,
            "recommended": False,
            **result,
        })

    results.sort(key=lambda r: r["combined_score"], reverse=True)
    if results:
        results[0]["recommended"] = True
    return results


# ── Step 6: Apply best plan to produce new shelf state ─────────────────────────

def _parse_shelf_label(label: str) -> Tuple[Optional[int], Optional[int]]:
    m = _re.search(r"Bay\s+(\d+)[,\s]+Shelf\s+(\d+)", label, _re.IGNORECASE)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def apply_placement_plan(
    shelf_state: Dict[ShelfKey, dict],
    placed_products: list,
    product_attrs: Optional[Dict[str, dict]] = None,
) -> Dict[ShelfKey, dict]:
    """Apply a placement plan to produce a new (proposed) shelf state.

    Does NOT mutate the original shelf_state — returns a deep copy.

    When product_attrs is provided, new products are inserted adjacent to
    existing products of the same brand so that brand blocks stay together.
    """
    attrs = product_attrs or {}

    new_state = copy.deepcopy(shelf_state)
    shelf_prod_index: Dict[ShelfKey, Dict[str, dict]] = {
        key: {p["product_code"]: p for p in shelf["products"]}
        for key, shelf in new_state.items()
    }

    # Pass 1: apply facing reductions
    for placement in placed_products:
        bay_num, shelf_num = _parse_shelf_label(placement.get("actual_shelf", ""))
        shelf = new_state.get((bay_num, shelf_num))
        if shelf is None:
            continue
        prod_idx = shelf_prod_index.get((bay_num, shelf_num), {})
        for red in placement.get("reductions_required", []):
            prod = prod_idx.get(red["product_code"])
            if prod is None:
                continue
            old_f = prod["photo_facings"]
            new_f = max(red["reduce_to"], prod.get("planogram_facings", 1))
            delta_cm = (old_f - new_f) * prod["width_cm"]
            prod["photo_facings"] = new_f
            shelf["used_cm"] = round(shelf["used_cm"] - delta_cm, 2)
            shelf["free_cm"] = round(shelf["free_cm"] + delta_cm, 2)

    # Pass 2: install new products, grouped next to same-brand neighbours
    for placement in placed_products:
        bay_num, shelf_num = _parse_shelf_label(placement.get("actual_shelf", ""))
        shelf = new_state.get((bay_num, shelf_num))
        if shelf is None:
            continue
        install_facings = placement.get("install_facings", 1)
        unit_width_cm   = placement.get("unit_width_cm", placement["needed_cm"])
        total_width_cm  = placement["needed_cm"]
        new_code = placement["product_code"]
        new_prod = {
            "product_code": new_code,
            "tiny_name": placement["tiny_name"],
            "planogram_facings": install_facings,
            "photo_facings": install_facings,
            "width_cm": unit_width_cm,
            "avg_sale_amount": placement["avg_sale_amount"],
            "is_new": True,
        }

        # Find the best insertion index: right after the last product that
        # shares the same brand as the new product.  This keeps brand blocks
        # contiguous in the proposed planogram visual.
        #
        # Matching strategy (in order):
        #   1. brand_name exact match (case-insensitive) — covers most cases.
        #   2. tiny_name prefix (first 3 chars) fallback — handles Latin/Cyrillic
        #      brand-name variants (e.g. "NESCAFE" vs "НЕСКАФЕ").
        new_brand = attrs.get(new_code, {}).get("brand_name", "").strip().lower()
        raw_prefix = placement.get("tiny_name", "")[:3]
        # Only use prefix matching when the prefix has real brand characters
        # (not just underscores, which are placeholder codes).
        new_prefix = raw_prefix.lower() if raw_prefix.replace("_", "") else ""
        insert_idx = None
        for i, p in enumerate(shelf["products"]):
            p_brand = attrs.get(p["product_code"], {}).get("brand_name", "").strip().lower()
            raw_p_prefix = p.get("tiny_name", "")[:3]
            p_prefix = raw_p_prefix.lower() if raw_p_prefix.replace("_", "") else ""
            brand_match  = new_brand and p_brand and p_brand == new_brand
            prefix_match = new_prefix and p_prefix and p_prefix == new_prefix
            if brand_match or prefix_match:
                insert_idx = i + 1  # keep scanning to find the last match

        if insert_idx is not None:
            shelf["products"].insert(insert_idx, new_prod)
        else:
            shelf["products"].append(new_prod)

        shelf_prod_index[(bay_num, shelf_num)][new_code] = new_prod
        shelf["used_cm"] = round(shelf["used_cm"] + total_width_cm, 2)
        shelf["free_cm"] = round(shelf["free_cm"] - total_width_cm, 2)

    return new_state


# ── Step 7: Build visual output ────────────────────────────────────────────────

def _product_color(product_code: str) -> str:
    hue = int(hashlib.md5(product_code.encode()).hexdigest()[:6], 16) % 360
    return f"hsl({hue}, 55%, 55%)"


def build_visual(
    new_state: Dict[ShelfKey, dict],
    original_state: Dict[ShelfKey, dict],
    placed_products: list,
    product_attrs: Dict[str, dict],
) -> List[dict]:
    """Build a list of bay dicts for the frontend visualisation.

    Each product entry carries:
        change_type   "new" | "reduced" | "existing"
        reduced_from  (only when change_type == "reduced")
        image_url, recognition_id, product_name, brand_name, color, …
    """
    original_facings: Dict[Tuple, int] = {}
    for key, shelf in original_state.items():
        for prod in shelf.get("products", []):
            original_facings[(key[0], key[1], prod["product_code"])] = prod["photo_facings"]

    new_product_codes = {p["product_code"] for p in placed_products}
    bays_dict: Dict[int, Dict[int, dict]] = {}

    for key in sorted(new_state.keys()):
        eq_num, shelf_num = key
        shelf = new_state[key]
        bays_dict.setdefault(eq_num, {})

        products_out = []
        for prod in shelf.get("products", []):
            code = prod["product_code"]
            facings = prod["photo_facings"]
            width_cm = prod.get("width_cm", 8.5)
            orig_f = original_facings.get((eq_num, shelf_num, code))

            if prod.get("is_new") or (orig_f is None and code in new_product_codes):
                change_type = "new"
            elif orig_f is not None and facings < orig_f:
                change_type = "reduced"
            else:
                change_type = "existing"

            attrs = product_attrs.get(code, {})
            no_bg = (attrs.get("image_no_bg_url") or "").strip()
            mini_or_display = (attrs.get("image_url") or "").strip()
            entry: dict = {
                "product_code": code,
                "tiny_name": prod.get("tiny_name", code),
                "product_name": attrs.get("product_name") or prod.get("tiny_name", code),
                "facings": facings,
                "width_cm": round(width_cm, 2),
                "total_width_cm": round(width_cm * facings, 2),
                "avg_sale_amount": prod.get("avg_sale_amount", 0),
                "change_type": change_type,
                "color": _product_color(code),
                "image_no_bg_url": no_bg,
                "image_url": no_bg or mini_or_display,
                "recognition_id": attrs.get("recognition_id") or "",
            }
            if change_type == "reduced" and orig_f is not None:
                entry["reduced_from"] = orig_f
            if attrs.get("brand_name"):
                entry["brand_name"] = attrs["brand_name"]
            products_out.append(entry)

        bays_dict[eq_num][shelf_num] = {
            "shelf_number": shelf_num,
            "width_cm": shelf["total_width_cm"],
            "used_cm": round(shelf.get("used_cm", 0.0), 1),
            "free_cm": round(shelf.get("free_cm", 0.0), 1),
            "products": products_out,
        }

    bays_list = []
    for eq_num in sorted(bays_dict.keys()):
        shelves_list = [bays_dict[eq_num][sn] for sn in sorted(bays_dict[eq_num].keys())]
        total_width = max((s["width_cm"] for s in shelves_list), default=120.0)
        bays_list.append({"bay_number": eq_num, "width_cm": round(total_width, 1), "shelves": shelves_list})

    return bays_list


# ── Main entry point ───────────────────────────────────────────────────────────

def run_optimization(
    realogram_positions: list,
    product_map_rows: list,
    planogram_rows: list,
    sales_rows: list,
    actions: list,
) -> ProposedResult:
    """Full pipeline: realogram → proposed planogram.

    Args:
        realogram_positions: saved realogram position rows.
        product_map_rows:    product map with sizes, names, images.
        planogram_rows:      planogram target positions (where things SHOULD go).
        sales_rows:          historical sales for prioritisation.
        actions:             out-of-shelf actions to attempt to install.

    Returns:
        ProposedResult with best strategy applied.
    """
    shelf_state, planogram_target, product_attrs = build_shelf_state_from_realogram(
        realogram_positions, product_map_rows, planogram_rows, sales_rows
    )

    merge_product_map_images(product_attrs, product_map_rows)
    pm_by_code = {
        r.get("product_code"): r
        for r in product_map_rows
        if r.get("product_code")
    }

    # Enrich product_attrs from action metadata (product_name, brand, etc.)
    for action in actions:
        code = action.get("product_code", "")
        if not code:
            continue
        attrs = product_attrs.setdefault(code, {})
        pm = pm_by_code.get(code, {})
        if not attrs.get("product_name"):
            attrs["product_name"] = (
                pm.get("product_name")
                or action.get("product_name")
                or action.get("tiny_name", "")
            )
        if not attrs.get("brand_name"):
            attrs["brand_name"] = pm.get("brand") or action.get("brand", "")
        if not attrs.get("brand_owner_name"):
            attrs["brand_owner_name"] = pm.get("brand") or action.get("brand", "")
        if not attrs.get("category_l0"):
            attrs["category_l0"] = pm.get("category_l0") or action.get("category_l0", "")
        if not attrs.get("category_l1"):
            attrs["category_l1"] = pm.get("category_l1") or action.get("category_l1", "")
        if not attrs.get("category_l2"):
            attrs["category_l2"] = pm.get("category_l2") or action.get("category_l2", "")
        if not attrs.get("category_l3"):
            attrs["category_l3"] = pm.get("category_l3") or action.get("category_l3", "")
        if not attrs.get("package_type"):
            attrs["package_type"] = pm.get("package_type") or action.get("package_type", "")
        if not attrs.get("category_name"):
            attrs["category_name"] = (
                attrs.get("category_l2")
                or pm.get("category_l2")
                or attrs.get("category_l1")
                or pm.get("category_l1")
                or action.get("category_l2")
                or action.get("category_l1", "")
            )
        _normalize_attrs_inplace(attrs)

    if not actions:
        bays = build_visual(shelf_state, shelf_state, [], product_attrs)
        return ProposedResult(
            strategy="No out-of-shelf actions",
            combined_score=1.0,
            summary={"placed_count": 0, "total_out_of_shelf": 0, "total_time_min": 0},
            actions=[],
            bays=bays,
            all_runs=[],
        )

    all_runs = run_all_strategies(actions, shelf_state, planogram_target, product_attrs)
    best = next((r for r in all_runs if r.get("recommended")), all_runs[0])

    new_state = apply_placement_plan(shelf_state, best["placed"], product_attrs)
    bays = build_visual(new_state, shelf_state, best["placed"], product_attrs)

    # Build merged actions list for the frontend
    placed_by_code = {p["product_code"]: p for p in best["placed"]}
    unplaced_by_code = {u["product_code"]: u for u in best["unplaced"]}
    actions_out = []
    for action in actions:
        code = action.get("product_code", "")
        placement = placed_by_code.get(code)
        actions_out.append({
            "product_code": code,
            "product_name": action.get("product_name") or action.get("tiny_name", ""),
            "tiny_name": action.get("tiny_name", ""),
            "brand": action.get("brand", ""),
            "priority": action.get("priority", ""),
            "avg_sale_amount": float(action.get("avg_sale_amount") or 0),
            "planogram_facings": action.get("planogram_facings", 1),
            "width_cm": action.get("width_cm", 0),
            "category_l0": action.get("category_l0", ""),
            "category_l1": action.get("category_l1", ""),
            "category_l2": action.get("category_l2", ""),
            "installed": bool(placement),
            "actual_shelf": placement.get("actual_shelf", "") if placement else "",
            "planogram_shelf": placement.get("planogram_shelf", "") if placement else "",
            "install_facings": placement.get("install_facings", 1) if placement else 0,
            "time_min": placement.get("time_min", 0) if placement else 0,
            "space_source": placement.get("space_source", "") if placement else "",
            "reductions": placement.get("reductions_required", []) if placement else [],
            "relocations": placement.get("relocations_required", []) if placement else [],
            "opportunistic": placement.get("opportunistic", False) if placement else False,
            "tree_score": placement.get("tree_score") if placement else None,
            "tree_score_max": placement.get("tree_score_max", TREE_SCORE_MAX) if placement else TREE_SCORE_MAX,
            "tree_group": placement.get("tree_group", "") if placement else "",
            "tree_follows_dt": placement.get("tree_follows_dt", False) if placement else False,
            "tree_reason": placement.get("tree_reason", "") if placement else "",
            "shelf_groups_before": placement.get("shelf_groups_before", "") if placement else "",
            "reason": unplaced_by_code.get(code, {}).get("reason", "") if not placement else "",
        })

    return ProposedResult(
        strategy=best["strategy_name"],
        combined_score=best["combined_score"],
        summary=best["summary"],
        actions=actions_out,
        bays=bays,
        all_runs=[{
            "strategy": r["strategy"],
            "strategy_name": r["strategy_name"],
            "combined_score": r["combined_score"],
            "recommended": r["recommended"],
            "summary": r["summary"],
        } for r in all_runs],
    )
