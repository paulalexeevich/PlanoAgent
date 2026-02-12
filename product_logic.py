"""
Product Logic — Rules & Algorithms for Filling Equipment
=========================================================
Defines configurable rules for product placement and provides:
  1. A deterministic rule-based fill algorithm (fallback)
  2. A prompt builder for Gemini AI-based filling

The rules control which products go on which shelf tiers,
facing allocations, grouping strategy, and target fill rate.
"""

import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional

from planogram_schema import Equipment, Bay, Shelf, Position, Product
from decision_tree import (
    DecisionTree, get_product_group_tuple, sort_products_by_tree,
    get_tree_for_category,
)


# ── Default rule values ──────────────────────────────────────────────────────

DEFAULT_BOTTOM_SHELF = {
    "min_pack_size": 12,
    "subcategories": [],                     # empty = any subcategory
    "description": "Large/heavy packs (12+, 15, 24-packs)",
}

DEFAULT_EYE_LEVEL = {
    "min_pack_size": 0,
    "max_pack_size": 6,
    "subcategories": [
        "Craft IPA", "Craft Pale Ale", "Craft Amber Ale",
        "Craft Session IPA", "Craft Wheat Beer", "Craft Lager",
    ],
    "description": "Craft & premium 6-packs — highest margin at eye level",
}

DEFAULT_TOP_SHELF = {
    "min_pack_size": 0,
    "max_pack_size": 6,
    "subcategories": [
        "Import Lager", "Import Dark Lager", "Import Stout",
        "Hard Cider",
    ],
    "description": "Import 6-packs, specialty & cider",
}

DEFAULT_TOP_SELLER_BRANDS = [
    "Bud Light", "Coors Light", "Miller Lite", "Michelob Ultra",
]


# ── ProductLogicRules ────────────────────────────────────────────────────────

@dataclass
class ProductLogicRules:
    """Configurable rule-set that governs how products fill equipment."""

    fill_target_pct: float = 85.0
    max_facings: int = 3
    group_by: str = "subcategory"              # "subcategory" | "brand"

    # Shelf-tier assignments (bottom → top)
    bottom_shelf_min_pack: int = 12
    bottom_shelf_subcategories: List[str] = field(default_factory=list)

    eye_level_subcategories: List[str] = field(default_factory=lambda: list(
        DEFAULT_EYE_LEVEL["subcategories"]
    ))

    top_shelf_subcategories: List[str] = field(default_factory=lambda: list(
        DEFAULT_TOP_SHELF["subcategories"]
    ))

    top_seller_brands: List[str] = field(default_factory=lambda: list(
        DEFAULT_TOP_SELLER_BRANDS
    ))
    top_seller_extra_facings: int = 2          # facings for top-seller brands

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
            f"TOP-SELLER BRANDS (give {self.top_seller_extra_facings} facings): "
            + ", ".join(self.top_seller_brands) + ".",
            "",
            "GENERAL MERCHANDISING:",
            "- Place heavier/larger items on lower shelves.",
            "- Premium & high-margin items at eye level (shelves 3–4 of 5).",
            "- Ensure brand variety across equipment — avoid all one brand.",
        ]
        return "\n".join(lines)


