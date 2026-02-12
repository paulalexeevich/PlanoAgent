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
    ProductLogicRules, fill_equipment_rule_based, build_fill_prompt
)

app = Flask(__name__, template_folder="templates", static_folder="static")

# Store the current state in memory
current_planogram = None
current_summary = None
current_equipment = None      # Empty equipment dict (Step 1 result)
current_rules = None          # ProductLogicRules (for Step 2)


def init_default_planogram():
    """Initialize with default beer planogram."""
    global current_planogram, current_summary
    current_planogram = generate_planogram()
    current_summary = generate_summary(current_planogram)


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


@app.route("/api/fill-products", methods=["POST"])
def fill_products():
    """
    Step 2: Fill the current empty equipment with products using Product Logic.

    Uses Gemini AI first; on failure falls back to rule-based algorithm.

    Expects optional JSON body with rule overrides:
      fill_target_pct, max_facings, group_by, top_seller_brands, etc.
    """
    global current_planogram, current_summary, current_equipment

    if current_equipment is None:
        return jsonify({
            "status": "error",
            "error": "No equipment generated yet. Run Step 1 first.",
        }), 400

    data = request.json or {}

    # Build rules (apply any overrides from request)
    rules = ProductLogicRules(
        fill_target_pct=float(data.get("fill_target_pct", 85)),
        max_facings=int(data.get("max_facings", 3)),
        group_by=data.get("group_by", "subcategory"),
    )

    products_json = _load_products_json()

    # Deep copy equipment so we don't mutate stored state for retries
    import copy
    equipment_copy = copy.deepcopy(current_equipment)

    source = "gemini_ai"
    try:
        # Primary: Gemini AI
        prompt = build_fill_prompt(equipment_copy, products_json, rules)
        result = fill_products_with_ai(equipment_copy, products_json, prompt)
        filled_equipment = result["equipment"]
        placed_products = result["products"]
    except Exception as ai_err:
        # Fallback: rule-based
        print(f"[Fill] AI failed ({ai_err}), falling back to rule-based")
        traceback.print_exc()
        equipment_copy = copy.deepcopy(current_equipment)
        result = fill_equipment_rule_based(equipment_copy, products_json, rules)
        filled_equipment = result["equipment"]
        placed_products = result["products"]
        source = "rule_based_fallback"

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
            "placement_strategy": f"fill_target={rules.fill_target_pct}%, group_by={rules.group_by}",
        },
        "equipment": filled_equipment,
        "products": placed_products,
    }

    current_planogram = Planogram.from_dict(planogram_data)
    current_summary = generate_summary(current_planogram)

    return jsonify({
        "planogram": current_planogram.to_dict(),
        "summary": current_summary,
        "status": "success",
        "source": source,
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


@app.route("/api/products", methods=["GET"])
def get_products():
    """Return all available products."""
    return jsonify(_load_products_json())


if __name__ == "__main__":
    init_default_planogram()
    print("\n  Planogram Agent running at http://localhost:5001\n")
    app.run(debug=True, port=5001)
