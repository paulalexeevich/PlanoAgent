"""
Product Logic — Rules & Algorithms for Filling Equipment
=========================================================
Three-phase approach:
  Phase 1: Capacity check — can all products fit at 1 facing? If not, trim by sales.
  Phase 2: Optimal facings — distribute extra facings by sales velocity until ~95% full.
  Phase 3: Placement — Gemini arranges products on shelves by decision tree; rule-based fallback.

The key principle: the ALGORITHM decides "how many facings" (math),
while Gemini AI decides "where to place" (merchandising logic).
"""

import json
import copy
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple

from planogram_schema import Equipment, Bay, Shelf, Position, Product
from decision_tree import (
    DecisionTree, get_product_group_tuple, sort_products_by_tree,
    get_tree_for_category,
)


# ── Default rule values ──────────────────────────────────────────────────────

DEFAULT_TOP_SELLER_BRANDS = [
    "Bud Light", "Coors Light", "Miller Lite", "Michelob Ultra",
]


# ── ProductLogicRules ────────────────────────────────────────────────────────

@dataclass
class ProductLogicRules:
    """Configurable rule-set that governs how products fill equipment."""

    fill_target_pct: float = 99.0           # Target fill rate
    max_facings: int = 5                     # Max facings per product
    group_by: str = "subcategory"            # "subcategory" | "brand"

    # Shelf-tier assignments (bottom → top)
    bottom_shelf_min_pack: int = 12
    bottom_shelf_subcategories: List[str] = field(default_factory=list)

    eye_level_subcategories: List[str] = field(default_factory=lambda: [
        "Craft IPA", "Craft Pale Ale", "Craft Amber Ale",
        "Craft Session IPA", "Craft Wheat Beer", "Craft Lager",
    ])

    top_shelf_subcategories: List[str] = field(default_factory=lambda: [
        "Import Lager", "Import Dark Lager", "Import Stout", "Hard Cider",
    ])

    top_seller_brands: List[str] = field(
        default_factory=lambda: list(DEFAULT_TOP_SELLER_BRANDS)
    )

    # ── helpers ───────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return asdict(self)

    def to_prompt_text(self) -> str:
        """Render rules as human-readable merchandising instructions."""
        lines = [
            "PRODUCT PLACEMENT RULES (must follow strictly):",
            f"- Target shelf fill rate: {self.fill_target_pct}%.",
            f"- Maximum facings per product: {self.max_facings}.",
            f"- Group products by {self.group_by} on the same shelf.",
            "",
            "SHELF TIER ASSIGNMENTS (shelves numbered bottom=1 to top=N):",
            f"  Bottom shelves (1–2): Products with pack_size >= {self.bottom_shelf_min_pack}."
            + (f" Prefer subcategories: {', '.join(self.bottom_shelf_subcategories)}."
               if self.bottom_shelf_subcategories else ""),
            f"  Eye-level shelves (middle): Subcategories: {', '.join(self.eye_level_subcategories)}.",
            f"  Top shelves (upper 1–2): Subcategories: {', '.join(self.top_shelf_subcategories)}.",
            f"  Remaining products: distribute to shelves with available space.",
            "",
            "GENERAL MERCHANDISING:",
            "- Place heavier/larger items on lower shelves.",
            "- Premium & high-margin items at eye level (shelves 3–4 of 5).",
            "- Ensure brand variety across equipment — avoid all one brand.",
        ]
        return "\n".join(lines)


# ==============================================================================
# PHASE 1: Capacity Check
# ==============================================================================

def phase1_capacity_check(
    products: List[dict],
    total_shelf_width: float,
) -> List[dict]:
    """
    Check if all products fit at 1 facing each.
    If not, drop lowest-selling products until they fit.

    Returns the list of selected products (sorted by sales DESC).
    """
    # Sort by weekly_units_sold DESC (highest sellers first)
    sorted_products = sorted(
        products,
        key=lambda p: p.get("weekly_units_sold", 0),
        reverse=True,
    )

    total_width_1facing = sum(p["width_in"] for p in sorted_products)

    if total_width_1facing <= total_shelf_width:
        # All products fit
        return sorted_products

    # Drop lowest sellers until products fit
    selected = []
    running_width = 0.0
    for p in sorted_products:
        if running_width + p["width_in"] <= total_shelf_width:
            selected.append(p)
            running_width += p["width_in"]
        # else: product is dropped (doesn't fit)

    return selected


