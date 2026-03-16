"""
Planogram Generator
===================
Generates planogram layouts from product data and equipment specifications.
Supports both JSON input and simple text-based input.

Placement Strategy:
- Groups products by subcategory for visual merchandising
- Places larger packs on lower shelves, smaller packs on eye-level shelves
- Respects physical constraints (shelf width, height clearance)
"""

import json
import os
from datetime import date
from planogram_schema import (
    Planogram, Equipment, Bay, Shelf, Position, Product
)

try:
    import requests as http_requests
except ImportError:
    http_requests = None


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DEFAULT_EQUIPMENT_FILE = os.path.join(DATA_DIR, "default_equipment.json")
CURRENT_PLANOGRAM_FILE = os.path.join(DATA_DIR, "current_planogram.json")

# Supabase configuration (same as app.py)
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://zcciroutarcpkwpnynyh.supabase.co"
).strip()
SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpjY2lyb3V0YXJjcGt3cG55bnloIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3NzI3MjIzMTAsImV4cCI6MjA4ODI5ODMxMH0."
    "LFnJ8WoxlNhZ06MBQm-1mmJK4mtkBLZAPd4UoPtGrkE"
).strip()


def _supabase_get(table: str, params: dict | None = None) -> list:
    """GET rows from Supabase table via REST API."""
    if not http_requests:
        print(f"[supabase] requests module not available", flush=True)
        return []
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        resp = http_requests.get(url, headers=headers, params=params, timeout=10)
        if resp.ok:
            data = resp.json()
            print(f"[supabase] GET {table}: {len(data)} rows", flush=True)
            return data
        else:
            print(f"[supabase] GET {table} HTTP {resp.status_code}: {resp.text[:200]}", flush=True)
    except Exception as e:
        print(f"[supabase] GET {table} failed: {e}", flush=True)
    return []


def load_default_equipment_config() -> dict:
    """Load default equipment config from Supabase, fallback to local file."""
    # Try Supabase first
    rows = _supabase_get("default_equipment_config", {"is_active": "eq.true", "limit": "1"})
    if rows:
        r = rows[0]
        return {
            "equipment_type": r.get("equipment_type", "gondola"),
            "num_bays": r.get("num_bays", 3),
            "num_shelves": r.get("num_shelves", 5),
            "bay_width": float(r.get("bay_width", 48.0)),
            "bay_height": float(r.get("bay_height", 72.0)),
            "bay_depth": float(r.get("bay_depth", 24.0)),
            "bays_config": r.get("bays_config"),
        }
    # Fallback to local file
    if os.path.exists(DEFAULT_EQUIPMENT_FILE):
        with open(DEFAULT_EQUIPMENT_FILE, 'r') as f:
            return json.load(f)
    # Ultimate fallback
    return {
        "equipment_type": "gondola",
        "num_bays": 3,
        "num_shelves": 5,
        "bay_width": 48.0,
        "bay_height": 72.0,
        "bay_depth": 24.0,
    }


def load_products_from_supabase() -> list:
    """Load beer products from Supabase."""
    rows = _supabase_get("beer_products", {"order": "weekly_units_sold.desc"})
    if not rows:
        return []
    return [Product(**{k: v for k, v in r.items() if k != "created_at"}) for r in rows]


def load_products(filepath: str = None) -> list:
    """Load products from Supabase or JSON file."""
    # Try Supabase first
    products = load_products_from_supabase()
    if products:
        return products
    # Fallback to local file
    if filepath is None:
        filepath = os.path.join(DATA_DIR, "beer_products.json")
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            data = json.load(f)
        return [Product(**p) for p in data]
    return []


