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


def _save_state(also_supabase: bool = False):
    """Persist current planogram + summary + decision tree + compliance to disk.

    When also_supabase=True, also push to the Supabase planograms table.
    """
    if current_planogram is None:
        return
    def _as_dict(obj):
        if obj is None:
            return None
        return obj.to_dict() if hasattr(obj, "to_dict") else obj

    payload = {
        "planogram": current_planogram.to_dict(),
        "summary": current_summary,
        "decision_tree": _as_dict(current_decision_tree),
        "compliance": _as_dict(current_compliance),
    }
    try:
        with open(CURRENT_PLANOGRAM_FILE, 'w') as f:
            json.dump(payload, f, indent=2, default=str)
    except Exception as e:
        print(f"[save] Failed to write {CURRENT_PLANOGRAM_FILE}: {e}", flush=True)

    if also_supabase:
        _save_planogram_to_supabase(
            current_planogram, current_summary, current_decision_tree, current_compliance
        )


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
    """Load product dimensions from test_coffee_product_map in Supabase.
    Returns dict keyed by product_code → {width_cm, height_cm, name, tiny_name, recognition_id}."""
    try:
        rows = _supabase_get("test_coffee_product_map", {
            "select": "product_code,tiny_name,product_name,width_cm,height_cm,recognition_id",
        })
        return {
            r["product_code"]: {
                "width_cm": float(r["width_cm"] or 0),
                "height_cm": float(r["height_cm"] or 0),
                "name": r.get("product_name") or "",
                "tiny_name": r.get("tiny_name") or "",
                "recognition_id": r.get("recognition_id") or "",
            }
            for r in rows if r.get("product_code")
        }
    except Exception as e:
        print(f"[product_sizes] Supabase failed: {e}", flush=True)
        return {}


def _build_image_map() -> dict:
    """Build external_product_id → miniature_url from test_coffee_product_map."""
    try:
        rows = _supabase_get("test_coffee_product_map", {
            "select": "product_code,miniature_url",
            "miniature_url": "not.is.null",
        })
        return {r["product_code"]: r["miniature_url"]
                for r in rows if r.get("product_code") and r.get("miniature_url")}
    except Exception as e:
        print(f"[image_map] Supabase failed: {e}", flush=True)
        return {}


def _build_no_bg_image_map() -> dict:
    """Build recognition_id → image_no_bg_url from test_coffee_product_map."""
    try:
        rows = _supabase_get("test_coffee_product_map", {
            "select": "recognition_id,image_no_bg_url",
            "image_no_bg_url": "not.is.null",
        })
        return {r["recognition_id"]: r["image_no_bg_url"]
                for r in rows if r.get("recognition_id") and r.get("image_no_bg_url")}
    except Exception as e:
        print(f"[no_bg_map] Supabase failed: {e}", flush=True)
        return {}


CM_TO_IN = 1.0 / 2.54



def _build_planogram_from_supabase(store_id: str = "617533") -> Planogram:
    """Build a planogram from test_coffee_planogram_positions + test_coffee_product_map."""
    pos_rows = _supabase_get("test_coffee_planogram_positions", {
        "select": "*",
        "store_id": f"eq.{store_id}",
        "order": "eq_num_in_scene_group,shelf_number,on_shelf_position",
    })
    if not pos_rows:
        raise ValueError(f"No planogram positions for store {store_id}")

    size_map = _load_product_sizes()
    image_map = _build_image_map()

    products = []
    seen_ids = set()
    prod_width_in = {}
    for row in pos_rows:
        eid = row["external_product_id"]
        pid = f"CSV-{eid}"
        if pid not in seen_ids:
            seen_ids.add(pid)
            name = (row.get("external_product_name") or "").strip()
            brand = name.split(" ")[0] if name else "Unknown"
            dims = size_map.get(eid, {})
            w_in = round(float(dims.get("width_cm", 7.5)) * CM_TO_IN, 2)
            h_in = round(float(dims.get("height_cm", 20.0)) * CM_TO_IN, 2)
            prod_width_in[pid] = w_in
            prod_entry = {
                "id": pid, "upc": eid,
                "name": dims.get("tiny_name") or name or pid,
                "brand": brand, "manufacturer": "Demo CSV",
                "category": "Coffee", "subcategory": "Demo Import",
                "beer_type": "N/A", "package_type": "pack_box",
                "pack_size": 1, "unit_size_oz": 0.0,
                "width_in": w_in, "height_in": h_in, "depth_in": 4.0,
                "price": 0.0, "cost": 0.0, "abv": 0.0,
                "color_hex": _stable_color_from_text(pid),
                "weekly_units_sold": 0,
            }
            if eid in image_map:
                prod_entry["image_url"] = image_map[eid]
            products.append(prod_entry)
        else:
            dims = size_map.get(eid, {})
            w_in = round(float(dims.get("width_cm", 7.5)) * CM_TO_IN, 2)
            prod_width_in[pid] = w_in

    grouped = defaultdict(list)
    for row in pos_rows:
        key = (row["eq_num_in_scene_group"], row["shelf_number"])
        grouped[key].append(row)

    bay_numbers = sorted({r["eq_num_in_scene_group"] for r in pos_rows})
    max_shelf = max(r["shelf_number"] for r in pos_rows)
    bay_depth_in = 8.0

    bay_computed_widths = {}
    for bay_num in bay_numbers:
        max_w = 0.0
        for shelf_num in range(1, max_shelf + 1):
            shelf_w = sum(
                prod_width_in.get(f"CSV-{r['external_product_id']}", 3.0) * max(1, r.get("faces_width") or 1)
                for r in grouped.get((bay_num, shelf_num), [])
            )
            max_w = max(max_w, shelf_w)
        bay_computed_widths[bay_num] = round(max_w + 1.0, 1)

    shelf_max_height = {}
    for (_, shelf_num), shelf_rows in grouped.items():
        for r in shelf_rows:
            p = next((pp for pp in products if pp["id"] == f"CSV-{r['external_product_id']}"), None)
            h = p["height_in"] if p else 8.0
            shelf_max_height[shelf_num] = max(shelf_max_height.get(shelf_num, 0), h)

    bays = []
    for bay_num in bay_numbers:
        bay_width_in = bay_computed_widths[bay_num]
        shelf_defs = []
        y_cursor = 2.0
        for shelf_num in range(max_shelf, 0, -1):
            clearance = shelf_max_height.get(shelf_num, 8.0) + 1.5
            positions = []
            x_cursor = 0.0
            for r in grouped.get((bay_num, shelf_num), []):
                pid = f"CSV-{r['external_product_id']}"
                fw = max(1, r.get("faces_width") or 1)
                fh = max(1, r.get("faces_height") or 1)
                fd = max(1, r.get("faces_depth") or 1)
                positions.append({
                    "product_id": pid, "x_position": round(x_cursor, 2),
                    "facings_wide": fw, "facings_high": fh, "facings_deep": fd,
                    "orientation": "front",
                })
                x_cursor += prod_width_in.get(pid, 3.0) * fw
            shelf_defs.append({
                "shelf_number": shelf_num, "width_in": bay_width_in,
                "height_in": round(clearance, 1), "depth_in": bay_depth_in,
                "y_position": round(y_cursor, 1), "positions": positions,
                "shelf_type": "standard",
            })
            y_cursor += clearance
        bays.append({
            "bay_number": bay_num, "width_in": bay_width_in,
            "height_in": round(y_cursor + 2.0, 1), "depth_in": bay_depth_in,
            "shelves": shelf_defs, "glued_right": False,
        })

    return Planogram.from_dict({
        "id": "PLN-CSV-COFFEE-617533",
        "name": "Coffee Demo Planogram (Supabase)",
        "category": "Coffee", "store_type": "Demo Store",
        "effective_date": "2026-02-18",
        "metadata": {
            "version": "1.0", "generated_by": "Supabase Import",
            "placement_strategy": "test_coffee_planogram_positions",
        },
        "equipment": {
            "id": "EQ-CSV-001", "name": "Coffee Equipment",
            "equipment_type": "gondola", "bays": bays,
        },
        "products": products,
    })


