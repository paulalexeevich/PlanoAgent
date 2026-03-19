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
            product_name, width_cm, height_cm, image_no_bg_url.
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
            }
            img = r.get("image_no_bg_url") or ""
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
            product_attrs[product_code] = {
                "category_name": row.get("category", ""),
                "brand_name": row.get("brand", ""),
                "brand_owner_name": row.get("brand", ""),
                "image_url": image_url,
                "product_name": sz.get("name") or row.get("product_name", "") or tiny_name,
                "recognition_id": pid,
            }

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
            grp = (
                attrs.get("category_name", ""),
                attrs.get("brand_owner_name", "") or attrs.get("brand_name", ""),
                attrs.get("brand_name", ""),
            )
            if any(g for g in grp) and grp not in shelf["tree_groups"]:
                shelf["tree_groups"].append(grp)

    return shelves, planogram_target, product_attrs


# ── Step 2: Tree scoring ────────────────────────────────────────────────────────

def _score_tree_insertion(prod_groups: tuple, shelf_tree_groups: list) -> int:
    """Score how well a product fits a shelf from a decision tree perspective.

    Returns:
        2 — perfect match (exact brand/subcategory group already on shelf)
        1 — compatible (same top-level category, different brand)
        0 — category break (different category)
    """
    if not shelf_tree_groups:
        return 1  # empty shelf → no conflict, but not "perfect"
    if prod_groups in shelf_tree_groups:
        return 2
    prod_cat = prod_groups[0] if prod_groups else ""
    shelf_cats = {g[0] for g in shelf_tree_groups if g}
    if prod_cat and prod_cat in shelf_cats:
        return 1
    return 0


# ── Step 3: Fit computation (non-mutating) ─────────────────────────────────────