# ── Rule-based fill algorithm (deterministic fallback) ───────────────────────

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
    # Divide shelves into zones
    bottom_end = max(1, total_shelves // 4)
    top_start = total_shelves - max(1, total_shelves // 4)
    if shelf_idx < bottom_end:
        return "bottom"
    if shelf_idx >= top_start:
        return "top"
    # middle zone — upper half is "eye", lower half is "middle"
    mid = (bottom_end + top_start) // 2
    return "eye" if shelf_idx >= mid else "middle"


def fill_equipment_rule_based(
    equipment_dict: dict,
    products_json: list,
    rules: ProductLogicRules,
    decision_tree: Optional[DecisionTree] = None,
) -> dict:
    """
    Deterministic algorithm: fill empty equipment with products.

    Args:
        equipment_dict:  equipment JSON (bays → shelves with empty positions)
        products_json:   full product catalog (list of dicts)
        rules:           ProductLogicRules instance
        decision_tree:   optional DecisionTree — if provided, products within
                         each tier are sorted by the tree's grouping order

    Returns:
        dict with keys:
          "equipment" — the filled equipment dict (original structure preserved)
          "products"  — list of product dicts actually placed
    """
    # Classify products into tiers
    tier_buckets: dict[str, list] = {"bottom": [], "middle": [], "eye": [], "top": []}
    for p in products_json:
        tier = _classify_product(p, rules)
        tier_buckets[tier].append(p)

    # Sort within each tier using the decision tree (if provided) for grouping
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
            target_w = shelf_w * (rules.fill_target_pct / 100.0)
            tier_label = _shelf_tier_for_index(s_idx, total_shelves)

            # Primary bucket for this tier, fallback to 'middle', then others
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
                while i < len(bucket) and x_pos < target_w:
                    prod = bucket[i]

                    # Height check
                    if prod["height_in"] > shelf_h:
                        i += 1
                        continue

                    # Determine facings
                    pw = prod["width_in"]
                    is_top_seller = prod["brand"] in rules.top_seller_brands
                    desired = rules.top_seller_extra_facings if is_top_seller else 1
                    max_fit = int((shelf_w - x_pos) / pw) if pw > 0 else 0
                    facings = min(desired, max_fit, rules.max_facings)
                    if facings < 1:
                        i += 1
                        continue

                    positions.append({
                        "product_id": prod["id"],
                        "x_position": round(x_pos, 2),
                        "facings_wide": facings,
                        "facings_high": 1,
                        "facings_deep": 1,
                        "orientation": "front",
                    })
                    x_pos += pw * facings
                    placed_product_ids.add(prod["id"])
                    bucket.pop(i)  # remove so it isn't reused
                    # don't increment i — next element shifted into place

            shelf["positions"] = positions

    # Collect only placed products
    placed_products = [p for p in products_json if p["id"] in placed_product_ids]

    return {
        "equipment": equipment_dict,
        "products": placed_products,
    }


# ── Gemini prompt builder ────────────────────────────────────────────────────

def build_fill_prompt(
    equipment_json: dict,
    products_json: list,
    rules: ProductLogicRules,
    decision_tree: Optional[DecisionTree] = None,
) -> str:
    """
    Build a Gemini prompt for Step 2: fill an existing equipment with products.

    The prompt tells Gemini to keep equipment dimensions/structure unchanged
    and only populate the `positions` arrays on each shelf.
    If a decision_tree is provided, its grouping instructions are included.
    """
    equip_compact = json.dumps(equipment_json, indent=2)
    products_compact = json.dumps(products_json, separators=(",", ":"))
    rules_text = rules.to_prompt_text()

    # Decision tree section
    dt_section = ""
    if decision_tree:
        dt_section = f"""
## {decision_tree.to_prompt_text()}

"""

    return f"""You are a retail planogram expert AI. You are given an EMPTY equipment fixture and a product catalog.
Your task is to FILL the shelves with products by populating the "positions" arrays.

## CRITICAL CONSTRAINTS
1. Do NOT change ANY equipment dimensions (width_in, height_in, depth_in, y_position, bay_number, shelf_number).
2. Do NOT add or remove bays or shelves.
3. ONLY populate the "positions" array on each shelf.
4. Every product_id in positions MUST exist in the products array you return.
5. The products array must contain ONLY products that appear in at least one position.
6. Products must physically fit: total width of positions on a shelf must not exceed shelf width_in.
7. Product height must not exceed shelf clearance (height_in).
8. x_position = previous product's x_position + (previous product's width_in * facings_wide). First product starts at 0.
9. Use the actual product dimensions from the catalog — do not invent dimensions.
{dt_section}## {rules_text}

## EMPTY EQUIPMENT (preserve this structure exactly)
{equip_compact}

## AVAILABLE PRODUCT CATALOG ({len(products_json)} products)
Each product has: id, name, brand, subcategory, beer_type, package_type, pack_size, unit_size_oz, width_in, height_in, depth_in, price, cost, abv, color_hex.

{products_compact}

## REQUIRED OUTPUT FORMAT
Return a single JSON object with exactly two keys:
{{
  "equipment": <the equipment object above with positions filled in — same structure, same dimensions>,
  "products": [<ONLY the products that are placed on at least one shelf, copied from the catalog>]
}}

Return ONLY valid JSON, no markdown fences, no explanation."""