# ── Recognition → Planogram converter ────────────────────────────────────────


def _build_planogram_from_recognition(shelf_width_cm: float = 125.0) -> Planogram:
    """Build a Planogram directly from recognition data.

    Each photo in recognition_photos becomes one bay.
    When store equipment data exists in Supabase and the recognition shelf
    count matches, stable equipment dimensions are used instead of the
    perspective-dependent recognition pixel calculations.
    """
    import statistics

    photo_names = _supabase_photo_list()
    if not photo_names:
        raise ValueError("No recognition photos found")

    # ── Fetch stable equipment config from Supabase ──────────────────────
    store_eq = _get_store_equipment()
    eq_cfg = None
    if store_eq:
        eq_cfg = {
            "num_shelves": store_eq.get("default_num_shelves", 7),
            "shelf_height_cm": float(store_eq.get("default_shelf_height_cm", 30.0)),
            "bay_width_cm": float(store_eq.get("bay_width_cm", 125.0)),
            "bay_height_cm": float(store_eq.get("bay_height_cm", 210.0)),
            "bay_depth_cm": float(store_eq.get("bay_depth_cm", 60.0)),
            "equipment_type": store_eq.get("equipment_type", "gondola"),
            "bays_config": store_eq.get("bays_config"),
        }
        shelf_width_cm = eq_cfg["bay_width_cm"]
        print(
            f"[equipment] Store equipment: {store_eq.get('num_bays', '?')} bays, "
            f"{eq_cfg['bay_width_cm']}cm wide, {eq_cfg['num_shelves']} shelves × "
            f"{eq_cfg['shelf_height_cm']}cm",
            flush=True,
        )
    else:
        print("[equipment] No store equipment in Supabase — using recognition dimensions", flush=True)

    no_bg_map = _build_no_bg_image_map()

    # Build recognition_id → product map sizes for stable dimensions
    raw_size_map = _load_product_sizes()
    product_size_by_recog_id: dict[str, dict] = {}
    for _code, info in raw_size_map.items():
        rid = info.get("recognition_id")
        if rid and info["width_cm"] > 0 and info["height_cm"] > 0:
            product_size_by_recog_id[rid] = info
    print(f"[realogram] Product map sizes loaded for {len(product_size_by_recog_id)} recognition IDs", flush=True)

    all_products_dict: dict[str, dict] = {}
    bays: list[dict] = []
    shelf_width_in = round(shelf_width_cm * CM_TO_IN, 2)

    for bay_idx, photo_name in enumerate(sorted(photo_names), start=1):
        shelf_rows = _supabase_shelves(photo_name)
        product_rows = _supabase_assortment_products(photo_name)

        shelf_lines = sorted(shelf_rows, key=lambda s: s.get("y1", 0))
        recog_num_shelves = len(shelf_lines)
        if recog_num_shelves == 0:
            continue

        # ── Per-bay equipment override (if bays_config provided) ─────────
        bay_eq_shelves = eq_cfg["num_shelves"] if eq_cfg else None
        bay_eq_shelf_h = eq_cfg["shelf_height_cm"] if eq_cfg else None
        bay_eq_depth = eq_cfg["bay_depth_cm"] if eq_cfg else None
        bay_eq_height = eq_cfg["bay_height_cm"] if eq_cfg else None
        if eq_cfg and eq_cfg["bays_config"] and isinstance(eq_cfg["bays_config"], list):
            if bay_idx <= len(eq_cfg["bays_config"]):
                bcfg = eq_cfg["bays_config"][bay_idx - 1]
                bay_eq_shelves = bcfg.get("num_shelves", bay_eq_shelves)
                bay_eq_shelf_h = float(bcfg.get("shelf_height_cm", bay_eq_shelf_h))

        use_equipment = bay_eq_shelves is not None and recog_num_shelves == bay_eq_shelves
        if use_equipment:
            print(
                f"[equipment] Bay {bay_idx}: recognition ({recog_num_shelves} shelves) "
                f"matches equipment — using stable dimensions",
                flush=True,
            )
        elif bay_eq_shelves is not None:
            print(
                f"[equipment] Bay {bay_idx}: recognition ({recog_num_shelves} shelves) "
                f"≠ equipment ({bay_eq_shelves}) — falling back to recognition dimensions",
                flush=True,
            )

        num_shelves = recog_num_shelves

        products_by_line: dict[int, list] = defaultdict(list)
        for p in product_rows:
            products_by_line[p.get("line", 0)].append(p)

        # ── Recognition-based scale (only needed when not using equipment) ──
        scale_by_line: dict[int, float] = {}
        global_scale = 0.06
        shelf_y_positions: list[float] = []
        if not use_equipment:
            for line_num, prods in products_by_line.items():
                scales = []
                for p in prods:
                    h_px = p.get("y2", 0) - p.get("y1", 0)
                    pm = product_size_by_recog_id.get(p.get("product_id", ""), {})
                    h_cm = pm.get("height_cm", 0) or p.get("facing_height_cm", 0)
                    if h_px > 20 and h_cm > 1:
                        scales.append(h_cm / h_px)
                if scales:
                    scale_by_line[line_num] = statistics.median(scales)

            all_scales = [s for s in scale_by_line.values()]
            global_scale = statistics.median(all_scales) if all_scales else 0.06

            all_lines = sorted(products_by_line.keys())
            for ln in all_lines:
                if ln not in scale_by_line:
                    scale_by_line[ln] = global_scale

            shelf_y_positions = [s.get("y1", 0) for s in shelf_lines]

        # ── Build shelves bottom-to-top ──────────────────────────────────
        shelf_defs: list[dict] = []
        y_cursor = 2.0

        for shelf_idx in range(num_shelves - 1, -1, -1):
            line_num = shelf_idx + 1

            if use_equipment:
                shelf_height_in = round(bay_eq_shelf_h * CM_TO_IN, 2)
            else:
                scale = scale_by_line.get(line_num, global_scale)
                if shelf_idx == 0:
                    top_products = products_by_line.get(line_num, [])
                    min_product_y = min((p["y1"] for p in top_products), default=0)
                    gap_px = shelf_y_positions[0] - min_product_y
                else:
                    gap_px = shelf_y_positions[shelf_idx] - shelf_y_positions[shelf_idx - 1]
                shelf_height_cm = scale * max(gap_px, 50)
                shelf_height_in = round(shelf_height_cm * CM_TO_IN, 2)

            # Place products on this shelf (always from recognition data)
            line_products = products_by_line.get(line_num, [])
            line_products = [p for p in line_products if not p.get("is_duplicated", False)]
            line_products.sort(key=lambda p: p.get("x1", 0))

            positions: list[dict] = []
            x_cursor_in = 0.0
            total_width_cm = 0.0

            for p in line_products:
                pid = p.get("product_id", "")
                if not pid:
                    continue

                map_dims = product_size_by_recog_id.get(pid, {})
                w_cm = map_dims.get("width_cm", 0) or p.get("facing_width_cm", 0) or p.get("group_width_cm", 0) or 7.5
                h_cm = map_dims.get("height_cm", 0) or p.get("facing_height_cm", 0) or 20.0
                w_in = round(w_cm * CM_TO_IN, 2)
                h_in = round(h_cm * CM_TO_IN, 2)

                facings_wide = max(1, p.get("group_count", 1))
                facing_w_in = w_in / facings_wide if facings_wide > 1 else w_in

                positions.append({
                    "product_id": pid,
                    "x_position": round(x_cursor_in, 2),
                    "facings_wide": facings_wide,
                    "facings_high": 1,
                    "facings_deep": 1,
                    "orientation": "front",
                })
                x_cursor_in += w_in
                total_width_cm += w_cm

                if pid not in all_products_dict:
                    prod_info = p
                    brand = prod_info.get("brand_name", "") or "Unknown"
                    no_bg_url = no_bg_map.get(pid, "")
                    all_products_dict[pid] = {
                        "id": pid,
                        "upc": prod_info.get("barcode", "") or pid,
                        "name": prod_info.get("display_name", "") or prod_info.get("art", "") or pid,
                        "brand": brand,
                        "manufacturer": prod_info.get("brand_owner_name", "") or "Recognition",
                        "category": prod_info.get("category_name", "") or "Coffee",
                        "subcategory": prod_info.get("macro_category_name", "") or "",
                        "beer_type": "N/A",
                        "package_type": "pack_box",
                        "pack_size": 1,
                        "unit_size_oz": 0.0,
                        "width_in": round(facing_w_in, 2),
                        "height_in": h_in,
                        "depth_in": 4.0,
                        "price": float(p.get("price", 0) or 0),
                        "cost": 0.0,
                        "abv": 0.0,
                        "color_hex": _stable_color_from_text(pid),
                        "weekly_units_sold": 0,
                        "image_url": no_bg_url or prod_info.get("miniature_url", ""),
                        "image_no_bg_url": no_bg_url,
                    }

            if total_width_cm > shelf_width_cm:
                print(
                    f"[recognition→plano] Bay {bay_idx} shelf {line_num}: "
                    f"overflow {total_width_cm:.1f} cm > {shelf_width_cm} cm",
                    flush=True,
                )

            depth_in = round(bay_eq_depth * CM_TO_IN, 2) if use_equipment and bay_eq_depth else 8.0
            shelf_defs.append({
                "shelf_number": num_shelves - shelf_idx,
                "width_in": shelf_width_in,
                "height_in": max(shelf_height_in, 4.0),
                "depth_in": depth_in,
                "y_position": round(y_cursor, 1),
                "positions": positions,
                "shelf_type": "standard",
            })
            y_cursor += max(shelf_height_in, 4.0)

        if use_equipment and bay_eq_height:
            bay_height_in = round(bay_eq_height * CM_TO_IN, 1)
        else:
            bay_height_in = round(y_cursor + 2.0, 1)
        bay_depth_in = round(bay_eq_depth * CM_TO_IN, 2) if use_equipment and bay_eq_depth else 8.0

        bays.append({
            "bay_number": bay_idx,
            "width_in": shelf_width_in,
            "height_in": bay_height_in,
            "depth_in": bay_depth_in,
            "shelves": shelf_defs,
            "glued_right": bay_idx < len(photo_names),
        })

    if not bays:
        raise ValueError("No bays could be built from recognition data")

    eq_type = eq_cfg["equipment_type"] if eq_cfg else "gondola"
    source_label = "Equipment + Recognition" if eq_cfg else "Recognition"

    return Planogram.from_dict({
        "id": "PLN-RECOGNITION-COFFEE",
        "name": f"Coffee Planogram (from {source_label})",
        "category": "Coffee",
        "store_type": "Recognition Import",
        "effective_date": "2026-03-11",
        "metadata": {
            "version": "1.0",
            "generated_by": "Recognition Converter",
            "shelf_width_cm": shelf_width_cm,
            "source_photos": sorted(photo_names),
            "equipment_source": "store_equipment" if eq_cfg else "recognition_only",
        },
        "equipment": {
            "id": "EQ-RECOG-001",
            "name": f"Coffee Equipment ({source_label})",
            "equipment_type": eq_type,
            "bays": bays,
        },
        "products": list(all_products_dict.values()),
    })


