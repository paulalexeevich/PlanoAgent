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

from dotenv import load_dotenv
load_dotenv()

from planogram_generator import (
    generate_planogram, generate_summary, process_user_input,
    load_products, create_default_equipment
)
from planogram_schema import Planogram, Equipment
from gemini_agent import generate_planogram_with_ai, fill_products_with_ai
from product_logic import (
    ProductLogicRules, fill_equipment_rule_based, build_fill_prompt,
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


def init_default_planogram():
    """Initialize with default beer planogram."""
    global current_planogram, current_summary, current_equipment
    current_planogram = generate_planogram()
    current_summary = generate_summary(current_planogram)
    # Also store the equipment dict so Fill Products works without Step 1
    from dataclasses import asdict
    current_equipment = asdict(current_planogram.equipment)


def _load_products_json() -> list:
    """Load raw product dicts from JSON file."""
    products_file = os.path.join(os.path.dirname(__file__), "data", "beer_products.json")
    with open(products_file, 'r') as f:
        return json.load(f)


@app.route("/")
def index():
    """Serve the main visualization page."""
    return render_template("index.html")


@app.route("/api/planogram", methods=["GET"])
def get_planogram():
    """Return current planogram data as JSON."""
    global current_planogram, current_summary
    if current_planogram is None:
        init_default_planogram()
    return jsonify({
        "planogram": current_planogram.to_dict(),
        "summary": current_summary
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
    current_summary = generate_summary(current_planogram)

    return jsonify({
        "planogram": current_planogram.to_dict(),
        "summary": current_summary,
        "status": "success",
        "source": "rule_based"
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

    # Build equipment config from form fields
    config = {
        "equipment_type": data.get("equipment_type", "gondola"),
        "num_bays":       int(data.get("num_bays", 3)),
        "num_shelves":    int(data.get("num_shelves", 5)),
        "bay_width":      float(data.get("bay_width", 48.0)),
        "bay_height":     float(data.get("bay_height", 72.0)),
        "bay_depth":      float(data.get("bay_depth", 24.0)),
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
    current_summary = generate_summary(current_planogram)

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
    """Count products, facings, and used width from equipment dict."""
    placed_ids = set()
    total_facings = 0
    used_width = 0.0
    for bay in filled_equipment.get("bays", []):
        for shelf in bay.get("shelves", []):
            for pos in shelf.get("positions", []):
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
        t_pp = _time.time()
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
    current_summary = generate_summary(current_planogram)

    # Validate decision tree compliance
    compliance = None
    if decision_tree:
        compliance = validate_compliance(planogram_data, decision_tree)

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
        current_summary = generate_summary(current_planogram)

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
    """Return all available products."""
    return jsonify(_load_products_json())


if __name__ == "__main__":
    init_default_planogram()
    print("\n  Planogram Agent running at http://localhost:5001\n")
    app.run(debug=True, port=5001)