def create_default_equipment(
    equipment_id: str = "EQ-001",
    equipment_type: str = "gondola",
    num_bays: int = 3,
    num_shelves: int = 5,
    bay_width: float = 48.0,
    bay_height: float = 72.0,
    bay_depth: float = 24.0,
    shelf_heights: list = None,
    bays_config: list = None,
) -> Equipment:
    """Create equipment with default or specified configuration.

    Args:
        bays_config: Optional per-bay overrides — list of dicts (one per bay) with:
            - width_in (float): Bay width override; falls back to bay_width
            - num_shelves (int): Number of shelves override; falls back to num_shelves
            - shelf_clearances (list[float]): Usable clearance height per shelf slot.
              If omitted, shelves are evenly distributed within the bay height.
        shelf_heights: Legacy parameter — y-positions from floor for ALL bays
          (only used when bays_config is None and shelf_heights is not None).
    """

    def _positions_from_clearances(clearances, b_height, base=6, thickness=1):
        """Convert per-shelf clearance heights → y-positions from floor.

        If the clearances exceed the available bay height, they are scaled
        proportionally so that all requested shelves fit.
        """
        n = len(clearances)
        total_needed = base + sum(float(c) + thickness for c in clearances)
        if total_needed > b_height and n > 0:
            available = b_height - base - n * thickness
            raw_sum = sum(float(c) for c in clearances)
            if raw_sum > 0:
                ratio = available / raw_sum
                clearances = [c * ratio for c in clearances]

        positions = []
        y = float(base)
        for c in clearances:
            if y >= b_height:
                break
            positions.append(round(y, 1))
            y += float(c) + thickness
        return positions

    def _positions_evenly(n, b_height, base=6):
        """Distribute n shelves evenly from base to top."""
        total_usable = b_height - base
        spacing = total_usable / n
        return [round(base + i * spacing, 1) for i in range(n)]

    bays = []
    for b_idx in range(num_bays):
        # Per-bay overrides (if provided)
        bay_cfg = (bays_config[b_idx] if bays_config and b_idx < len(bays_config) else None) or {}

        b_width = float(bay_cfg.get("width_in") or bay_width)
        n_shelves = int(bay_cfg.get("num_shelves") or num_shelves)
        clearances = bay_cfg.get("shelf_clearances") or None  # list[float] or None

        # Compute shelf y-positions
        if clearances and len(clearances) > 0:
            positions = _positions_from_clearances(clearances, bay_height)
        elif shelf_heights is not None and bays_config is None:
            # Legacy: use global shelf_heights y-positions as-is
            positions = shelf_heights
        else:
            positions = _positions_evenly(n_shelves, bay_height)

        shelves = []
        for s_idx, y_pos in enumerate(positions):
            # Clearance height for this shelf slot
            if clearances and s_idx < len(clearances):
                clearance = float(clearances[s_idx])
            elif s_idx < len(positions) - 1:
                clearance = positions[s_idx + 1] - y_pos - 1  # 1 inch shelf thickness
            else:
                clearance = bay_height - y_pos - 1

            shelves.append(Shelf(
                shelf_number=s_idx + 1,
                width_in=b_width,
                height_in=round(max(clearance, 1.0), 1),
                depth_in=bay_depth,
                y_position=round(y_pos, 1),
                positions=[]
            ))

        bays.append(Bay(
            bay_number=b_idx + 1,
            width_in=b_width,
            height_in=bay_height,
            depth_in=bay_depth,
            shelves=shelves,
            glued_right=bool(bay_cfg.get("glued_right", False))
        ))

    return Equipment(
        id=equipment_id,
        name=f"Beer Section {equipment_type.title()}",
        equipment_type=equipment_type,
        bays=bays
    )


def categorize_products(products: list) -> dict:
    """Group products by subcategory for planogram placement."""
    groups = {}
    for p in products:
        key = p.subcategory
        if key not in groups:
            groups[key] = []
        groups[key].append(p)
    return groups