def _load_coffee_planogram(source: str = "auto"):
    """Load coffee planogram into current state.

    Args:
        source: "auto" (default priority chain), "recognition" (force recognition),
                "positions" (force positions table), "saved" (force saved planogram).

    Priority (auto): 1) Supabase planograms table (pre-built)
                     2) Build from recognition data
                     3) Build from Supabase positions table
    """
    global current_planogram, current_summary, current_compliance, current_decision_tree, current_equipment

    def _apply(plano, label):
        global current_planogram, current_summary, current_compliance, current_decision_tree, current_equipment
        current_planogram = plano
        current_summary = generate_summary(plano, len(plano.products))
        current_compliance = None
        current_decision_tree = None
        from dataclasses import asdict
        current_equipment = asdict(plano.equipment) if plano.equipment else None
        _save_state()
        print(f"[init] {label}", flush=True)

    if source in ("auto", "saved"):
        try:
            rows = _supabase_get("planograms", {
                "select": "planogram_data,summary_data",
                "planogram_id": "eq.PLN-CSV-COFFEE-617533",
                "limit": "1",
            })
            if rows:
                planogram_data = rows[0]["planogram_data"]
                image_map = _build_image_map()
                for prod in planogram_data.get("products", []):
                    upc = prod.get("upc", "")
                    if upc and upc in image_map:
                        prod["image_url"] = image_map[upc]
                _apply(Planogram.from_dict(planogram_data),
                       "Loaded coffee planogram from Supabase planograms table")
                return
        except Exception as e:
            print(f"[init] Supabase planograms load failed: {e}", flush=True)
            if source == "saved":
                raise

    if source in ("auto", "recognition"):
        try:
            _apply(_build_planogram_from_recognition(),
                   "Built coffee planogram from recognition data")
            return
        except Exception as e:
            print(f"[init] Recognition build failed: {e}", flush=True)
            if source == "recognition":
                raise

    if source in ("auto", "positions"):
        try:
            _apply(_build_planogram_from_supabase("617533"),
                   "Built coffee planogram from Supabase positions")
            return
        except Exception as e:
            print(f"[init] Supabase positions build failed: {e}", flush=True)
            if source == "positions":
                raise

    raise RuntimeError("Could not load coffee planogram from any source")


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
        "decision_tree": current_decision_tree.to_dict() if hasattr(current_decision_tree, 'to_dict') and current_decision_tree else current_decision_tree,
        "compliance": current_compliance.to_dict() if hasattr(current_compliance, 'to_dict') and current_compliance else current_compliance,
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
        "decision_tree": current_decision_tree.to_dict() if hasattr(current_decision_tree, 'to_dict') and current_decision_tree else current_decision_tree,
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
).strip()
SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpjY2lyb3V0YXJjcGt3cG55bnloIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3NzI3MjIzMTAsImV4cCI6MjA4ODI5ODMxMH0."
    "LFnJ8WoxlNhZ06MBQm-1mmJK4mtkBLZAPd4UoPtGrkE"
).strip()
_SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}