# ==============================================================================
# PHASE 2: Optimal Facings Calculation
# ==============================================================================

def phase2_optimal_facings(
    selected_products: List[dict],
    total_shelf_width: float,
    rules: ProductLogicRules,
) -> Dict[str, int]:
    """
    Calculate optimal facing count for each product to fill ~95% of shelf space.

    Algorithm:
      1. Start with 1 facing per product.
      2. Remaining space = total - sum(widths).
      3. Iterate through products by sales rank.
      4. For each product, try adding 1 more facing. If it fits, add it.
      5. Repeat rounds until no more facings can be added or we hit target.

    Returns: dict mapping product_id → facing count.
    """
    target_width = total_shelf_width * (rules.fill_target_pct / 100.0)

    # Initialize: 1 facing each
    facings: Dict[str, int] = {}
    for p in selected_products:
        facings[p["id"]] = 1

    used_width = sum(p["width_in"] for p in selected_products)

    # Sort by sales DESC for extra facings priority
    sales_sorted = sorted(
        selected_products,
        key=lambda p: p.get("weekly_units_sold", 0),
        reverse=True,
    )

    # Minimum product width (used as stop threshold)
    min_width = min(p["width_in"] for p in selected_products) if selected_products else 0

    # Iteratively add facings
    max_rounds = 20  # safety cap
    for round_num in range(max_rounds):
        added_any = False

        for p in sales_sorted:
            pid = p["id"]
            pw = p["width_in"]

            # Already at max facings?
            if facings[pid] >= rules.max_facings:
                continue

            # Can we fit one more facing?
            if used_width + pw <= total_shelf_width:
                facings[pid] += 1
                used_width += pw
                added_any = True

            # Hit target?
            if used_width >= target_width:
                break

        if not added_any or used_width >= target_width:
            break

    return facings


# ==============================================================================
# PHASE 3a: Rule-based placement (deterministic fallback)
# ==============================================================================

def _classify_product(product: dict, rules: ProductLogicRules) -> str:
    """Return tier label for a product: 'bottom', 'eye', 'top', or 'middle'."""
    pack_size = product.get("pack_size", 1)
    subcat = product.get("subcategory", "")

    if pack_size >= rules.bottom_shelf_min_pack:
        return "bottom"
    if subcat in rules.eye_level_subcategories:
        return "eye"
    if subcat in rules.top_shelf_subcategories:
        return "top"
    return "middle"