def _compute_fit(shelf: dict, needed_cm: float) -> Optional[dict]:
    """Evaluate whether a product fits on a shelf WITHOUT mutating shelf state.

    Returns a fit dict or None if no space is available even after reductions.
    """
    if shelf["free_cm"] >= needed_cm:
        return {"space_source": "free_space", "reductions": [], "time_min": 2}

    if shelf["net_available_cm"] < needed_cm:
        return None

    reductions = []
    time_min = 2
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
            "time_min": take * 2,
        })
        time_min += take * 2
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
    sales_first_strict   — highest sales first, only exact planogram shelf
    sales_first_flexible — highest sales first, ±1 shelf allowed
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
                product_attrs.get(x.get("product_code", ""), {}).get("category_name", "zzz"),
                -float(x.get("avg_sale_amount") or 0),
            ),
        )
    elif strategy == "min_time":
        def _min_time_key(a):
            tgt = planogram_target.get(a.get("product_code", ""))
            needed = float(a.get("width_cm") or 8.5)
            if tgt and shelves.get(tgt, {}).get("free_cm", 0) >= needed:
                return (0, -float(a.get("avg_sale_amount") or 0))
            return (1, -float(a.get("avg_sale_amount") or 0))
        sorted_actions = sorted(actions, key=_min_time_key)
    else:
        sorted_actions = list(actions)

    placed: list = []
    unplaced: list = []

    for action in sorted_actions:
        product_code = action.get("product_code", "")
        tiny_name = action.get("tiny_name", "")
        unit_width_cm = max(1.0, float(action.get("width_cm") or 8.5))
        install_facings = max(1, int(action.get("planogram_facings") or 1))
        needed_cm = round(unit_width_cm * install_facings, 1)
        avg_sale = float(action.get("avg_sale_amount") or 0)

        target_key = planogram_target.get(product_code)
        if not target_key:
            unplaced.append({"product_code": product_code, "tiny_name": tiny_name,
                             "avg_sale_amount": avg_sale, "reason": "No planogram position found"})
            continue

        eq_num, shelf_num = target_key
        candidate_keys = (
            [target_key]
            if strategy == "sales_first_strict"
            else [k for k in [(eq_num, shelf_num), (eq_num, shelf_num - 1), (eq_num, shelf_num + 1)]
                  if k in shelves]
        )

        attrs = product_attrs.get(product_code, {})
        prod_groups = (
            attrs.get("category_name", ""),
            attrs.get("brand_owner_name", "") or attrs.get("brand_name", ""),
            attrs.get("brand_name", ""),
        )

        # For flexible strategies, also consider shelves where the product's
        # category already exists (tree score == 2).  This ensures products land
        # next to their category peers rather than just ±1 from planogram.
        # If no perfect-match shelf is found anywhere in the bay, also try
        # compatible (score 1) shelves so products with sparse realogram data
        # still have options beyond the narrow ±1 window.
        if strategy != "sales_first_strict":
            bay_shelves = sorted(k for k in shelves if k[0] == eq_num and k not in candidate_keys)
            tree2_keys = [k for k in bay_shelves
                          if _score_tree_insertion(prod_groups, shelves[k]["tree_groups"]) == 2]
            candidate_keys += tree2_keys
            if not tree2_keys:  # no perfect match — try category-compatible shelves
                tree1_keys = [k for k in bay_shelves
                              if _score_tree_insertion(prod_groups, shelves[k]["tree_groups"]) == 1]
                candidate_keys += tree1_keys

        options = []
        for shelf_key in candidate_keys:
            shelf = shelves[shelf_key]
            fit = _compute_fit(shelf, needed_cm)
            if fit is None:
                continue
            tree_score = _score_tree_insertion(prod_groups, shelf["tree_groups"])
            options.append({"shelf_key": shelf_key, "shelf_delta": abs(shelf_key[1] - shelf_num),
                            "tree_score": tree_score, **fit})

        if not options:
            unplaced.append({"product_code": product_code, "tiny_name": tiny_name,
                             "avg_sale_amount": avg_sale,
                             "reason": "Insufficient space after all excess facing reductions exhausted"})
            continue

        best = max(options, key=lambda o: (o["tree_score"], -o["time_min"]))
        shelf_key = best["shelf_key"]
        shelf = shelves[shelf_key]
        shelf_groups_before = list(shelf["tree_groups"])

        # Recalculate time: 2 min per facing installed + reduction removal time
        reduction_time = sum(r.get("time_min", 2) for r in best.get("reductions", []))
        best["time_min"] = reduction_time + 2 * install_facings

        _apply_fit(shelf, best, needed_cm)

        if prod_groups not in shelf["tree_groups"]:
            shelf["tree_groups"].append(prod_groups)

        ts = best["tree_score"]
        if not shelf_groups_before:
            tree_reason = "Empty shelf — no conflict"
        elif ts == 2:
            tree_reason = "Exact group match on shelf"
        elif ts == 1:
            tree_reason = "Same category, different brand"
        else:
            shelf_cats = ", ".join(sorted({g[0] for g in shelf_groups_before if g and g[0]})) or "other"
            tree_reason = f"Category break — shelf has: {shelf_cats}"

        placed.append({
            "product_code": product_code,
            "tiny_name": tiny_name,
            "avg_sale_amount": avg_sale,
            "planogram_shelf": f"Bay {eq_num}, Shelf {shelf_num}",
            "actual_shelf": f"Bay {shelf_key[0]}, Shelf {shelf_key[1]}",
            "shelf_delta": best["shelf_delta"],
            "needed_cm": round(needed_cm, 1),
            "install_facings": install_facings,
            "unit_width_cm": round(unit_width_cm, 1),
            "space_source": best["space_source"],
            "tree_score": ts,
            "tree_score_max": 2,
            "tree_group": " > ".join(g for g in prod_groups if g) or "(unknown category)",
            "tree_follows_dt": ts >= 1,
            "tree_reason": tree_reason,
            "shelf_groups_before": "; ".join(
                " > ".join(g for g in grp if g) for grp in shelf_groups_before
            ) or "—",
            "time_min": best["time_min"],
            "reductions_required": best["reductions"],
        })

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
            "tree_compliance_pct": round(sum(tree_scores) / max(len(tree_scores) * 2, 1) * 100, 1),
            "follows_dt_count": follows_dt,
            "violates_dt_count": len(placed) - follows_dt,
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
) -> Dict[ShelfKey, dict]:
    """Apply a placement plan to produce a new (proposed) shelf state.

    Does NOT mutate the original shelf_state — returns a deep copy.
    """
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

    # Pass 2: install new products
    for placement in placed_products:
        bay_num, shelf_num = _parse_shelf_label(placement.get("actual_shelf", ""))
        shelf = new_state.get((bay_num, shelf_num))
        if shelf is None:
            continue
        install_facings = placement.get("install_facings", 1)
        unit_width_cm   = placement.get("unit_width_cm", placement["needed_cm"])
        total_width_cm  = placement["needed_cm"]
        new_prod = {
            "product_code": placement["product_code"],
            "tiny_name": placement["tiny_name"],
            "planogram_facings": install_facings,
            "photo_facings": install_facings,
            "width_cm": unit_width_cm,
            "avg_sale_amount": placement["avg_sale_amount"],
            "is_new": True,
        }
        shelf["products"].append(new_prod)
        shelf_prod_index[(bay_num, shelf_num)][placement["product_code"]] = new_prod
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
                "image_url": attrs.get("image_url") or "",
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

    # Enrich product_attrs from action metadata (product_name, brand, etc.)
    for action in actions:
        code = action.get("product_code", "")
        if not code:
            continue
        attrs = product_attrs.setdefault(code, {})
        if not attrs.get("product_name"):
            attrs["product_name"] = action.get("product_name") or action.get("tiny_name", "")
        if not attrs.get("brand_name"):
            attrs["brand_name"] = action.get("brand", "")
        if not attrs.get("category_name"):
            attrs["category_name"] = action.get("category_l1", "")

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

    new_state = apply_placement_plan(shelf_state, best["placed"])
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
            "category_l1": action.get("category_l1", ""),
            "installed": bool(placement),
            "actual_shelf": placement.get("actual_shelf", "") if placement else "",
            "planogram_shelf": placement.get("planogram_shelf", "") if placement else "",
            "install_facings": placement.get("install_facings", 1) if placement else 0,
            "time_min": placement.get("time_min", 0) if placement else 0,
            "space_source": placement.get("space_source", "") if placement else "",
            "reductions": placement.get("reductions_required", []) if placement else [],
            "tree_score": placement.get("tree_score") if placement else None,
            "tree_score_max": placement.get("tree_score_max", 2) if placement else 2,
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