def _supabase_get(table: str, params: dict | None = None) -> list:
    """GET rows from a Supabase table via REST API."""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = http_requests.get(url, headers=_SUPABASE_HEADERS, params=params, timeout=5)
    resp.raise_for_status()
    return resp.json()


def _supabase_post(table: str, data: dict) -> dict:
    """POST a row to a Supabase table, returning the created row."""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {**_SUPABASE_HEADERS, "Content-Type": "application/json", "Prefer": "return=representation"}
    resp = http_requests.post(url, headers=headers, json=data, timeout=15)
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else data


def _supabase_patch(table: str, params: dict, data: dict) -> dict:
    """PATCH (update) rows matching params in a Supabase table."""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {**_SUPABASE_HEADERS, "Content-Type": "application/json", "Prefer": "return=representation"}
    resp = http_requests.patch(url, headers=headers, params=params, json=data, timeout=15)
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else data


# ── Supabase Store Equipment ──────────────────────────────────────────────────


def _get_store_equipment() -> dict | None:
    """Fetch the active store equipment config from Supabase.

    Returns the first active row from store_equipment, or None.
    """
    try:
        rows = _supabase_get("store_equipment", {
            "select": "*",
            "is_active": "eq.true",
            "order": "created_at.desc",
            "limit": "1",
        })
        if rows:
            return rows[0]
    except Exception as e:
        print(f"[supabase] Failed to fetch store equipment: {e}", flush=True)
    return None