def assign_products_to_shelves(equipment: Equipment, products: list) -> Equipment:
    """
    Intelligent product placement algorithm.
    
    Strategy:
    - Bottom shelves: Large packs (12+, 24-packs) — heavy items low
    - Middle shelves (eye level): Premium/Craft 6-packs — high margin items
    - Upper shelves: Import 6-packs and specialty items
    - Products grouped by subcategory within each shelf
    """

    # Sort products by pack size (large first) then by subcategory
    sorted_products = sorted(products, key=lambda p: (-p.pack_size, p.subcategory, p.brand))

    # Separate into shelf tiers
    large_packs = [p for p in sorted_products if p.pack_size >= 12]
    medium_packs = [p for p in sorted_products if p.pack_size == 6 and p.subcategory.startswith("Domestic")]
    craft_packs = [p for p in sorted_products if p.pack_size <= 6 and "Craft" in p.subcategory]
    import_packs = [p for p in sorted_products if p.pack_size <= 6 and "Import" in p.subcategory]
    other_packs = [p for p in sorted_products if p not in large_packs + medium_packs + craft_packs + import_packs]

    # Build shelf assignment tiers (bottom to top)
    tiers = [
        large_packs,        # Bottom shelf - heavy items
        medium_packs,       # Lower-middle
        craft_packs,        # Eye level - premium
        import_packs,       # Upper-middle
        other_packs         # Top shelf
    ]

    # Place products across bays and shelves
    for bay in equipment.bays:
        num_shelves = len(bay.shelves)
        for shelf_idx, shelf in enumerate(bay.shelves):
            # Map shelf index to tier
            tier_idx = min(shelf_idx, len(tiers) - 1)
            tier_products = tiers[tier_idx]

            if not tier_products:
                continue

            x_pos = 0.0
            while tier_products and x_pos + tier_products[0].width_in <= shelf.width_in:
                product = tier_products[0]

                # Check height constraint
                if product.height_in > shelf.height_in:
                    tier_products.pop(0)
                    continue

                # Determine facings based on remaining space and product importance
                remaining_width = shelf.width_in - x_pos
                max_facings = int(remaining_width / product.width_in)
                
                # More facings for domestic light lager (top sellers)
                if "Light Lager" in product.subcategory and max_facings >= 2:
                    facings = min(2, max_facings)
                else:
                    facings = 1

                shelf.positions.append(Position(
                    product_id=product.id,
                    x_position=round(x_pos, 1),
                    facings_wide=facings,
                    facings_high=1,
                    facings_deep=1,
                    orientation="front"
                ))

                x_pos += product.width_in * facings
                tier_products.pop(0)

    return equipment


def generate_planogram(
    products_file: str = None,
    products: list = None,
    equipment_config: dict = None,
    planogram_name: str = "Beer Category Planogram",
    store_type: str = "Standard Grocery"
) -> Planogram:
    """
    Main entry point: Generate a complete planogram.
    
    Args:
        products_file: Path to products JSON file
        products: List of Product objects (alternative to file)
        equipment_config: Dict with equipment settings (optional)
        planogram_name: Name for the planogram
        store_type: Type of store
    
    Returns:
        Complete Planogram object with products placed on shelves
    """

    # Load products (tries Supabase first, then local file)
    if products is None:
        products = load_products(products_file)
    
    if not products:
        print("[generate_planogram] WARNING: No products loaded, creating empty planogram", flush=True)

    # Create equipment
    if equipment_config:
        equipment = create_default_equipment(**equipment_config)
    else:
        equipment = create_default_equipment(**load_default_equipment_config())

    # Assign products to shelves
    equipment = assign_products_to_shelves(equipment, products)

    # Build planogram
    planogram = Planogram(
        id="PLN-BEER-001",
        name=planogram_name,
        category="Beer",
        store_type=store_type,
        effective_date=date.today().isoformat(),
        equipment=equipment,
        products=products,
        metadata={
            "version": "1.0",
            "generated_by": "Planogram Agent v0.1",
            "placement_strategy": "category_grouped_weight_based"
        }
    )

    return planogram


