"""
Planogram Agent — Web Application
==================================
Flask-based web app that serves the planogram visualizer.
Provides API endpoints for generating and viewing planograms.
Supports both rule-based and Gemini AI-powered generation.
"""

from flask import Flask, render_template, jsonify, request
import json
import os
import traceback
import csv
import hashlib
import requests as http_requests
from collections import defaultdict

from dotenv import load_dotenv
load_dotenv()

from planogram_generator import (
    generate_planogram, generate_summary, process_user_input,
    load_products, create_default_equipment,
    load_default_equipment_config, CURRENT_PLANOGRAM_FILE,
)
from planogram_schema import Planogram, Equipment
from gemini_agent import generate_planogram_with_ai, fill_products_with_ai
from product_logic import (
    ProductLogicRules, fill_equipment_rule_based, fill_equipment_cross_bay,
    build_fill_prompt,
    compute_facings_for_ai, get_total_shelf_width, phase1_capacity_check,
    phase2_optimal_facings, validate_and_fix_shelves,
    recover_missing_products, boost_underused_shelves, fill_shelf_gaps,
)
from decision_tree import (
    get_tree_for_category, validate_compliance, BEER_DECISION_TREE
)

app = Flask(__name__, template_folder="templates", static_folder="static")

# Store the current state in memory
current_planogram = None
current_summary = None
current_equipment = None      # Empty equipment dict (Step 1 result)
current_rules = None          # ProductLogicRules (for Step 2)
current_compliance = None     # Compliance report (for DT tracking)
current_decision_tree = None  # Decision tree definition


def _save_state():
    """Persist current planogram + summary + decision tree + compliance to disk."""
    if current_planogram is None:
        return
    payload = {
        "planogram": current_planogram.to_dict(),
        "summary": current_summary,
        "decision_tree": current_decision_tree.to_dict() if current_decision_tree else None,
        "compliance": current_compliance.to_dict() if current_compliance else None,
    }
    try:
        with open(CURRENT_PLANOGRAM_FILE, 'w') as f:
            json.dump(payload, f, indent=2, default=str)
    except Exception as e:
        print(f"[save] Failed to write {CURRENT_PLANOGRAM_FILE}: {e}", flush=True)


def _load_saved_state() -> bool:
    """Try to load state from data/current_planogram.json. Returns True on success."""
    global current_planogram, current_summary, current_equipment
    global current_compliance, current_decision_tree

    if not os.path.exists(CURRENT_PLANOGRAM_FILE):
        return False

    try:
        with open(CURRENT_PLANOGRAM_FILE, 'r') as f:
            payload = json.load(f)

        current_planogram = Planogram.from_dict(payload["planogram"])
        current_summary = generate_summary(current_planogram, _full_catalog_size())

        from dataclasses import asdict
        current_equipment = asdict(current_planogram.equipment)

        decision_tree = get_tree_for_category("Beer")
        current_decision_tree = decision_tree
        if decision_tree and current_planogram.products:
            current_compliance = validate_compliance(
                current_planogram.to_dict(), decision_tree
            )
        print(f"[init] Loaded saved state from {CURRENT_PLANOGRAM_FILE}", flush=True)
        return True
    except Exception as e:
        print(f"[init] Could not load saved state: {e}", flush=True)
        return False


def init_default_planogram():
    """Initialize with default beer planogram (from file defaults)."""
    global current_planogram, current_summary, current_equipment, current_compliance, current_decision_tree
    current_planogram = generate_planogram()
    current_summary = generate_summary(current_planogram, _full_catalog_size())
    from dataclasses import asdict
    current_equipment = asdict(current_planogram.equipment)
    decision_tree = get_tree_for_category("Beer")
    current_decision_tree = decision_tree
    if decision_tree and current_planogram.products:
        compliance = validate_compliance(current_planogram.to_dict(), decision_tree)
        current_compliance = compliance
    _save_state()


def _load_products_json() -> list:
    """Load raw product dicts from JSON file."""
    products_file = os.path.join(os.path.dirname(__file__), "data", "beer_products.json")
    with open(products_file, 'r') as f:
        return json.load(f)


def _full_catalog_size() -> int:
    """Return total number of SKUs in the active catalog.
    Uses the current planogram's own product list when it's not the beer default."""
    if current_planogram and current_planogram.category != "Beer":
        return len(current_planogram.products)
    return len(_load_products_json())