def _save_store_equipment(data: dict) -> dict | None:
    """Create or update store equipment in Supabase."""
    try:
        existing = _get_store_equipment()
        if existing:
            return _supabase_patch(
                "store_equipment",
                {"id": f"eq.{existing['id']}"},
                {**data, "updated_at": "now()"},
            )
        else:
            return _supabase_post("store_equipment", data)
    except Exception as e:
        print(f"[supabase] Failed to save store equipment: {e}", flush=True)
    return None


# ── Supabase Planogram Persistence ────────────────────────────────────────────


def _save_planogram_to_supabase(
    planogram_obj, summary=None, decision_tree=None, compliance=None
) -> dict | None:
    """Save (upsert) current planogram to the planograms table.

    Uses planogram_id to decide insert vs update: if a row with matching
    planogram_id already exists, it is updated; otherwise a new row is created.
    """
    if planogram_obj is None:
        return None

    plano = planogram_obj.to_dict()
    eq = planogram_obj.equipment

    row = {
        "planogram_id": plano["id"],
        "name": plano["name"],
        "category": plano.get("category", ""),
        "store_type": plano.get("store_type", ""),
        "effective_date": plano.get("effective_date"),
        "total_products": planogram_obj.total_products(),
        "total_positions": planogram_obj.total_positions(),
        "total_facings": planogram_obj.total_facings(),
        "equipment_type": eq.equipment_type if eq else None,
        "num_bays": len(eq.bays) if eq else 0,
        "num_shelves": eq.total_shelves if eq else 0,
        "planogram_data": plano,
        "summary_data": summary,
        "decision_tree_data": decision_tree.to_dict() if hasattr(decision_tree, "to_dict") and decision_tree else decision_tree,
        "compliance_data": compliance.to_dict() if hasattr(compliance, "to_dict") and compliance else compliance,
    }

    from datetime import datetime, timezone
    row["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        existing = _supabase_get("planograms", {
            "select": "id",
            "planogram_id": f"eq.{plano['id']}",
            "order": "created_at.desc",
            "limit": "1",
        })
        if existing:
            result = _supabase_patch("planograms", {"id": f"eq.{existing[0]['id']}"}, row)
            print(f"[supabase] Updated planogram {plano['id']} (row {existing[0]['id']})", flush=True)
        else:
            result = _supabase_post("planograms", row)
            print(f"[supabase] Saved new planogram {plano['id']}", flush=True)
        return result
    except Exception as e:
        print(f"[supabase] Failed to save planogram: {e}", flush=True)
        return None


def _list_planograms_from_supabase(limit: int = 50) -> list:
    """List saved planograms (metadata only, no full data)."""
    try:
        return _supabase_get("planograms", {
            "select": "id,planogram_id,name,category,store_type,equipment_type,"
                      "num_bays,num_shelves,total_products,total_positions,"
                      "total_facings,created_at,updated_at",
            "order": "updated_at.desc",
            "limit": str(limit),
        })
    except Exception as e:
        print(f"[supabase] Failed to list planograms: {e}", flush=True)
        return []


def _load_planogram_from_supabase(row_id: int) -> dict | None:
    """Load a single planogram (full data) by row id."""
    try:
        rows = _supabase_get("planograms", {
            "select": "*",
            "id": f"eq.{row_id}",
            "limit": "1",
        })
        return rows[0] if rows else None
    except Exception as e:
        print(f"[supabase] Failed to load planogram {row_id}: {e}", flush=True)
        return None


def _delete_planogram_from_supabase(row_id: int) -> bool:
    """Delete a planogram row by id."""
    try:
        url = f"{SUPABASE_URL}/rest/v1/planograms?id=eq.{row_id}"
        resp = http_requests.delete(url, headers=_SUPABASE_HEADERS, timeout=10)
        resp.raise_for_status()
        print(f"[supabase] Deleted planogram row {row_id}", flush=True)
        return True
    except Exception as e:
        print(f"[supabase] Failed to delete planogram {row_id}: {e}", flush=True)
        return False


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


def _load_art_name_map() -> dict:
    """Build recognition_id → {tiny_name, name} mapping from Supabase product map."""
    try:
        rows = _supabase_get("test_coffee_product_map", {
            "select": "recognition_id,tiny_name,product_name",
        })
        mapping = {}
        for r in rows:
            rid = r.get("recognition_id")
            if rid:
                mapping[rid] = {
                    "tiny_name": r.get("tiny_name") or "",
                    "name": r.get("product_name") or "",
                }
        return mapping
    except Exception as e:
        print(f"[art_name_map] Supabase failed: {e}", flush=True)
        return {}