def generate_summary(planogram: Planogram, full_catalog_size: int = 0) -> dict:
    """Generate a comprehensive summary of the planogram.
    
    full_catalog_size: total SKUs in the master catalog (before capacity filtering).
                       When 0, falls back to len(planogram.products).
    """
    products_map = planogram.products_map
    
    # Collect stats
    total_positions = 0
    total_facings = 0
    total_units = 0
    shelf_fill_rates = []
    revenue_potential = 0
    cost_total = 0
    
    bay_summaries = []
    for bay in planogram.equipment.bays:
        bay_info = {
            "bay_number": bay.bay_number,
            "width": bay.width_in,
            "shelves": []
        }
        for shelf in bay.shelves:
            shelf_products = []
            shelf_facings = 0
            shelf_revenue = 0
            for pos in shelf.positions:
                if getattr(pos, '_phantom', False):
                    continue
                product = products_map.get(pos.product_id)
                if product:
                    units = pos.total_units()
                    shelf_products.append({
                        "name": product.name,
                        "brand": product.brand,
                        "facings": pos.facings_wide,
                        "units": units,
                        "revenue": product.price * pos.facings_wide
                    })
                    shelf_facings += pos.facings_wide
                    total_units += units
                    revenue_potential += product.price * pos.facings_wide
                    cost_total += product.cost * pos.facings_wide
            
            fill = shelf.fill_rate(products_map)
            shelf_fill_rates.append(fill)
            total_positions += len(shelf.positions)
            total_facings += shelf_facings
            
            bay_info["shelves"].append({
                "shelf_number": shelf.shelf_number,
                "y_position": shelf.y_position,
                "clearance": shelf.height_in,
                "fill_rate": round(fill, 1),
                "num_products": len(shelf.positions),
                "products": shelf_products
            })
        bay_summaries.append(bay_info)

    # Category breakdown (skip phantoms to avoid double-counting cross-bay products)
    category_breakdown = {}
    for bay in planogram.equipment.bays:
        for shelf in bay.shelves:
            for pos in shelf.positions:
                if getattr(pos, '_phantom', False):
                    continue
                product = products_map.get(pos.product_id)
                if product:
                    cat = product.subcategory
                    if cat not in category_breakdown:
                        category_breakdown[cat] = {"count": 0, "facings": 0, "revenue": 0}
                    category_breakdown[cat]["count"] += 1
                    category_breakdown[cat]["facings"] += pos.facings_wide
                    category_breakdown[cat]["revenue"] += product.price * pos.facings_wide

    # Brand breakdown (skip phantoms to avoid double-counting cross-bay products)
    brand_breakdown = {}
    for bay in planogram.equipment.bays:
        for shelf in bay.shelves:
            for pos in shelf.positions:
                if getattr(pos, '_phantom', False):
                    continue
                product = products_map.get(pos.product_id)
                if product:
                    brand = product.brand
                    if brand not in brand_breakdown:
                        brand_breakdown[brand] = {"count": 0, "facings": 0}
                    brand_breakdown[brand]["count"] += 1
                    brand_breakdown[brand]["facings"] += pos.facings_wide

    avg_fill = sum(shelf_fill_rates) / len(shelf_fill_rates) if shelf_fill_rates else 0

    # Per-SKU space analysis: aggregate revenue and space per unique product
    # Skip phantoms to avoid double-counting cross-bay products
    sku_space = {}  # product_id -> {name, brand, subcategory, revenue, space_in, facings}
    placed_ids = set()
    for bay in planogram.equipment.bays:
        for shelf in bay.shelves:
            for pos in shelf.positions:
                if getattr(pos, '_phantom', False):
                    continue
                product = products_map.get(pos.product_id)
                if product:
                    placed_ids.add(pos.product_id)
                    if pos.product_id not in sku_space:
                        sku_space[pos.product_id] = {
                            "product_id": pos.product_id,
                            "name": product.name,
                            "brand": product.brand,
                            "subcategory": product.subcategory,
                            "price": product.price,
                            "revenue": 0,
                            "space_in": 0,
                            "facings": 0,
                        }
                    sku_space[pos.product_id]["revenue"] += product.price * pos.facings_wide
                    sku_space[pos.product_id]["space_in"] += product.width_in * pos.facings_wide
                    sku_space[pos.product_id]["facings"] += pos.facings_wide

    # Calculate $/space and sort descending
    sku_space_list = []
    for sid, info in sku_space.items():
        rev_per_space = round(info["revenue"] / info["space_in"], 2) if info["space_in"] > 0 else 0
        sku_space_list.append({**info, "revenue_per_space": rev_per_space})
    sku_space_list.sort(key=lambda x: x["revenue_per_space"], reverse=True)

    # Total space used (inches) across all shelves
    total_space_used_in = sum(info["space_in"] for info in sku_space.values())
    # Total available space (inches)
    total_space_available_in = sum(
        shelf.width_in
        for bay in planogram.equipment.bays
        for shelf in bay.shelves
    )
    avg_revenue_per_space = round(revenue_potential / total_space_used_in, 2) if total_space_used_in > 0 else 0

    # Assortment analysis — use full catalog size when available
    catalog_ids = set(p.id for p in planogram.products)
    total_catalog = full_catalog_size if full_catalog_size > 0 else len(catalog_ids)
    unplaced_products = []
    for p in planogram.products:
        if p.id not in placed_ids:
            unplaced_products.append({
                "product_id": p.id,
                "name": p.name,
                "brand": p.brand,
                "subcategory": p.subcategory,
            })
    assortment_pct = round(len(placed_ids) / total_catalog * 100, 1) if total_catalog > 0 else 0

    return {
        "planogram_name": planogram.name,
        "category": planogram.category,
        "store_type": planogram.store_type,
        "date": planogram.effective_date,
        "equipment": {
            "type": planogram.equipment.equipment_type,
            "total_bays": len(planogram.equipment.bays),
            "total_shelves": planogram.equipment.total_shelves,
            "total_width_in": planogram.equipment.total_width,
            "total_width_ft": round(planogram.equipment.total_width / 12, 1)
        },
        "products": {
            "total_in_catalog": planogram.total_products(),
            "total_placed": total_positions,
            "total_facings": total_facings,
            "total_units_capacity": total_units,
            "unplaced_count": planogram.total_products() - total_positions
        },
        "financials": {
            "total_revenue_potential": round(revenue_potential, 2),
            "total_cost": round(cost_total, 2),
            "total_margin": round(revenue_potential - cost_total, 2),
            "margin_pct": round(((revenue_potential - cost_total) / revenue_potential) * 100, 1) if revenue_potential > 0 else 0
        },
        "space_utilization": {
            "avg_shelf_fill_rate": round(avg_fill, 1),
            "shelf_fill_rates": [round(f, 1) for f in shelf_fill_rates],
            "total_space_used_in": round(total_space_used_in, 1),
            "total_space_available_in": round(total_space_available_in, 1),
        },
        "assortment": {
            "total_catalog": total_catalog,
            "total_placed": len(placed_ids),
            "assortment_pct": assortment_pct,
            "placed_ids": list(placed_ids),
            "unplaced": unplaced_products,
        },
        "sku_space_analysis": sku_space_list,
        "avg_revenue_per_space": avg_revenue_per_space,
        "category_breakdown": category_breakdown,
        "brand_breakdown": brand_breakdown,
        "bay_details": bay_summaries
    }


