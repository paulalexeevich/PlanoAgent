"""
Decision Tree — Shopper Navigation Logic for Planograms
========================================================
Defines pre-built category decision trees that control how products
are grouped on shelves so shoppers can navigate intuitively.

A decision tree is an ordered list of levels.  Each level specifies
a product attribute (or derived group) that products are grouped by.
Products within the same group at every level should be placed
adjacently on the planogram.

Example for Beer:
  Level 1  Segment     → Domestic | Craft | Import | Specialty
  Level 2  Subcategory → Light Lager | IPA | Pale Ale | …
  Level 3  Package     → can | bottle | tallboy_can
  Level 4  Brand       → Bud Light | Sierra Nevada | …

After generation, `validate_compliance()` scores how well the
planogram respects the tree (0–100 %).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class DecisionTreeLevel:
    """One level of the decision tree."""
    name: str                          # Human label, e.g. "Segment"
    attribute: str                     # Product field, e.g. "subcategory"
    derive_fn_name: Optional[str] = None  # Name of a registered derivation
    # (We store a *name* rather than a lambda so the object is JSON-safe.)

    def to_dict(self) -> dict:
        return {"name": self.name, "attribute": self.attribute,
                "derive_fn_name": self.derive_fn_name}


@dataclass
class DecisionTree:
    """Ordered list of grouping levels for a product category."""
    category: str                      # e.g. "Beer"
    name: str                          # e.g. "Beer Standard"
    description: str
    levels: List[DecisionTreeLevel] = field(default_factory=list)

    # ── serialization ─────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "name": self.name,
            "description": self.description,
            "levels": [l.to_dict() for l in self.levels],
        }

    def level_names(self) -> List[str]:
        return [l.name for l in self.levels]

    # ── prompt text ───────────────────────────────────────────────────
    def to_prompt_text(self) -> str:
        """Render the tree as merchandising instructions for an AI prompt."""
        lines = [
            "DECISION TREE (shopper navigation logic — follow strictly):",
            f"Category: {self.category}",
            f"Tree: {self.name}",
            "",
            "Products must be grouped in this EXACT priority order.",
            "Adjacent products on the same shelf (and across consecutive shelves)",
            "must share the same group value at every level before differing.",
            "Think of it as a nested sort: Level 1 is the coarsest grouping,",
            "Level N is the finest.",
            "",
        ]
        for i, level in enumerate(self.levels, 1):
            groups = _example_groups(level)
            groups_str = f" (e.g. {', '.join(groups)})" if groups else ""
            lines.append(f"  Level {i} — {level.name} "
                         f"(attribute: {level.attribute}){groups_str}")
        lines.append("")
        lines.append(
            "Within each bay, products should flow left→right following "
            "this grouping.  When a shelf fills, continue the same group "
            "on the next shelf up.  Switch to the next group only when "
            "the current group is fully placed."
        )
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# Derivation functions  (registered by name so they are JSON-safe)
# ═══════════════════════════════════════════════════════════════════════

def _derive_beer_segment(product: dict) -> str:
    """Derive high-level segment from subcategory for Beer."""
    subcat = product.get("subcategory", "")
    if subcat.startswith("Domestic"):
        return "Domestic"
    if subcat.startswith("Craft"):
        return "Craft"
    if subcat.startswith("Import"):
        return "Import"
    if "Cider" in subcat or "Specialty" in subcat:
        return "Specialty"
    return "Other"


def _derive_pack_tier(product: dict) -> str:
    """Derive pack-size tier: Singles, 6-Pack, 12-Pack, Multi-Pack."""
    ps = product.get("pack_size", 1)
    if ps <= 1:
        return "Singles"
    if ps <= 6:
        return "6-Pack"
    if ps <= 12:
        return "12-Pack"
    return "Multi-Pack"


_DERIVE_REGISTRY: Dict[str, Callable[[dict], str]] = {
    "beer_segment": _derive_beer_segment,
    "pack_tier": _derive_pack_tier,
}


def get_group_value(product: dict, level: DecisionTreeLevel) -> str:
    """Return the group value for a product at a given tree level."""
    if level.derive_fn_name and level.derive_fn_name in _DERIVE_REGISTRY:
        return _DERIVE_REGISTRY[level.derive_fn_name](product)
    return str(product.get(level.attribute, ""))


def get_product_group_tuple(product: dict, tree: DecisionTree) -> Tuple[str, ...]:
    """Return the full group tuple for a product across all tree levels."""
    return tuple(get_group_value(product, lvl) for lvl in tree.levels)


# ═══════════════════════════════════════════════════════════════════════
# Pre-built trees
# ═══════════════════════════════════════════════════════════════════════

BEER_DECISION_TREE = DecisionTree(
    category="Beer",
    name="Beer Standard",
    description=(
        "Shoppers navigate: Segment (Domestic/Craft/Import) → "
        "Style (Light Lager, IPA, …) → Package (can/bottle) → Brand"
    ),
    levels=[
        DecisionTreeLevel(
            name="Segment",
            attribute="subcategory",       # used as fallback
            derive_fn_name="beer_segment", # Domestic / Craft / Import / Specialty
        ),
        DecisionTreeLevel(
            name="Style",
            attribute="subcategory",       # direct field
        ),
        DecisionTreeLevel(
            name="Package",
            attribute="package_type",
        ),
        DecisionTreeLevel(
            name="Brand",
            attribute="brand",
        ),
    ],
)

# Registry of all pre-built trees, keyed by category name
CATEGORY_TREES: Dict[str, DecisionTree] = {
    "Beer": BEER_DECISION_TREE,
}


def get_tree_for_category(category: str) -> Optional[DecisionTree]:
    """Return the pre-built decision tree for a category, or None."""
    return CATEGORY_TREES.get(category)


# ═══════════════════════════════════════════════════════════════════════
# Compliance validation
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class LevelCompliance:
    """Compliance result for one tree level."""
    level_name: str
    total_transitions: int      # how many times the group changed
    clean_transitions: int      # transitions that never "go back" to an earlier group
    break_count: int            # times a group reappeared after being interrupted
    unique_groups: int
    compliance_pct: float       # 0-100
    groups_in_order: List[str]  # the groups as encountered left→right

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ComplianceReport:
    """Full compliance report for a planogram vs. a decision tree."""
    tree_name: str
    overall_pct: float
    levels: List[LevelCompliance]
    # Ordered list of (bay, shelf, x, product_id, group_tuple) for visual overlay
    position_groups: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tree_name": self.tree_name,
            "overall_pct": self.overall_pct,
            "levels": [l.to_dict() for l in self.levels],
            "position_groups": self.position_groups,
        }


def validate_compliance(
    planogram_data: dict,
    tree: DecisionTree,
) -> ComplianceReport:
    """
    Walk through every position in the planogram (bay-by-bay,
    shelf bottom→top, left→right) and score how well the product
    sequence respects each level of the decision tree.

    A "break" at a level means a group appeared, was interrupted by
    a different group, and then appeared again later in the sequence.
    Fewer breaks = higher compliance.
    """
    # Build products map
    products_map: Dict[str, dict] = {
        p["id"]: p for p in planogram_data.get("products", [])
    }

    # Collect ordered sequence of positions
    ordered_positions: List[dict] = []
    equipment = planogram_data.get("equipment", {})
    for bay in sorted(equipment.get("bays", []), key=lambda b: b.get("bay_number", 0)):
        for shelf in sorted(bay.get("shelves", []), key=lambda s: s.get("shelf_number", 0)):
            for pos in sorted(shelf.get("positions", []), key=lambda p: p.get("x_position", 0)):
                pid = pos.get("product_id", "")
                product = products_map.get(pid)
                if not product:
                    continue
                group_tuple = get_product_group_tuple(product, tree)
                ordered_positions.append({
                    "bay": bay.get("bay_number", 0),
                    "shelf": shelf.get("shelf_number", 0),
                    "x": pos.get("x_position", 0),
                    "product_id": pid,
                    "groups": {lvl.name: group_tuple[i]
                               for i, lvl in enumerate(tree.levels)},
                })

    if not ordered_positions:
        return ComplianceReport(
            tree_name=tree.name,
            overall_pct=0,
            levels=[],
            position_groups=ordered_positions,
        )

    # Score each level HIERARCHICALLY:
    # Level N is evaluated only within the contiguous runs of Level N-1.
    # This correctly measures "within each Style group, are Packages contiguous?"
    # instead of "are ALL cans before ALL bottles globally".
    level_results: List[LevelCompliance] = []

    for lvl_idx, level in enumerate(tree.levels):

        if lvl_idx == 0:
            # Top level: evaluate across all positions (no parent context)
            partitions = [ordered_positions]
        else:
            # Partition positions by contiguous runs of the parent level
            parent_level = tree.levels[lvl_idx - 1]
            partitions = []
            current_run: List[dict] = [ordered_positions[0]]
            for pos in ordered_positions[1:]:
                if pos["groups"][parent_level.name] == current_run[-1]["groups"][parent_level.name]:
                    current_run.append(pos)
                else:
                    partitions.append(current_run)
                    current_run = [pos]
            partitions.append(current_run)

        # Aggregate breaks and transitions across all partitions
        total_breaks = 0
        total_transitions = 0
        all_seen: List[str] = []

        for partition in partitions:
            if len(partition) < 2:
                val = partition[0]["groups"][level.name]
                if val not in all_seen:
                    all_seen.append(val)
                continue

            seq = [p["groups"][level.name] for p in partition]
            seen: set = set()
            finished: set = set()
            current = seq[0]
            seen.add(current)
            if current not in all_seen:
                all_seen.append(current)

            for val in seq[1:]:
                if val != current:
                    total_transitions += 1
                    if val in finished:
                        total_breaks += 1
                    finished.add(current)
                    current = val
                    seen.add(current)
                    if val not in all_seen:
                        all_seen.append(val)

        unique = len(all_seen)
        if total_transitions == 0:
            pct = 100.0
        else:
            pct = max(0, (1 - total_breaks / max(total_transitions, 1)) * 100)

        level_results.append(LevelCompliance(
            level_name=level.name,
            total_transitions=total_transitions,
            clean_transitions=total_transitions - total_breaks,
            break_count=total_breaks,
            unique_groups=unique,
            compliance_pct=round(pct, 1),
            groups_in_order=all_seen,
        ))

    # Overall = weighted average (higher levels matter more)
    if level_results:
        weights = list(range(len(level_results), 0, -1))  # L1 highest weight
        total_w = sum(weights)
        overall = sum(lr.compliance_pct * w
                      for lr, w in zip(level_results, weights)) / total_w
    else:
        overall = 0

    return ComplianceReport(
        tree_name=tree.name,
        overall_pct=round(overall, 1),
        levels=level_results,
        position_groups=ordered_positions,
    )


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _example_groups(level: DecisionTreeLevel) -> List[str]:
    """Return example group values for prompt illustration."""
    if level.derive_fn_name == "beer_segment":
        return ["Domestic", "Craft", "Import", "Specialty"]
    if level.derive_fn_name == "pack_tier":
        return ["Singles", "6-Pack", "12-Pack", "Multi-Pack"]
    if level.attribute == "package_type":
        return ["can", "bottle", "tallboy_can"]
    if level.attribute == "subcategory":
        return ["Domestic Light Lager", "Craft IPA", "Import Lager", "..."]
    return []


def sort_products_by_tree(products: list, tree: DecisionTree) -> list:
    """Sort a product list according to the decision tree grouping order."""
    return sorted(products, key=lambda p: get_product_group_tuple(p, tree))