@app.route("/photo-viewer")
def photo_viewer():
    """Serve the interactive photo bounding-box viewer."""
    try:
        photos = _supabase_photo_list()
    except Exception:
        photos = []
    return render_template("photo_viewer.html", photos=photos)


@app.route("/api/debug/files")
def debug_files():
    """Debug endpoint to list files in Demo data folder."""
    demo_dir = os.path.join(os.path.dirname(__file__), "Demo data")
    try:
        files = sorted(os.listdir(demo_dir)) if os.path.exists(demo_dir) else []
        return jsonify({
            "demo_dir": demo_dir,
            "exists": os.path.exists(demo_dir),
            "files": files,
            "pwd": os.getcwd(),
            "__file__": __file__,
        })
    except Exception as e:
        return jsonify({"error": str(e), "pwd": os.getcwd()}), 500


@app.route("/api/photo-list")
def photo_list():
    """Return list of available photo names from Supabase."""
    try:
        names = _supabase_photo_list()
        return jsonify({"photos": names, "source": "supabase"})
    except Exception as e:
        return jsonify({"error": str(e), "source": "supabase"}), 502


@app.route("/api/photo-data/<photo_name>")
def photo_data(photo_name):
    """Return products + shelves JSON for a given photo from Supabase."""
    try:
        products = _supabase_assortment_products(photo_name)
        shelves = _supabase_shelves(photo_name)
        return jsonify({"products": products, "shelves": shelves, "source": "supabase"})
    except Exception as e:
        return jsonify({"error": str(e), "source": "supabase"}), 502


@app.route("/api/planogram-facings")
def planogram_facings():
    """Return planned planogram facings keyed by tiny_name.

    Reads from test_coffee_planogram_positions which has the actual store
    planogram layout with faces_width per position.
    Maps external_product_id → tiny_name via test_coffee_product_map.
    """
    size_map = _load_product_sizes()
    ext_to_tiny = {eid: info["tiny_name"] for eid, info in size_map.items() if info.get("tiny_name")}
    image_map = _build_image_map()

    try:
        rows = _supabase_get("test_coffee_planogram_positions", {
            "select": "external_product_id,external_product_name,faces_width,"
                      "shelf_number,eq_num_in_scene_group,on_shelf_position",
        })
    except Exception as e:
        print(f"[planogram-facings] Failed to load positions: {e}", flush=True)
        return jsonify({})

    facings = {}
    for r in rows:
        ext_id = r.get("external_product_id", "")
        tiny = ext_to_tiny.get(ext_id, "")
        if not tiny:
            continue

        fw = int(r.get("faces_width", 1) or 1)
        sz = size_map.get(ext_id, {})

        if tiny not in facings:
            facings[tiny] = {
                "facings_wide": 0,
                "positions": 0,
                "name": r.get("external_product_name", ""),
                "brand": "",
                "image_url": image_map.get(ext_id, ""),
                "width_cm": sz.get("width_cm", 0),
                "height_cm": sz.get("height_cm", 0),
            }
        facings[tiny]["facings_wide"] += fw
        facings[tiny]["positions"] += 1

    print(f"[planogram-facings] Loaded {len(facings)} products from planogram positions", flush=True)
    return jsonify(facings)


@app.route("/api/sales-data")
def sales_data():
    """Return avg weekly sale_amount per product from source_data_617533.

    Joins via recognition_product_id to map back to tiny_name so the photo
    viewer can look up sales by the same key used for planogram facings.
    """
    size_map = _load_product_sizes()
    ext_to_tiny = {eid: info["tiny_name"] for eid, info in size_map.items() if info.get("tiny_name")}

    try:
        rows = _supabase_get("source_data_617533", {
            "select": "product_code,product_name,recognition_product_id,"
                      "sale_amount,sale_qty,stock_qty,on_planogram,"
                      "face_width_planogram,in_target_assortment",
        })
    except Exception as e:
        print(f"[sales-data] Failed: {e}", flush=True)
        return jsonify({})

    from collections import defaultdict
    agg = defaultdict(lambda: {"amounts": [], "qty": [], "stock": [],
                               "product_name": "", "product_code": "",
                               "on_planogram": 0, "in_target_assortment": 0,
                               "face_width_planogram": 0})
    for r in rows:
        pid = r.get("recognition_product_id") or ""
        tiny = ext_to_tiny.get(r.get("product_code", ""), "")
        if not tiny and not pid:
            continue
        key = tiny or pid
        amt = r.get("sale_amount")
        qty = r.get("sale_qty")
        stk = r.get("stock_qty")
        if amt is not None:
            agg[key]["amounts"].append(float(amt))
        if qty is not None:
            agg[key]["qty"].append(float(qty))
        if stk is not None:
            agg[key]["stock"].append(float(stk))
        agg[key]["product_name"] = r.get("product_name", "")
        agg[key]["product_code"] = r.get("product_code", "")
        agg[key]["on_planogram"] = r.get("on_planogram", 0)
        agg[key]["in_target_assortment"] = r.get("in_target_assortment", 0)
        agg[key]["face_width_planogram"] = r.get("face_width_planogram") or 0

    result = {}
    for key, v in agg.items():
        result[key] = {
            "avg_sale_amount": round(sum(v["amounts"]) / len(v["amounts"]), 2) if v["amounts"] else 0,
            "total_sale_amount": round(sum(v["amounts"]), 2),
            "avg_sale_qty": round(sum(v["qty"]) / len(v["qty"]), 2) if v["qty"] else 0,
            "avg_stock_qty": round(sum(v["stock"]) / len(v["stock"]), 2) if v["stock"] else 0,
            "weeks": len(v["amounts"]),
            "product_name": v["product_name"],
            "product_code": v["product_code"],
            "on_planogram": v["on_planogram"],
            "in_target_assortment": v["in_target_assortment"],
            "face_width_planogram": v["face_width_planogram"],
        }
    return jsonify(result)