def process_user_input(user_input: str) -> dict:
    """
    Parse simple natural language input to extract planogram parameters.
    
    Examples:
        "Create a beer planogram with 3 bays, 5 shelves, gondola type"
        "4 bay cooler with 4 shelves each 48 inches wide"
    """
    input_lower = user_input.lower()
    
    config = {
        "equipment_type": "gondola",
        "num_bays": 3,
        "num_shelves": 5,
        "bay_width": 48.0,
        "bay_height": 72.0,
    }

    # Extract equipment type
    for eq_type in ["cooler", "endcap", "wall_section", "gondola", "island"]:
        if eq_type in input_lower:
            config["equipment_type"] = eq_type
            break

    # Extract numbers
    import re
    bay_match = re.search(r'(\d+)\s*bay', input_lower)
    if bay_match:
        config["num_bays"] = int(bay_match.group(1))

    shelf_match = re.search(r'(\d+)\s*shel', input_lower)
    if shelf_match:
        config["num_shelves"] = int(shelf_match.group(1))

    width_match = re.search(r'(\d+)\s*(?:inch|in|")\s*wide', input_lower)
    if width_match:
        config["bay_width"] = float(width_match.group(1))

    height_match = re.search(r'(\d+)\s*(?:inch|in|")\s*(?:tall|high|height)', input_lower)
    if height_match:
        config["bay_height"] = float(height_match.group(1))

    return config


if __name__ == "__main__":
    # Generate sample planogram
    planogram = generate_planogram()

    # Save planogram JSON
    output_path = os.path.join(os.path.dirname(__file__), "data", "sample_planogram.json")
    with open(output_path, 'w') as f:
        f.write(planogram.to_json())
    print(f"Planogram saved to {output_path}")

    # Generate and save summary
    summary = generate_summary(planogram)
    summary_path = os.path.join(os.path.dirname(__file__), "data", "planogram_summary.json")
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"Summary saved to {summary_path}")

    # Print summary
    print(f"\n{'='*60}")
    print(f"PLANOGRAM SUMMARY: {summary['planogram_name']}")
    print(f"{'='*60}")
    print(f"Equipment: {summary['equipment']['type']} — {summary['equipment']['total_bays']} bays, "
          f"{summary['equipment']['total_shelves']} shelves")
    print(f"Total Width: {summary['equipment']['total_width_ft']} ft")
    print(f"Products: {summary['products']['total_placed']} placed / "
          f"{summary['products']['total_in_catalog']} in catalog")
    print(f"Total Facings: {summary['products']['total_facings']}")
    print(f"Avg Fill Rate: {summary['space_utilization']['avg_shelf_fill_rate']}%")
    print(f"Revenue Potential: ${summary['financials']['total_revenue_potential']:,.2f}")
    print(f"Margin: ${summary['financials']['total_margin']:,.2f} ({summary['financials']['margin_pct']}%)")
    print(f"\nCategory Breakdown:")
    for cat, info in sorted(summary['category_breakdown'].items()):
        print(f"  {cat}: {info['facings']} facings, ${info['revenue']:,.2f} revenue")