def _shelf_tier_for_index(shelf_idx: int, total_shelves: int) -> str:
    """Map a shelf index (0-based, bottom=0) to a tier label."""
    if total_shelves <= 2:
        return ["bottom", "eye"][shelf_idx] if shelf_idx < 2 else "top"
    bottom_end = max(1, total_shelves // 4)
    top_start = total_shelves - max(1, total_shelves // 4)
    if shelf_idx < bottom_end:
        return "bottom"
    if shelf_idx >= top_start:
        return "top"
    mid = (bottom_end + top_start) // 2
    return "eye" if shelf_idx >= mid else "middle"


def phase3_rule_based_placement(
    equipment_dict: dict,
    selected_products: List[dict],
    facings: Dict[str, int],
    rules: ProductLogicRules,
    decision_tree: Optional[DecisionTree] = None,
) -> dict:
    """
    Place products on shelves using deterministic rules.
    Uses pre-calculated facings from Phase 2.
    """
    # Build product lookup
    prod_map = {p["id"]: p for p in selected_products}

    # Classify products into tiers
    tier_buckets: Dict[str, List[dict]] = {
        "bottom": [], "middle": [], "eye": [], "top": []
    }
    for p in selected_products:
        tier = _classify_product(p, rules)
        tier_buckets[tier].append(p)

    # Sort within each tier
    for tier in tier_buckets.values():
        if decision_tree:
            tier.sort(key=lambda p: get_product_group_tuple(p, decision_tree))
        elif rules.group_by == "subcategory":
            tier.sort(key=lambda p: (p["subcategory"], p["brand"], p["name"]))
        else:
            tier.sort(key=lambda p: (p["brand"], p["subcategory"], p["name"]))

    placed_product_ids = set()

    for bay in equipment_dict.get("bays", []):
        shelves = bay.get("shelves", [])
        total_shelves = len(shelves)

        for s_idx, shelf in enumerate(shelves):
            shelf_w = shelf.get("width_in", 48)
            shelf_h = shelf.get("height_in", 12)
            tier_label = _shelf_tier_for_index(s_idx, total_shelves)

            # Priority order for this shelf tier
            priority = [tier_label, "middle", "eye", "bottom", "top"]
            seen = set()
            ordered_buckets = []
            for t in priority:
                if t not in seen:
                    ordered_buckets.append(t)
                    seen.add(t)

            positions = []
            x_pos = 0.0

            for bucket_name in ordered_buckets:
                bucket = tier_buckets[bucket_name]
                i = 0
                while i < len(bucket):
                    prod = bucket[i]
                    pid = prod["id"]
                    pw = prod["width_in"]
                    f = facings.get(pid, 1)
                    total_w = pw * f

                    # Height check
                    if prod["height_in"] > shelf_h:
                        i += 1
                        continue

                    # Width check — must fit on this shelf
                    if x_pos + total_w > shelf_w + 0.1:  # small tolerance
                        # Try with fewer facings
                        max_fit = int((shelf_w - x_pos) / pw) if pw > 0 else 0
                        if max_fit < 1:
                            i += 1
                            continue
                        f = min(f, max_fit)
                        total_w = pw * f

                    positions.append({
                        "product_id": pid,
                        "x_position": round(x_pos, 2),
                        "facings_wide": f,
                        "facings_high": 1,
                        "facings_deep": 1,
                        "orientation": "front",
                    })
                    x_pos += total_w
                    placed_product_ids.add(pid)
                    bucket.pop(i)

            shelf["positions"] = positions

    placed_products = [p for p in selected_products if p["id"] in placed_product_ids]

    return {
        "equipment": equipment_dict,
        "products": placed_products,
    }


# ==============================================================================
# Helper: calculate total shelf width from equipment
# ==============================================================================

def get_total_shelf_width(equipment_dict: dict) -> float:
    """Sum of all shelf widths across all bays."""
    total = 0.0
    for bay in equipment_dict.get("bays", []):
        for shelf in bay.get("shelves", []):
            total += shelf.get("width_in", 48)
    return total


# ==============================================================================
# POST-PROCESSING: Validate & fix shelf overflows
# ==============================================================================

def validate_and_fix_shelves(equipment_dict: dict, products_map: dict) -> dict:
    """
    Post-process AI output: ensure no shelf exceeds its width.

    For any overflowing shelf:
      1. Reduce facings on lowest-priority products.
      2. Remove products that still don't fit.
      3. Recalculate x_positions sequentially.

    Args:
        equipment_dict: filled equipment from AI
        products_map: dict of product_id → product dict (with weekly_units_sold)

    Returns:
        The fixed equipment dict (modified in-place).
    """
    fixes = 0

    for bay in equipment_dict.get("bays", []):
        for shelf in bay.get("shelves", []):
            shelf_w = shelf.get("width_in", 48)
            positions = shelf.get("positions", [])

            if not positions:
                continue

            # Calculate current total width
            total_used = 0.0
            for pos in positions:
                pid = pos.get("product_id", "")
                prod = products_map.get(pid)
                if prod:
                    pw = prod.get("width_in", 0)
                    facings = pos.get("facings_wide", 1)
                    total_used += pw * facings

            if total_used <= shelf_w + 0.5:  # tolerance
                # Shelf is fine, just re-calculate x_positions
                x = 0.0
                for pos in positions:
                    pos["x_position"] = round(x, 2)
                    prod = products_map.get(pos.get("product_id", ""))
                    if prod:
                        x += prod.get("width_in", 0) * pos.get("facings_wide", 1)
                continue

            # ── Shelf overflows — fix it ──
            fixes += 1

            # Sort positions by sales (lowest sales last = first to trim)
            positions.sort(
                key=lambda pos: products_map.get(
                    pos.get("product_id", ""), {}
                ).get("weekly_units_sold", 0),
                reverse=True,
            )

            # Pass 1: reduce facings on lowest sellers
            for pos in reversed(positions):
                pid = pos.get("product_id", "")
                prod = products_map.get(pid)
                if not prod:
                    continue
                pw = prod.get("width_in", 0)
                while total_used > shelf_w + 0.5 and pos.get("facings_wide", 1) > 1:
                    pos["facings_wide"] -= 1
                    total_used -= pw

            # Pass 2: remove products that still cause overflow
            new_positions = []
            running = 0.0
            for pos in positions:
                pid = pos.get("product_id", "")
                prod = products_map.get(pid)
                if not prod:
                    continue
                pw = prod.get("width_in", 0) * pos.get("facings_wide", 1)
                if running + pw <= shelf_w + 0.5:
                    new_positions.append(pos)
                    running += pw

            # Recalculate x_positions
            x = 0.0
            for pos in new_positions:
                pos["x_position"] = round(x, 2)
                prod = products_map.get(pos.get("product_id", ""))
                if prod:
                    x += prod.get("width_in", 0) * pos.get("facings_wide", 1)

            shelf["positions"] = new_positions

    if fixes > 0:
        print(f"[PostProcess] Fixed {fixes} overflowing shelf(s)", flush=True)

    return equipment_dict


# ==============================================================================
# POST-PROCESSING: Recover products missed by AI
# ==============================================================================

def recover_missing_products(
    equipment_dict: dict,
    selected_products: List[dict],
    facings: Dict[str, int],
    products_map: dict,
) -> Tuple[dict, List[str]]:
    """
    After AI placement + overflow fixing, find products that were NOT placed
    and insert them into shelves with remaining space.

    Strategy:
      1. Collect all product IDs currently on shelves.
      2. Find missing products (in selected list but not placed).
      3. Sort missing products by sales DESC (highest sellers recovered first).
      4. For each missing product, scan shelves for remaining space.
         - Try with assigned facings first, then reduce to 1 if needed.
      5. Recalculate x_positions on any modified shelf.

    Args:
        equipment_dict: equipment after validate_and_fix_shelves
        selected_products: list from Phase 1
        facings: dict from Phase 2 (product_id → facing count)
        products_map: dict of product_id → product dict

    Returns:
        (equipment_dict, list_of_recovered_product_ids)
    """
    # Step 1: collect placed product IDs
    placed_ids = set()
    for bay in equipment_dict.get("bays", []):
        for shelf in bay.get("shelves", []):
            for pos in shelf.get("positions", []):
                placed_ids.add(pos.get("product_id", ""))

    # Step 2: find missing products
    missing = [p for p in selected_products if p["id"] not in placed_ids]
    if not missing:
        return equipment_dict, []

    # Sort by sales DESC — recover best sellers first
    missing.sort(key=lambda p: p.get("weekly_units_sold", 0), reverse=True)

    recovered = []

    # Step 3: build a shelf-space index (remaining width per shelf)
    shelf_refs = []  # list of (bay_dict, shelf_dict, remaining_width)
    for bay in equipment_dict.get("bays", []):
        for shelf in bay.get("shelves", []):
            shelf_w = shelf.get("width_in", 48)
            shelf_h = shelf.get("height_in", 12)
            used = 0.0
            for pos in shelf.get("positions", []):
                prod = products_map.get(pos.get("product_id", ""))
                if prod:
                    used += prod.get("width_in", 0) * pos.get("facings_wide", 1)
            shelf_refs.append({
                "shelf": shelf,
                "remaining": shelf_w - used,
                "height": shelf_h,
                "width": shelf_w,
            })

    # Step 4: place each missing product
    for prod in missing:
        pid = prod["id"]
        pw = prod["width_in"]
        ph = prod["height_in"]
        assigned = facings.get(pid, 1)

        placed = False
        # Try with assigned facings, then reduce down to 1
        for try_facings in range(assigned, 0, -1):
            need_width = pw * try_facings

            # Find best-fit shelf (smallest remaining that still fits)
            best_idx = -1
            best_remaining = float("inf")
            for i, sr in enumerate(shelf_refs):
                if ph <= sr["height"] and need_width <= sr["remaining"] + 0.5:
                    if sr["remaining"] < best_remaining:
                        best_remaining = sr["remaining"]
                        best_idx = i

            if best_idx >= 0:
                sr = shelf_refs[best_idx]
                shelf = sr["shelf"]
                positions = shelf.get("positions", [])

                # Calculate x_position = end of current positions
                x_pos = 0.0
                for pos in positions:
                    p_data = products_map.get(pos.get("product_id", ""))
                    if p_data:
                        x_pos += p_data.get("width_in", 0) * pos.get("facings_wide", 1)

                positions.append({
                    "product_id": pid,
                    "x_position": round(x_pos, 2),
                    "facings_wide": try_facings,
                    "facings_high": 1,
                    "facings_deep": 1,
                    "orientation": "front",
                })
                shelf["positions"] = positions
                sr["remaining"] -= need_width
                recovered.append(pid)
                placed = True
                break

        if not placed:
            # Could not fit this product anywhere — skip it
            pass

    if recovered:
        print(f"[Recovery] Placed {len(recovered)} missing product(s) "
              f"({len(missing)} were missing, {len(missing) - len(recovered)} could not fit)",
              flush=True)

    return equipment_dict, recovered


# ==============================================================================
# POST-PROCESSING: Reconcile facings (boost underused shelves)
# ==============================================================================

def boost_underused_shelves(
    equipment_dict: dict,
    products_map: dict,
    facings: Dict[str, int],
    max_facings: int = 5,
) -> dict:
    """
    After recovery, if shelves still have significant remaining space,
    boost facings on existing products (highest sellers first) to fill gaps.

    This addresses the case where AI used fewer facings than assigned.

    Returns:
        The modified equipment dict.
    """
    boosted = 0

    for bay in equipment_dict.get("bays", []):
        for shelf in bay.get("shelves", []):
            shelf_w = shelf.get("width_in", 48)
            positions = shelf.get("positions", [])
            if not positions:
                continue

            # Calculate current usage
            used = 0.0
            for pos in positions:
                prod = products_map.get(pos.get("product_id", ""))
                if prod:
                    used += prod.get("width_in", 0) * pos.get("facings_wide", 1)

            remaining = shelf_w - used
            if remaining < 2.0:  # less than 2 inches free — not worth boosting
                continue

            # Sort positions by sales DESC — boost best sellers first
            scored = []
            for pos in positions:
                prod = products_map.get(pos.get("product_id", ""))
                sales = prod.get("weekly_units_sold", 0) if prod else 0
                scored.append((sales, pos, prod))
            scored.sort(key=lambda x: x[0], reverse=True)

            changed = False
            # Pass 1: restore facings up to Phase 2 target
            for sales, pos, prod in scored:
                if not prod:
                    continue
                pw = prod["width_in"]
                pid = pos["product_id"]
                current_f = pos.get("facings_wide", 1)
                target_f = facings.get(pid, current_f)

                while current_f < target_f and remaining >= pw - 0.5:
                    current_f += 1
                    remaining -= pw
                    changed = True
                    boosted += 1

                pos["facings_wide"] = current_f

            # Pass 2: if still space, boost best sellers beyond Phase 2 (up to max_facings)
            for sales, pos, prod in scored:
                if not prod:
                    continue
                pw = prod["width_in"]
                current_f = pos.get("facings_wide", 1)

                while current_f < max_facings and remaining >= pw - 0.5:
                    current_f += 1
                    remaining -= pw
                    changed = True
                    boosted += 1

                pos["facings_wide"] = current_f

            # Recalculate x_positions if changed
            if changed:
                x = 0.0
                for pos in positions:
                    pos["x_position"] = round(x, 2)
                    prod = products_map.get(pos.get("product_id", ""))
                    if prod:
                        x += prod.get("width_in", 0) * pos.get("facings_wide", 1)

    if boosted > 0:
        print(f"[Boost] Added {boosted} extra facing(s) to underused shelves", flush=True)

    return equipment_dict


# ==============================================================================
# POST-PROCESSING: Fill remaining shelf gaps with best sellers
# ==============================================================================

def fill_shelf_gaps(
    equipment_dict: dict,
    selected_products: List[dict],
    products_map: dict,
    target_pct: float = 99.0,
) -> dict:
    """
    Final gap-filler: for each shelf with remaining space, add facings of
    the highest-selling product that fits (height-compatible).

    A product may gain extra facings on a shelf it's already on, or appear
    as a new entry on a shelf it wasn't assigned to.

    This runs as the last post-processing step to push fill toward 99%.
    """
    total_shelf_width = get_total_shelf_width(equipment_dict)
    target_width = total_shelf_width * (target_pct / 100.0)
    added = 0

    # Sort products by sales DESC — prefer best sellers
    sales_sorted = sorted(
        selected_products,
        key=lambda p: p.get("weekly_units_sold", 0),
        reverse=True,
    )

    max_rounds = 50  # safety cap to prevent infinite loop
    for _ in range(max_rounds):
        # Calculate current total usage
        current_used = 0.0
        for bay in equipment_dict.get("bays", []):
            for shelf in bay.get("shelves", []):
                for pos in shelf.get("positions", []):
                    prod = products_map.get(pos.get("product_id", ""))
                    if prod:
                        current_used += prod.get("width_in", 0) * pos.get("facings_wide", 1)

        if current_used >= target_width:
            break  # Target reached!

        # Find shelf with most remaining space
        best_shelf = None
        best_remaining = 0.0
        best_shelf_h = 0.0
        for bay in equipment_dict.get("bays", []):
            for shelf in bay.get("shelves", []):
                shelf_w = shelf.get("width_in", 48)
                shelf_h = shelf.get("height_in", 12)
                used = 0.0
                for pos in shelf.get("positions", []):
                    prod = products_map.get(pos.get("product_id", ""))
                    if prod:
                        used += prod.get("width_in", 0) * pos.get("facings_wide", 1)
                remaining = shelf_w - used
                if remaining > best_remaining:
                    best_remaining = remaining
                    best_shelf = shelf
                    best_shelf_h = shelf_h

        if best_shelf is None or best_remaining < 2.0:
            break  # No shelf has usable space

        # Find the best product to add to this shelf
        placed = False
        for prod in sales_sorted:
            pw = prod["width_in"]
            ph = prod["height_in"]
            if pw > best_remaining + 0.5:
                continue  # Too wide
            if ph > best_shelf_h:
                continue  # Too tall

            positions = best_shelf.get("positions", [])

            # Check if product is already on this shelf — boost its facings
            existing_pos = None
            for pos in positions:
                if pos.get("product_id") == prod["id"]:
                    existing_pos = pos
                    break

            if existing_pos:
                existing_pos["facings_wide"] = existing_pos.get("facings_wide", 1) + 1
            else:
                # Add as new entry at end
                x_pos = 0.0
                for pos in positions:
                    p_data = products_map.get(pos.get("product_id", ""))
                    if p_data:
                        x_pos += p_data.get("width_in", 0) * pos.get("facings_wide", 1)
                positions.append({
                    "product_id": prod["id"],
                    "x_position": round(x_pos, 2),
                    "facings_wide": 1,
                    "facings_high": 1,
                    "facings_deep": 1,
                    "orientation": "front",
                })
                best_shelf["positions"] = positions

            added += 1
            placed = True
            break

        if not placed:
            break  # No product fits anywhere

        # Recalculate x_positions for the modified shelf
        positions = best_shelf.get("positions", [])
        x = 0.0
        for pos in positions:
            pos["x_position"] = round(x, 2)
            prod = products_map.get(pos.get("product_id", ""))
            if prod:
                x += prod.get("width_in", 0) * pos.get("facings_wide", 1)

    if added > 0:
        print(f"[GapFill] Added {added} facing(s) to fill shelf gaps", flush=True)

    return equipment_dict


# ==============================================================================
# COMBINED: full pipeline (all 3 phases, rule-based fallback)
# ==============================================================================

def fill_equipment_rule_based(
    equipment_dict: dict,
    products_json: list,
    rules: ProductLogicRules,
    decision_tree: Optional[DecisionTree] = None,
) -> dict:
    """
    Full pipeline: capacity check → optimal facings → rule-based placement.
    """
    total_w = get_total_shelf_width(equipment_dict)

    # Phase 1
    selected = phase1_capacity_check(products_json, total_w)

    # Phase 2
    facings = phase2_optimal_facings(selected, total_w, rules)

    # Phase 3
    return phase3_rule_based_placement(
        equipment_dict, selected, facings, rules, decision_tree
    )


# ==============================================================================
# COMBINED: Compute facings + build Gemini prompt (Phase 1+2 → Phase 3 via AI)
# ==============================================================================

def compute_facings_for_ai(
    equipment_dict: dict,
    products_json: list,
    rules: ProductLogicRules,
) -> Tuple[List[dict], Dict[str, int]]:
    """
    Run Phase 1 + Phase 2 to produce the selected product list and facing counts.
    Returns: (selected_products, facings_dict)
    """
    total_w = get_total_shelf_width(equipment_dict)
    selected = phase1_capacity_check(products_json, total_w)
    facings = phase2_optimal_facings(selected, total_w, rules)
    return selected, facings


def build_fill_prompt(
    equipment_json: dict,
    selected_products: list,
    facings: Dict[str, int],
    rules: ProductLogicRules,
    decision_tree: Optional[DecisionTree] = None,
) -> str:
    """
    Build Gemini prompt for Phase 3: place products with pre-calculated facings.

    AI receives:
      - Equipment structure (empty)
      - Product list with EXACT facing counts (non-negotiable)
      - Decision tree instructions for grouping/ordering
      - Shelf tier guidelines
    """
    equip_compact = json.dumps(equipment_json, indent=2)
    rules_text = rules.to_prompt_text()

    # Build product list with facings embedded
    products_with_facings = []
    for p in selected_products:
        pw = copy.copy(p)
        pw["assigned_facings"] = facings.get(p["id"], 1)
        pw["total_width"] = round(p["width_in"] * pw["assigned_facings"], 2)
        products_with_facings.append(pw)

    products_compact = json.dumps(products_with_facings, separators=(",", ":"))

    # Decision tree section
    dt_section = ""
    if decision_tree:
        dt_section = f"""
## {decision_tree.to_prompt_text()}

"""

    return f"""You are a retail planogram expert AI. You are given an EMPTY equipment fixture and a product catalog with PRE-CALCULATED facing counts.

## YOUR TASK
Assign each product to a specific shelf and position. The number of facings is ALREADY DECIDED — you must NOT change them.

## CRITICAL CONSTRAINTS
1. Do NOT change ANY equipment dimensions (width_in, height_in, depth_in, y_position, bay_number, shelf_number).
2. Do NOT add or remove bays or shelves.
3. ONLY populate the "positions" array on each shelf.
4. Each product MUST use EXACTLY the "assigned_facings" value as facings_wide. DO NOT change facing counts.
5. Total width of products on each shelf must NOT exceed the shelf width_in.
   Calculate: sum of (product width_in × facings_wide) for all positions on a shelf ≤ shelf width_in.
6. Product height must not exceed shelf height_in.
7. x_position must be sequential: first product x_position=0, next = prev_x + prev_width*prev_facings, etc.
8. Every product in the list below must be placed on exactly one shelf. Do not skip any product.
9. Use the actual product dimensions — do not invent values.
{dt_section}## {rules_text}

## EMPTY EQUIPMENT (preserve this structure exactly)
{equip_compact}

## PRODUCTS WITH PRE-CALCULATED FACINGS ({len(products_with_facings)} products, {sum(f for f in facings.values())} total facings)
Each product has "assigned_facings" (MUST use as facings_wide) and "total_width" (width × facings).

{products_compact}

## SHELF CAPACITY SUMMARY
{_shelf_capacity_summary(equipment_json)}

## REQUIRED OUTPUT FORMAT
Return a single JSON object with exactly two keys:
{{
  "equipment": <the equipment object with positions filled — same structure, same dimensions>,
  "products": [<ONLY the products placed, copied from catalog (without assigned_facings/total_width fields)>]
}}

Return ONLY valid JSON, no markdown fences, no explanation."""


def _shelf_capacity_summary(equipment_json: dict) -> str:
    """Generate a shelf capacity table to help AI verify fits."""
    lines = []
    for bay in equipment_json.get("bays", []):
        bn = bay.get("bay_number", "?")
        for shelf in bay.get("shelves", []):
            sn = shelf.get("shelf_number", "?")
            w = shelf.get("width_in", 48)
            h = shelf.get("height_in", 12)
            lines.append(f"Bay {bn} / Shelf {sn}: width={w}in, height={h}in")
    return "\n".join(lines)