@app.route("/demo-images/<path:filename>")
def demo_images(filename):
    """Serve images from the Demo data folder."""
    from flask import send_from_directory
    demo_dir = os.path.join(os.path.dirname(__file__), "Demo data")
    return send_from_directory(demo_dir, filename)


@app.route("/api/load-demo-csv", methods=["POST"])
def load_demo_csv():
    """Load coffee planogram from Supabase."""
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


@app.route("/api/build-from-recognition", methods=["POST"])
def build_from_recognition():
    """Build a planogram directly from recognition photos + assortment data."""
    global current_planogram, current_summary, current_compliance, current_decision_tree, current_equipment
    try:
        data = request.json or {}
        shelf_width_cm = float(data.get("shelf_width_cm", 125.0))

        current_planogram = _build_planogram_from_recognition(shelf_width_cm)
        current_summary = generate_summary(current_planogram, len(current_planogram.products))
        current_compliance = None
        current_decision_tree = None
        from dataclasses import asdict
        current_equipment = asdict(current_planogram.equipment) if current_planogram.equipment else None
        _save_state()

        return jsonify({
            "status": "success",
            "source": "recognition",
            "planogram": current_planogram.to_dict(),
            "summary": current_summary,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "error": str(e),
        }), 400


# ── Store Equipment API Endpoints ─────────────────────────────────────────────


@app.route("/api/store-equipment", methods=["GET"])
def get_store_equipment():
    """Return the active store equipment configuration."""
    eq = _get_store_equipment()
    if eq:
        return jsonify({"status": "success", "equipment": eq})
    return jsonify({"status": "success", "equipment": None})


@app.route("/api/store-equipment", methods=["POST"])
def update_store_equipment():
    """Create or update store equipment configuration.

    Accepts JSON with any subset of:
      name, equipment_type, num_bays, bay_width_cm, bay_height_cm,
      bay_depth_cm, default_num_shelves, default_shelf_height_cm, bays_config
    """
    data = request.json or {}
    allowed = {
        "name", "equipment_type", "num_bays", "bay_width_cm",
        "bay_height_cm", "bay_depth_cm", "default_num_shelves",
        "default_shelf_height_cm", "bays_config", "is_active",
    }
    payload = {k: v for k, v in data.items() if k in allowed}
    if not payload:
        return jsonify({"status": "error", "error": "No valid fields provided"}), 400

    result = _save_store_equipment(payload)
    if result:
        return jsonify({"status": "success", "equipment": result})
    return jsonify({"status": "error", "error": "Failed to save equipment"}), 502


# ── Supabase Planogram API Endpoints ──────────────────────────────────────────


@app.route("/api/planogram/save", methods=["POST"])
def save_planogram_to_cloud():
    """Save the current planogram to Supabase.

    Optional JSON body: { "name": "custom name" }
    """
    global current_planogram

    if current_planogram is None:
        return jsonify({"status": "error", "error": "No planogram loaded"}), 400

    data = request.json or {}
    if "name" in data:
        current_planogram = Planogram.from_dict({
            **current_planogram.to_dict(),
            "name": data["name"],
        })

    result = _save_planogram_to_supabase(
        current_planogram, current_summary, current_decision_tree, current_compliance
    )
    if result:
        return jsonify({"status": "success", "saved": result})
    return jsonify({"status": "error", "error": "Failed to save to Supabase"}), 502


@app.route("/api/planogram/list")
def list_cloud_planograms():
    """List all planograms saved in Supabase (metadata only)."""
    limit = request.args.get("limit", 50, type=int)
    rows = _list_planograms_from_supabase(limit)
    return jsonify({"status": "success", "planograms": rows})


@app.route("/api/planogram/load/<int:row_id>", methods=["POST"])
def load_planogram_from_cloud(row_id):
    """Load a planogram from Supabase by row id and set it as current."""
    global current_planogram, current_summary, current_equipment
    global current_compliance, current_decision_tree

    row = _load_planogram_from_supabase(row_id)
    if not row:
        return jsonify({"status": "error", "error": f"Planogram {row_id} not found"}), 404

    plano_data = row["planogram_data"]
    current_planogram = Planogram.from_dict(plano_data)
    current_summary = row.get("summary_data") or generate_summary(current_planogram, _full_catalog_size())

    from dataclasses import asdict
    current_equipment = asdict(current_planogram.equipment) if current_planogram.equipment else None

    current_decision_tree = row.get("decision_tree_data")
    current_compliance = row.get("compliance_data")

    _save_state()

    return jsonify({
        "status": "success",
        "planogram": current_planogram.to_dict(),
        "summary": current_summary,
        "decision_tree": current_decision_tree.to_dict() if hasattr(current_decision_tree, 'to_dict') and current_decision_tree else current_decision_tree,
        "compliance": current_compliance.to_dict() if hasattr(current_compliance, 'to_dict') and current_compliance else current_compliance,
    })


@app.route("/api/planogram/delete/<int:row_id>", methods=["DELETE"])
def delete_cloud_planogram(row_id):
    """Delete a planogram from Supabase by row id."""
    ok = _delete_planogram_from_supabase(row_id)
    if ok:
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "error": "Failed to delete"}), 502