def _stable_color_from_text(text: str) -> str:
    """Generate deterministic pastel-ish hex color for a product name/id."""
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()
    r = int(digest[0:2], 16)
    g = int(digest[2:4], 16)
    b = int(digest[4:6], 16)
    # Keep colors readable on dark labels
    r = (r // 2) + 64
    g = (g // 2) + 64
    b = (b // 2) + 64
    return f"#{r:02X}{g:02X}{b:02X}"


def _load_product_sizes() -> dict:
    """Load real product dimensions (cm) from product_code_external_id_map.csv.
    Returns dict keyed by external_id → {width_cm, height_cm, name, tiny_name}."""
    size_csv = os.path.join(os.path.dirname(__file__), "Demo data", "product_code_external_id_map.csv")
    size_map = {}
    if not os.path.exists(size_csv):
        return size_map
    with open(size_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            eid = (row.get("external_id") or "").strip()
            if not eid:
                continue
            try:
                w = float(row.get("width") or 0)
                h = float(row.get("height") or 0)
            except ValueError:
                continue
            size_map[eid] = {
                "width_cm": w,
                "height_cm": h,
                "name": (row.get("name") or "").strip(),
                "tiny_name": (row.get("tiny_name") or "").strip(),
            }
    return size_map


def _build_image_map() -> dict:
    """Build external_product_id → miniature_url mapping.

    Chain: external_id → tiny_name (product_code_external_id_map.csv)
           tiny_name   → miniature_url (coffee_1/2/3_assortment.json)
    Returns dict keyed by external_id → image URL string.
    """
    demo_dir = os.path.join(os.path.dirname(__file__), "Demo data")

    # Step 1: tiny_name → miniature_url from all three assortment files
    tiny_to_url: dict = {}
    for i in (1, 2, 3):
        assortment_path = os.path.join(demo_dir, f"coffee_{i}_assortment.json")
        if not os.path.exists(assortment_path):
            continue
        with open(assortment_path, "r", encoding="utf-8") as f:
            items = json.load(f)
        for item in items:
            prod = item.get("product", {})
            tn = (prod.get("tiny_name") or "").strip()
            url = (prod.get("miniature_url") or "").strip()
            if tn and url and tn not in tiny_to_url:
                tiny_to_url[tn] = url

    # Step 2: external_id → tiny_name from CSV
    size_csv = os.path.join(demo_dir, "product_code_external_id_map.csv")
    ext_to_url: dict = {}
    if not os.path.exists(size_csv):
        return ext_to_url
    with open(size_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            eid = (row.get("external_id") or "").strip()
            tn = (row.get("tiny_name") or "").strip()
            if eid and tn and tn in tiny_to_url:
                ext_to_url[eid] = tiny_to_url[tn]

    return ext_to_url


CM_TO_IN = 1.0 / 2.54


def _build_planogram_from_demo_csv(csv_path: str) -> Planogram:
    """
    Build a planogram from demo CSV.

    Mapping:
      eq_num_in_scene_group -> bay_number
      shelf_number          -> shelf_number  (1 = top, max = bottom)
      on_shelf_position     -> left-to-right order on shelf

    Real product dimensions loaded from product_code_external_id_map.csv (cm → in).
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    size_map = _load_product_sizes()
    image_map = _build_image_map()

    rows = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("external_product_id"):
                continue
            try:
                bay_num = int(row.get("eq_num_in_scene_group") or 0)
                shelf_num = int(row.get("shelf_number") or 0)
                pos_num = int(row.get("on_shelf_position") or 0)
            except ValueError:
                continue
            if bay_num <= 0 or shelf_num <= 0 or pos_num <= 0:
                continue
            rows.append(row)

    if not rows:
        raise ValueError("CSV has no usable rows")

    # Build product catalog with real sizes
    products = []
    seen_ids = set()
    prod_width_in = {}
    for row in rows:
        eid = row["external_product_id"]
        pid = f"CSV-{eid}"
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        name = (row.get("external_product_name") or "").strip()
        brand = name.split(" ")[0] if name else "Unknown"
        dims = size_map.get(eid, {})
        w_in = round(dims.get("width_cm", 7.5) * CM_TO_IN, 2)
        h_in = round(dims.get("height_cm", 20.0) * CM_TO_IN, 2)
        prod_width_in[pid] = w_in
        prod_entry = {
            "id": pid,
            "upc": eid,
            "name": dims.get("tiny_name") or name or pid,
            "brand": brand,
            "manufacturer": "Demo CSV",
            "category": "Coffee",
            "subcategory": "Demo Import",
            "beer_type": "N/A",
            "package_type": "pack_box",
            "pack_size": 1,
            "unit_size_oz": 0.0,
            "width_in": w_in,
            "height_in": h_in,
            "depth_in": 4.0,
            "price": 0.0,
            "cost": 0.0,
            "abv": 0.0,
            "color_hex": _stable_color_from_text(pid),
            "weekly_units_sold": 0,
        }
        if eid in image_map:
            prod_entry["image_url"] = image_map[eid]
        products.append(prod_entry)

    # Group rows by bay/shelf and sort by on_shelf_position
    grouped = defaultdict(list)
    for row in rows:
        key = (int(row["eq_num_in_scene_group"]), int(row["shelf_number"]))
        grouped[key].append(row)
    for key in grouped:
        grouped[key].sort(key=lambda r: int(r.get("on_shelf_position") or 0))

    bay_numbers = sorted({int(r["eq_num_in_scene_group"]) for r in rows})
    shelf_numbers = sorted({int(r["shelf_number"]) for r in rows})
    max_shelf = max(shelf_numbers)

    bay_depth_in = 8.0

    # Calculate bay widths from actual product widths on widest shelf per bay
    bay_computed_widths = {}
    for bay_num in bay_numbers:
        max_w = 0.0
        for shelf_num in range(1, max_shelf + 1):
            shelf_rows = grouped.get((bay_num, shelf_num), [])
            shelf_w = 0.0
            for r in shelf_rows:
                pid = f"CSV-{r['external_product_id']}"
                fw = max(1, int(r.get("faces_width") or 1))
                shelf_w += prod_width_in.get(pid, 3.0) * fw
            max_w = max(max_w, shelf_w)
        bay_computed_widths[bay_num] = round(max_w + 1.0, 1)  # 1in margin

    # Compute shelf clearance from tallest product on each shelf tier
    shelf_max_height = {}
    for (bay_num, shelf_num), shelf_rows in grouped.items():
        for r in shelf_rows:
            pid = f"CSV-{r['external_product_id']}"
            p = next((pp for pp in products if pp["id"] == pid), None)
            h = p["height_in"] if p else 8.0
            shelf_max_height[shelf_num] = max(shelf_max_height.get(shelf_num, 0), h)

    bays = []
    for bay_num in bay_numbers:
        bay_width_in = bay_computed_widths[bay_num]

        # Shelf #1 = top, shelf #max = bottom
        # y_position counts up from floor; so shelf #max gets lowest y
        shelf_defs = []
        y_cursor = 2.0  # start 2in from floor for bottom shelf
        for shelf_num in range(max_shelf, 0, -1):
            clearance = shelf_max_height.get(shelf_num, 8.0) + 1.5
            shelf_rows = grouped.get((bay_num, shelf_num), [])

            # Calculate cumulative x_position from real widths
            positions = []
            x_cursor = 0.0
            for r in shelf_rows:
                pid = f"CSV-{r['external_product_id']}"
                facings_wide = max(1, int(r.get("faces_width") or 1))
                facings_high = max(1, int(r.get("faces_height") or 1))
                facings_deep = max(1, int(r.get("faces_depth") or 1))
                positions.append({
                    "product_id": pid,
                    "x_position": round(x_cursor, 2),
                    "facings_wide": facings_wide,
                    "facings_high": facings_high,
                    "facings_deep": facings_deep,
                    "orientation": "front",
                })
                x_cursor += prod_width_in.get(pid, 3.0) * facings_wide

            shelf_defs.append({
                "shelf_number": shelf_num,
                "width_in": bay_width_in,
                "height_in": round(clearance, 1),
                "depth_in": bay_depth_in,
                "y_position": round(y_cursor, 1),
                "positions": positions,
                "shelf_type": "standard",
            })
            y_cursor += clearance

        # shelf_defs built bottom-up; keep as-is (renderer uses y_position)
        bay_height_in = round(y_cursor + 2.0, 1)

        bays.append({
            "bay_number": bay_num,
            "width_in": bay_width_in,
            "height_in": bay_height_in,
            "depth_in": bay_depth_in,
            "shelves": shelf_defs,
            "glued_right": False,
        })

    planogram_data = {
        "id": "PLN-CSV-COFFEE-617533",
        "name": "Coffee Demo Planogram (CSV Import)",
        "category": "Coffee",
        "store_type": "Demo Store",
        "effective_date": "2026-02-18",
        "metadata": {
            "version": "1.0",
            "generated_by": "CSV Demo Import",
            "placement_strategy": "eq_num_in_scene_group/shelf_number/on_shelf_position mapping",
            "source_file": os.path.basename(csv_path),
        },
        "equipment": {
            "id": "EQ-CSV-001",
            "name": "Coffee Equipment",
            "equipment_type": "gondola",
            "bays": bays,
        },
        "products": products,
    }

    return Planogram.from_dict(planogram_data)


def _load_coffee_planogram():
    """Load coffee planogram into current state (non-HTTP helper)."""
    global current_planogram, current_summary, current_compliance, current_decision_tree, current_equipment

    coffee_json = os.path.join(os.path.dirname(__file__), "data", "coffee_default_planogram.json")
    with open(coffee_json, "r", encoding="utf-8") as f:
        planogram_data = json.load(f)

    image_map = _build_image_map()
    for prod in planogram_data.get("products", []):
        upc = prod.get("upc", "")
        if upc and upc in image_map:
            prod["image_url"] = image_map[upc]

    current_planogram = Planogram.from_dict(planogram_data)
    current_summary = generate_summary(current_planogram, len(current_planogram.products))
    current_compliance = None
    current_decision_tree = None
    from dataclasses import asdict
    current_equipment = asdict(current_planogram.equipment) if current_planogram.equipment else None
    _save_state()


@app.route("/")
def index():
    """Serve the main visualization page. ?mode=beer (default) or ?mode=coffee."""
    mode = request.args.get("mode", "beer").lower()
    if mode not in ("beer", "coffee"):
        mode = "beer"

    if mode == "coffee":
        if current_planogram is None or current_planogram.category != "Coffee":
            _load_coffee_planogram()
    else:
        if current_planogram is None or current_planogram.category == "Coffee":
            init_default_planogram()

    return render_template("index.html", mode=mode)


@app.route("/api/planogram", methods=["GET"])
def get_planogram():
    """Return current planogram data as JSON."""
    global current_planogram, current_summary, current_compliance, current_decision_tree
    mode = request.args.get("mode", "").lower()
    if mode == "coffee":
        if current_planogram is None or current_planogram.category != "Coffee":
            _load_coffee_planogram()
    elif mode == "beer":
        if current_planogram is None or current_planogram.category == "Coffee":
            init_default_planogram()
    else:
        if current_planogram is None:
            if not _load_saved_state():
                init_default_planogram()
    return jsonify({
        "planogram": current_planogram.to_dict(),
        "summary": current_summary,
        "decision_tree": current_decision_tree.to_dict() if current_decision_tree else None,
        "compliance": current_compliance.to_dict() if current_compliance else None,
    })


@app.route("/api/generate", methods=["POST"])
def generate():
    """Generate a new planogram from user input (rule-based fallback)."""
    global current_planogram, current_summary

    data = request.json or {}

    # Check if it's a text-based input
    if "user_input" in data:
        config = process_user_input(data["user_input"])
    elif "equipment_config" in data:
        config = data["equipment_config"]
    else:
        config = {}

    # Generate planogram
    current_planogram = generate_planogram(
        equipment_config=config if config else None,
        planogram_name=data.get("name", "Beer Category Planogram"),
        store_type=data.get("store_type", "Standard Grocery")
    )
    current_summary = generate_summary(current_planogram, _full_catalog_size())
    _save_state()

    return jsonify({
        "planogram": current_planogram.to_dict(),
        "summary": current_summary,
        "status": "success",
        "source": "rule_based"
    })


@app.route("/api/remove-products", methods=["POST"])
def remove_products():
    """Remove all products from shelves, keeping the equipment structure."""
    global current_planogram, current_summary, current_compliance

    if current_planogram is None:
        if not _load_saved_state():
            init_default_planogram()

    eq = current_planogram.equipment
    if eq:
        for bay in eq.bays:
            for shelf in bay.shelves:
                shelf.positions = []
    current_planogram.products = []
    current_compliance = None
    current_summary = generate_summary(current_planogram, _full_catalog_size())
    _save_state()

    return jsonify({
        "planogram": current_planogram.to_dict(),
        "summary": current_summary,
        "decision_tree": current_decision_tree.to_dict() if current_decision_tree else None,
        "compliance": None,
        "status": "success",
        "source": "equipment_only",
    })


@app.route("/api/generate-equipment", methods=["POST"])
def generate_equipment():
    """
    Step 1: Generate empty equipment from user-specified parameters.

    Expects JSON body with any/all of:
      equipment_type, num_bays, num_shelves, bay_width, bay_height, bay_depth

    Returns empty equipment JSON (shelves have no positions).
    """
    global current_equipment, current_planogram, current_summary

    data = request.json or {}
    defaults = load_default_equipment_config()

    config = {
        "equipment_type": data.get("equipment_type", defaults["equipment_type"]),
        "num_bays":       int(data.get("num_bays", defaults["num_bays"])),
        "num_shelves":    int(data.get("num_shelves", defaults["num_shelves"])),
        "bay_width":      float(data.get("bay_width", defaults["bay_width"])),
        "bay_height":     float(data.get("bay_height", defaults["bay_height"])),
        "bay_depth":      float(data.get("bay_depth", defaults["bay_depth"])),
        "bays_config":    data.get("bays_config", defaults.get("bays_config")),
    }

    # Create equipment object
    equipment = create_default_equipment(**config)

    # Store as dict for Step 2
    from dataclasses import asdict
    current_equipment = asdict(equipment)

    # Build a planogram shell (no products) for visualization
    from datetime import date
    current_planogram = Planogram(
        id="PLN-BEER-001",
        name=f"Beer {config['equipment_type'].title()} Planogram",
        category="Beer",
        store_type="Standard Grocery",
        effective_date=date.today().isoformat(),
        equipment=equipment,
        products=[],
        metadata={
            "version": "1.0",
            "generated_by": "Equipment Generator",
            "placement_strategy": "empty — awaiting product fill",
        },
    )
    current_summary = generate_summary(current_planogram, _full_catalog_size())
    _save_state()

    return jsonify({
        "planogram": current_planogram.to_dict(),
        "summary": current_summary,
        "status": "success",
        "source": "equipment_only",
    })


def _postprocess_pipeline(filled_equipment, selected_products, facings, prod_map, rules):
    """
    Run the 6-step post-processing pipeline (B–E) and return final equipment + stats.
    Steps: overflow fix → recover missing → boost → gap fill → audit.
    """
    import time as _time

    timings = {}

    # Step B: Fix shelf overflows
    t0 = _time.time()
    filled_equipment = validate_and_fix_shelves(filled_equipment, prod_map)
    timings["overflow_fix"] = _time.time() - t0

    # Step C: Recover any products missed
    t0 = _time.time()
    filled_equipment, recovered_ids = recover_missing_products(
        filled_equipment, selected_products, facings, prod_map,
    )
    timings["recovery"] = _time.time() - t0

    # Step D: Boost facings on underused shelves
    t0 = _time.time()
    filled_equipment = boost_underused_shelves(
        filled_equipment, prod_map, facings, rules.max_facings,
    )
    timings["boost"] = _time.time() - t0

    # Step E: Fill remaining shelf gaps with best sellers
    t0 = _time.time()
    filled_equipment = fill_shelf_gaps(
        filled_equipment, selected_products, prod_map,
        target_pct=rules.fill_target_pct,
    )
    timings["gap_fill"] = _time.time() - t0

    return filled_equipment, timings


def _audit_equipment(filled_equipment, prod_map):
    """Count products, facings, and used width from equipment dict.
    Skips phantom positions (cross-bay duplicates) to avoid double-counting."""
    placed_ids = set()
    total_facings = 0
    used_width = 0.0
    for bay in filled_equipment.get("bays", []):
        for shelf in bay.get("shelves", []):
            for pos in shelf.get("positions", []):
                if pos.get("_phantom"):
                    continue
                pid = pos.get("product_id", "")
                placed_ids.add(pid)
                f_w = pos.get("facings_wide", 1)
                total_facings += f_w
                prod = prod_map.get(pid)
                if prod:
                    used_width += prod.get("width_in", 0) * f_w
    total_w = get_total_shelf_width(filled_equipment)
    fill_pct = (used_width / total_w * 100) if total_w > 0 else 0
    return {
        "products": len(placed_ids),
        "facings": total_facings,
        "used_width": round(used_width, 1),
        "total_width": round(total_w, 1),
        "fill_pct": round(fill_pct, 1),
        "placed_ids": placed_ids,
    }


@app.route("/api/fill-products", methods=["POST"])
def fill_products():
    """
    Step 2: Fill equipment with products.

    Supports mode parameter:
      - "ai"        : Gemini AI placement → post-processing (default)
      - "algorithm"  : Rule-based placement → post-processing
      - "compare"    : Run BOTH, return side-by-side comparison

    Phase 1+2 (capacity check + optimal facings) always runs first.
    """
    global current_planogram, current_summary, current_equipment

    import time as _time
    import copy

    data = request.json or {}
    mode = data.get("mode", "ai")  # "ai", "algorithm", or "compare"

    # Accept equipment from request body as fallback if server state was lost
    if current_equipment is None and "equipment" in data:
        current_equipment = data["equipment"]
    elif current_equipment is None:
        return jsonify({
            "status": "error",
            "error": "No equipment generated yet. Run Step 1 first.",
        }), 400

    # Build rules
    rules = ProductLogicRules(
        fill_target_pct=float(data.get("fill_target_pct", 99)),
        max_facings=int(data.get("max_facings", 5)),
        group_by=data.get("group_by", "subcategory"),
    )

    products_json = _load_products_json()
    prod_map = {p["id"]: p for p in products_json}
    decision_tree = get_tree_for_category("Beer")

    # ── Phase 1 + 2: Compute selected products & optimal facings ──
    t_phase12 = _time.time()
    equipment_copy = copy.deepcopy(current_equipment)
    selected_products, facings = compute_facings_for_ai(
        equipment_copy, products_json, rules
    )
    phase12_ms = round((_time.time() - t_phase12) * 1000)

    total_w = get_total_shelf_width(equipment_copy)
    used_w = sum(p["width_in"] * facings[p["id"]] for p in selected_products)
    print(f"[Fill] Phase 1+2: {len(selected_products)} products, "
          f"{sum(facings.values())} facings, "
          f"{used_w:.1f}/{total_w:.1f}in ({used_w/total_w*100:.1f}%) "
          f"[{phase12_ms}ms]", flush=True)

    # ── Helper: run a single mode and return results ──
    def _run_mode(run_mode):
        t_start = _time.time()
        eq_copy = copy.deepcopy(current_equipment)
        src = run_mode
        timings = {"phase12_ms": phase12_ms}

        if run_mode == "ai":
            try:
                t_ai = _time.time()
                prompt = build_fill_prompt(
                    eq_copy, selected_products, facings, rules,
                    decision_tree=decision_tree,
                )
                result = fill_products_with_ai(eq_copy, products_json, prompt)
                filled_eq = result["equipment"]
                timings["ai_call_ms"] = round((_time.time() - t_ai) * 1000)
                src = "gemini_ai"
            except Exception as ai_err:
                print(f"[Fill] AI failed ({ai_err}), falling back to rule-based",
                      flush=True)
                traceback.print_exc()
                eq_copy = copy.deepcopy(current_equipment)
                t_rb = _time.time()
                result = fill_equipment_rule_based(
                    eq_copy, products_json, rules, decision_tree=decision_tree,
                )
                filled_eq = result["equipment"]
                timings["rule_based_ms"] = round((_time.time() - t_rb) * 1000)
                src = "rule_based_fallback"
        elif run_mode == "cross_bay":
            t_rb = _time.time()
            result = fill_equipment_cross_bay(
                eq_copy, products_json, rules, decision_tree=decision_tree,
            )
            filled_eq = result["equipment"]
            timings["rule_based_ms"] = round((_time.time() - t_rb) * 1000)
            src = "cross_bay"
        else:
            t_rb = _time.time()
            result = fill_equipment_rule_based(
                eq_copy, products_json, rules, decision_tree=decision_tree,
            )
            filled_eq = result["equipment"]
            timings["rule_based_ms"] = round((_time.time() - t_rb) * 1000)
            src = "algorithm"

        # Audit before post-processing
        before = _audit_equipment(filled_eq, prod_map)
        print(f"[{src}] Before post-process: {before['products']} products, "
              f"{before['facings']} facings, {before['fill_pct']}%", flush=True)

        # Post-processing pipeline
        # For algorithm mode: Phase 3 already places products in tree order
        # and distributes facings. Only run overflow fix (safe for compliance).
        # For AI mode: run full pipeline (recover, boost, gap-fill).
        t_pp = _time.time()
        if run_mode in ("algorithm", "cross_bay"):
            # Minimal post-processing: only fix shelf overflows
            filled_eq = validate_and_fix_shelves(filled_eq, prod_map)
            pp_timings = {"overflow_fix": _time.time() - t_pp}
            print(f"[{src}] {run_mode} mode: skipping recover/boost/gap-fill "
                  f"to preserve tree compliance", flush=True)
        else:
            filled_eq, pp_timings = _postprocess_pipeline(
                filled_eq, selected_products, facings, prod_map, rules,
            )
        timings["postprocess_ms"] = round((_time.time() - t_pp) * 1000)
        timings.update({f"pp_{k}_ms": round(v * 1000) for k, v in pp_timings.items()})

        # Final audit
        after = _audit_equipment(filled_eq, prod_map)
        timings["total_ms"] = round((_time.time() - t_start) * 1000)

        print(f"[{src}] Final: {after['products']} products, "
              f"{after['facings']} facings, {after['fill_pct']}% "
              f"[total={timings['total_ms']}ms]", flush=True)

        return filled_eq, after, src, timings

    # ── Execute based on mode ──
    if mode == "compare":
        # Run algorithm first (fast), then AI
        print(f"\n{'='*60}", flush=True)
        print(f"[COMPARE] Running ALGORITHM mode...", flush=True)
        algo_eq, algo_stats, algo_src, algo_timings = _run_mode("algorithm")

        # Validate compliance for algorithm
        algo_compliance = None
        if decision_tree:
            algo_placed = [p for p in products_json if p["id"] in algo_stats["placed_ids"]]
            algo_planogram_data = {"equipment": algo_eq, "products": algo_placed}
            algo_compliance = validate_compliance(algo_planogram_data, decision_tree)

        print(f"\n[COMPARE] Running AI mode...", flush=True)
        ai_eq, ai_stats, ai_src, ai_timings = _run_mode("ai")

        # Validate compliance for AI
        ai_compliance = None
        if decision_tree:
            ai_placed = [p for p in products_json if p["id"] in ai_stats["placed_ids"]]
            ai_planogram_data = {"equipment": ai_eq, "products": ai_placed}
            ai_compliance = validate_compliance(ai_planogram_data, decision_tree)

        # Print comparison table
        print(f"\n{'='*60}", flush=True)
        print(f"[COMPARE] === RESULTS ===", flush=True)
        print(f"  {'Metric':<25} {'Algorithm':>12} {'AI':>12}", flush=True)
        print(f"  {'-'*25} {'-'*12} {'-'*12}", flush=True)
        print(f"  {'Products placed':<25} {algo_stats['products']:>12} {ai_stats['products']:>12}", flush=True)
        print(f"  {'Total facings':<25} {algo_stats['facings']:>12} {ai_stats['facings']:>12}", flush=True)
        print(f"  {'Fill %':<25} {algo_stats['fill_pct']:>11.1f}% {ai_stats['fill_pct']:>11.1f}%", flush=True)
        a_comp = f"{algo_compliance.overall_pct:.1f}%" if algo_compliance else "N/A"
        i_comp = f"{ai_compliance.overall_pct:.1f}%" if ai_compliance else "N/A"
        print(f"  {'Decision tree compliance':<25} {a_comp:>12} {i_comp:>12}", flush=True)
        print(f"  {'Total time (ms)':<25} {algo_timings['total_ms']:>12} {ai_timings['total_ms']:>12}", flush=True)
        speedup = ai_timings['total_ms'] / max(algo_timings['total_ms'], 1)
        print(f"  {'Speedup':<25} {'':>12} {speedup:>11.0f}x", flush=True)
        print(f"{'='*60}\n", flush=True)

        # Use the best result (algorithm is much faster, use it if fill is comparable)
        # Return comparison data so UI can display it
        return jsonify({
            "status": "success",
            "mode": "compare",
            "comparison": {
                "algorithm": {
                    "fill_pct": algo_stats["fill_pct"],
                    "products": algo_stats["products"],
                    "facings": algo_stats["facings"],
                    "compliance": algo_compliance.overall_pct if algo_compliance else None,
                    "time_ms": algo_timings["total_ms"],
                    "timings": algo_timings,
                },
                "ai": {
                    "fill_pct": ai_stats["fill_pct"],
                    "products": ai_stats["products"],
                    "facings": ai_stats["facings"],
                    "compliance": ai_compliance.overall_pct if ai_compliance else None,
                    "time_ms": ai_timings["total_ms"],
                    "timings": ai_timings,
                },
            },
            # Use algorithm result for display (it ran first, much faster)
            "planogram": None,  # Signal to UI to pick
            "source": "compare",
        })

    # ── Single mode (ai or algorithm) ──
    filled_equipment, stats, source, timings = _run_mode(mode)

    # Update placed_products to reflect what's actually on shelves
    placed_products = [p for p in products_json if p["id"] in stats["placed_ids"]]

    # Build planogram object
    from datetime import date
    planogram_data = {
        "id": "PLN-BEER-001",
        "name": current_planogram.name if current_planogram else "Beer Planogram",
        "category": "Beer",
        "store_type": "Standard Grocery",
        "effective_date": date.today().isoformat(),
        "metadata": {
            "version": "1.0",
            "generated_by": f"Product Logic ({source})",
            "placement_strategy": f"fill_target={rules.fill_target_pct}%, "
                                  f"{len(selected_products)} products, "
                                  f"{sum(facings.values())} facings",
        },
        "equipment": filled_equipment,
        "products": placed_products,
    }

    current_planogram = Planogram.from_dict(planogram_data)
    current_summary = generate_summary(current_planogram, _full_catalog_size())

    # Validate decision tree compliance
    global current_compliance, current_decision_tree
    compliance = None
    current_decision_tree = decision_tree
    if decision_tree:
        compliance = validate_compliance(planogram_data, decision_tree)
        current_compliance = compliance

    _save_state()

    return jsonify({
        "planogram": current_planogram.to_dict(),
        "summary": current_summary,
        "status": "success",
        "source": source,
        "decision_tree": decision_tree.to_dict() if decision_tree else None,
        "compliance": compliance.to_dict() if compliance else None,
        "timings": timings,
    })


@app.route("/api/generate-ai", methods=["POST"])
def generate_ai():
    """
    Generate a planogram using Gemini 2.5 Flash AI.
    
    Expects JSON body:
      { "user_input": "Create a 4-bay cooler with 6 shelves..." }
    
    Sends the user request + full product catalog + schema instructions to Gemini,
    then parses the response and returns it for visualization.
    """
    global current_planogram, current_summary

    data = request.json or {}
    user_input = data.get("user_input", "").strip()

    if not user_input:
        user_input = "Create a standard beer planogram with 3 bays, 5 shelves per bay, gondola type, 48 inches wide, 72 inches tall. Optimize product placement for maximum sales."

    try:
        # Load full product catalog
        products_json = _load_products_json()

        # Call Gemini
        planogram_data = generate_planogram_with_ai(user_input, products_json)

        # Ensure required fields have defaults
        planogram_data.setdefault("category", "Beer")
        planogram_data.setdefault("store_type", "Standard Grocery")
        planogram_data.setdefault("effective_date", "2026-02-12")
        planogram_data.setdefault("metadata", {})

        # Parse into Planogram object for summary generation
        current_planogram = Planogram.from_dict(planogram_data)
        current_summary = generate_summary(current_planogram, _full_catalog_size())
        _save_state()

        return jsonify({
            "planogram": current_planogram.to_dict(),
            "summary": current_summary,
            "status": "success",
            "source": "gemini_ai"
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "error": str(e),
            "source": "gemini_ai"
        }), 500


@app.route("/api/decision-tree", methods=["GET"])
def get_decision_tree():
    """Return the pre-built decision tree for a category."""
    category = request.args.get("category", "Beer")
    tree = get_tree_for_category(category)
    if tree:
        return jsonify(tree.to_dict())
    return jsonify({"error": f"No decision tree for category: {category}"}), 404


@app.route("/api/products", methods=["GET"])
def get_products():
    """Return products for the currently loaded planogram.
    Falls back to the beer catalog if no planogram is loaded."""
    if current_planogram and current_planogram.products:
        from dataclasses import asdict
        return jsonify([asdict(p) for p in current_planogram.products])
    return jsonify(_load_products_json())


# ── Supabase Recognition Data ─────────────────────────────────────────────────

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://zcciroutarcpkwpnynyh.supabase.co"
)
SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpjY2lyb3V0YXJjcGt3cG55bnloIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3NzI3MjIzMTAsImV4cCI6MjA4ODI5ODMxMH0."
    "LFnJ8WoxlNhZ06MBQm-1mmJK4mtkBLZAPd4UoPtGrkE"
)
_SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}


def _supabase_get(table: str, params: dict | None = None) -> list:
    """GET rows from a Supabase table via REST API."""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = http_requests.get(url, headers=_SUPABASE_HEADERS, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _supabase_photo_list() -> list[str]:
    """Return distinct photo_names stored in recognition_photos."""
    rows = _supabase_get("recognition_photos", {"select": "photo_name", "order": "photo_name"})
    return [r["photo_name"] for r in rows]


def _supabase_shelves(photo_name: str) -> list:
    """Fetch raw shelf detections from Supabase for a photo_name."""
    rows = _supabase_get("recognition_raw_shelves", {
        "select": "external_id,photo_id,x1,y1,x2,y2,line_type,approved,shelf_idx,internal_idx,is_hook,photo_recognized_version",
        "photo_name": f"eq.{photo_name}",
        "order": "y1",
    })
    return [{"_id": r["external_id"], **{k: r[k] for k in r if k != "external_id"}} for r in rows]


def _supabase_assortment_products(photo_name: str) -> list:
    """Fetch assortment data from Supabase and transform to photo-viewer format."""
    rows = _supabase_get("recognition_assortment", {
        "select": "*",
        "photo_name": f"eq.{photo_name}",
        "order": "line,numgroup",
    })
    products = []
    for item in rows:
        prod = item.get("product_info") or {}
        facing = item.get("facing") or {}
        group = item.get("group_data") or {}
        products.append({
            "_id": item.get("external_id", ""),
            "product_id": item.get("product_id", ""),
            "art": prod.get("tiny_name", "") or item.get("product_id", ""),
            "x1": item.get("x1", 0),
            "y1": item.get("y1", 0),
            "x2": item.get("x2", 0),
            "y2": item.get("y2", 0),
            "display_name": prod.get("tiny_name", ""),
            "full_name": prod.get("name", ""),
            "brand_name": prod.get("brand_name", ""),
            "sub_brand_name": prod.get("sub_brand_name", ""),
            "brand_owner_name": prod.get("brand_owner_name", ""),
            "category_name": prod.get("category_name", ""),
            "macro_category_name": prod.get("macro_category_name", ""),
            "miniature_url": prod.get("miniature_url", ""),
            "barcode": prod.get("barcode", ""),
            "classification_score": item.get("kma", 0) / 100 if item.get("kma") else 0,
            "is_duplicated": item.get("is_duplicated", False),
            "line": item.get("line", 0),
            "numgroup": item.get("numgroup", 0),
            "facing_count": facing.get("fact", 1),
            "facing_width_cm": facing.get("width_cm", 0),
            "facing_height_cm": facing.get("height_cm", 0),
            "group_count": group.get("fact", 1),
            "group_width_cm": group.get("width_cm", 0),
            "group_height_cm": group.get("height_cm", 0),
            "price": item.get("price", 0),
            "price_type": item.get("price_type", 0),
            "price_status": item.get("price_status", ""),
            "assortment_group": item.get("assortment_group", 0),
            "start_group": item.get("start_group", False),
            "is_support": item.get("is_support", False),
        })
    return products


# ── Photo Viewer ──────────────────────────────────────────────────────────────

def _load_assortment_products(assortment_path: str) -> list:
    """Transform assortment JSON into the product list format for the photo viewer.

    Each assortment item contains rich product info (brand, category, miniature_url,
    dimensions, price) which we flatten for the viewer."""
    with open(assortment_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    products = []
    for item in raw:
        prod = item.get("product", {})
        facing = item.get("facing", {})
        group = item.get("group", {})
        products.append({
            "_id": item.get("_id", ""),
            "product_id": item.get("product_id", ""),
            "art": prod.get("tiny_name", "") or item.get("product_id", ""),
            "x1": item.get("x1", 0),
            "y1": item.get("y1", 0),
            "x2": item.get("x2", 0),
            "y2": item.get("y2", 0),
            "display_name": prod.get("tiny_name", ""),
            "full_name": prod.get("name", ""),
            "brand_name": prod.get("brand_name", ""),
            "sub_brand_name": prod.get("sub_brand_name", ""),
            "brand_owner_name": prod.get("brand_owner_name", ""),
            "category_name": prod.get("category_name", ""),
            "macro_category_name": prod.get("macro_category_name", ""),
            "miniature_url": prod.get("miniature_url", ""),
            "barcode": prod.get("barcode", ""),
            "classification_score": item.get("kma", 0) / 100 if item.get("kma") else 0,
            "is_duplicated": item.get("is_duplicated", False),
            "line": item.get("line", 0),
            "numgroup": item.get("numgroup", 0),
            "facing_count": facing.get("fact", 1),
            "facing_width_cm": facing.get("width_cm", 0),
            "facing_height_cm": facing.get("height_cm", 0),
            "group_count": group.get("fact", 1),
            "group_width_cm": group.get("width_cm", 0),
            "group_height_cm": group.get("height_cm", 0),
            "price": item.get("price", 0),
            "price_type": item.get("price_type", 0),
            "price_status": item.get("price_status", ""),
            "assortment_group": item.get("assortment_group", 0),
            "start_group": item.get("start_group", False),
            "is_support": item.get("is_support", False),
        })
    return products


def _load_art_name_map() -> dict:
    """Build art→tiny_name mapping from product_art_mapping.csv."""
    csv_path = os.path.join(os.path.dirname(__file__), "Demo data", "product_art_mapping.csv")
    mapping = {}
    if not os.path.exists(csv_path):
        return mapping
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            art = (row.get("art") or "").strip()
            if art:
                mapping[art] = {
                    "tiny_name": (row.get("tiny_name") or "").strip(),
                    "name": (row.get("name") or "").strip(),
                }
    return mapping


@app.route("/photo-viewer")
def photo_viewer():
    """Serve the interactive photo bounding-box viewer."""
    demo_dir = os.path.join(os.path.dirname(__file__), "Demo data")
    photos = []
    for fname in sorted(os.listdir(demo_dir)):
        if fname.endswith(".jpg") or fname.endswith(".png"):
            base = fname.rsplit(".", 1)[0]
            prod_file = os.path.join(demo_dir, f"{base}_raw_products.json")
            shelf_file = os.path.join(demo_dir, f"{base}_raw_shelves.json")
            if os.path.exists(prod_file) and os.path.exists(shelf_file):
                photos.append(base)
    return render_template("photo_viewer.html", photos=photos)


@app.route("/api/photo-list")
def photo_list():
    """Return list of available photo names. ?source=supabase fetches from DB."""
    source = request.args.get("source", "json")
    if source == "supabase":
        try:
            names = _supabase_photo_list()
            return jsonify({"photos": names, "source": "supabase"})
        except Exception as e:
            return jsonify({"error": str(e), "source": "supabase"}), 502
    demo_dir = os.path.join(os.path.dirname(__file__), "Demo data")
    photos = []
    for fname in sorted(os.listdir(demo_dir)):
        if fname.endswith(".jpg") or fname.endswith(".png"):
            base = fname.rsplit(".", 1)[0]
            if os.path.exists(os.path.join(demo_dir, f"{base}_raw_products.json")):
                photos.append(base)
    return jsonify({"photos": photos, "source": "json"})


@app.route("/api/photo-data/<photo_name>")
def photo_data(photo_name):
    """Return products + shelves JSON for a given photo base name.

    ?source=supabase  → fetch from Supabase recognition tables.
    Otherwise prefers assortment JSON, falling back to raw_products + art_mapping.
    """
    source = request.args.get("source", "json")

    if source == "supabase":
        try:
            products = _supabase_assortment_products(photo_name)
            shelves = _supabase_shelves(photo_name)
            return jsonify({"products": products, "shelves": shelves, "source": "supabase"})
        except Exception as e:
            return jsonify({"error": str(e), "source": "supabase"}), 502

    demo_dir = os.path.join(os.path.dirname(__file__), "Demo data")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    shelf_file = os.path.join(demo_dir, f"{photo_name}_raw_shelves.json")

    if not os.path.exists(shelf_file):
        return jsonify({"error": "Photo data not found"}), 404

    with open(shelf_file, "r", encoding="utf-8") as f:
        shelves = json.load(f)

    assortment_file = os.path.join(data_dir, f"{photo_name}_assortment.json")
    if os.path.exists(assortment_file):
        products = _load_assortment_products(assortment_file)
        return jsonify({"products": products, "shelves": shelves, "source": "assortment"})

    prod_file = os.path.join(demo_dir, f"{photo_name}_raw_products.json")
    if not os.path.exists(prod_file):
        return jsonify({"error": "Photo data not found"}), 404

    with open(prod_file, "r", encoding="utf-8") as f:
        products = json.load(f)

    art_map = _load_art_name_map()
    for p in products:
        art = p.get("art", "")
        info = art_map.get(art, {})
        p["display_name"] = info.get("tiny_name") or art.replace("_", " ").title()
        p["full_name"] = info.get("name") or ""

    return jsonify({"products": products, "shelves": shelves, "source": "raw"})


@app.route("/api/planogram-facings")
def planogram_facings():
    """Return planogram facing counts keyed by tiny_name for cross-referencing with photos.

    Builds a map: tiny_name → {facings_wide, positions, in_planogram}.
    Uses product_code_external_id_map.csv to translate external_id → tiny_name.
    """
    global current_planogram
    if current_planogram is None:
        if not _load_saved_state():
            init_default_planogram()

    size_map = _load_product_sizes()
    # external_id → tiny_name
    ext_to_tiny = {eid: info["tiny_name"] for eid, info in size_map.items() if info.get("tiny_name")}

    facings = {}  # tiny_name → {facings_wide, positions}
    if current_planogram and current_planogram.equipment:
        from dataclasses import asdict
        eq = asdict(current_planogram.equipment)
        for bay in eq.get("bays", []):
            for shelf in bay.get("shelves", []):
                for pos in shelf.get("positions", []):
                    pid = pos.get("product_id", "")
                    if pos.get("_phantom"):
                        continue
                    ext_id = pid.replace("CSV-", "") if pid.startswith("CSV-") else pid
                    tiny = ext_to_tiny.get(ext_id, "")
                    if not tiny:
                        continue
                    fw = pos.get("facings_wide", 1)
                    if tiny not in facings:
                        facings[tiny] = {"facings_wide": 0, "positions": 0}
                    facings[tiny]["facings_wide"] += fw
                    facings[tiny]["positions"] += 1

    return jsonify(facings)


@app.route("/demo-images/<path:filename>")
def demo_images(filename):
    """Serve images from the Demo data folder."""
    from flask import send_from_directory
    demo_dir = os.path.join(os.path.dirname(__file__), "Demo data")
    return send_from_directory(demo_dir, filename)


@app.route("/api/load-demo-csv", methods=["POST"])
def load_demo_csv():
    """Load pre-built coffee planogram from data/coffee_default_planogram.json."""
    try:
        _load_coffee_planogram()
        return jsonify({
            "status": "success",
            "source": "coffee_default_planogram",
            "planogram": current_planogram.to_dict(),
            "summary": current_summary,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "error": str(e),
        }), 400


# Load persisted state on startup; fall back to generating from defaults
if not _load_saved_state():
    init_default_planogram()

if __name__ == "__main__":
    print("\n  Planogram Agent running at http://localhost:5001\n")
    app.run(debug=True, port=5001)