# ── Planogram Actions API ─────────────────────────────────────────────────────


@app.route("/api/actions")
def list_actions():
    """Return all planogram actions, ordered by avg_sale_amount desc."""
    try:
        # Check if Supabase is configured
        if not SUPABASE_URL or not SUPABASE_KEY:
            return jsonify({
                "status": "error",
                "error": "Supabase not configured. Set SUPABASE_URL and SUPABASE_KEY environment variables."
            }), 503
        
        limit = request.args.get("limit", 100, type=int)
        rows = _supabase_get("planogram_actions", {
            "select": "*",
            "order": "avg_sale_amount.desc.nullslast",
            "limit": str(min(limit, 500)),  # Cap at 500 for performance
        })
        return jsonify({"status": "success", "actions": rows})
    except Exception as e:
        print(f"[actions] Error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/toggle-duplicate", methods=["POST"])
def toggle_duplicate():
    """Toggle is_duplicated flag on a recognition_assortment row."""
    data = request.json or {}
    external_id = data.get("external_id")
    if not external_id:
        return jsonify({"status": "error", "error": "external_id required"}), 400
    try:
        rows = _supabase_get("recognition_assortment", {
            "select": "external_id,is_duplicated",
            "external_id": f"eq.{external_id}",
            "limit": "1",
        })
        if not rows:
            return jsonify({"status": "error", "error": "Row not found"}), 404
        current = rows[0].get("is_duplicated", False)
        new_val = not current
        _supabase_patch("recognition_assortment", {"external_id": f"eq.{external_id}"}, {"is_duplicated": new_val})
        return jsonify({"status": "success", "is_duplicated": new_val})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/actions/<int:action_id>", methods=["PATCH"])
def update_action(action_id):
    """Update an action (status, target_facings, notes, etc.)."""
    data = request.json
    allowed = {"status", "target_facings", "target_shelf", "target_position",
               "priority", "notes", "resolved_at"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        return jsonify({"status": "error", "error": "No valid fields to update"}), 400
    try:
        result = _supabase_patch("planogram_actions", {"id": f"eq.{action_id}"}, update)
        return jsonify({"status": "success", "action": result})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/suggest-placement")
def suggest_placement():
    """Find the best shelf to place a product based on category and brand similarity.

    Scores each (bay, shelf) by how many products on it share category_l2 / category_l1
    / brand with the target product.  Returns the top-scoring shelf.
    """
    target_cat_l2 = (request.args.get("category_l2") or "").strip()
    target_cat_l1 = (request.args.get("category_l1") or "").strip()
    target_brand = (request.args.get("brand") or "").strip()

    if not target_cat_l2 and not target_brand:
        return jsonify({"status": "error",
                        "error": "Provide at least category_l2 or brand"}), 400

    try:
        pos_rows = _supabase_get("test_coffee_planogram_positions", {
            "select": "external_product_id,eq_num_in_scene_group,shelf_number",
        })
    except Exception as e:
        return jsonify({"status": "error", "error": f"positions: {e}"}), 502

    try:
        pm_rows = _supabase_get("test_coffee_product_map", {
            "select": "product_code,category_l1,category_l2,product_name",
        })
    except Exception as e:
        return jsonify({"status": "error", "error": f"product_map: {e}"}), 502

    pm = {}
    for r in pm_rows:
        pc = r.get("product_code")
        if pc:
            name = r.get("product_name") or ""
            pm[pc] = {
                "category_l1": r.get("category_l1") or "",
                "category_l2": r.get("category_l2") or "",
                "brand": name.split(" ")[0] if name else "",
            }

    shelf_scores = defaultdict(lambda: {"score": 0, "cat_l2": 0, "cat_l1": 0, "brand": 0, "total": 0})
    for r in pos_rows:
        ext_id = r.get("external_product_id", "")
        bay = r.get("eq_num_in_scene_group")
        shelf = r.get("shelf_number")
        if bay is None or shelf is None:
            continue
        info = pm.get(ext_id, {})
        key = (bay, shelf)
        shelf_scores[key]["total"] += 1

        if target_cat_l2 and info.get("category_l2") == target_cat_l2:
            shelf_scores[key]["score"] += 3
            shelf_scores[key]["cat_l2"] += 1
        elif target_cat_l1 and info.get("category_l1") == target_cat_l1:
            shelf_scores[key]["score"] += 1
            shelf_scores[key]["cat_l1"] += 1

        if target_brand and info.get("brand", "").lower() == target_brand.lower():
            shelf_scores[key]["score"] += 2
            shelf_scores[key]["brand"] += 1

    if not shelf_scores:
        return jsonify({"status": "error", "error": "No shelf data available"}), 404

    best_key = max(shelf_scores, key=lambda k: shelf_scores[k]["score"])
    best = shelf_scores[best_key]

    reasons = []
    if best["cat_l2"]:
        reasons.append(f'{best["cat_l2"]} products share category "{target_cat_l2}"')
    if best["brand"]:
        reasons.append(f'{best["brand"]} products share brand "{target_brand}"')
    if best["cat_l1"] and not best["cat_l2"]:
        reasons.append(f'{best["cat_l1"]} products share L1 category')

    return jsonify({
        "status": "success",
        "bay_number": best_key[0],
        "shelf_number": best_key[1],
        "score": best["score"],
        "reason": "; ".join(reasons) if reasons else "Best available shelf",
    })


# Load persisted state on startup; fall back to generating from defaults
if not _load_saved_state():
    init_default_planogram()

if __name__ == "__main__":
    print("\n  Planogram Agent running at http://localhost:5001\n")
    app.run(debug=True, port=5001)
