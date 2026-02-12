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
    generate_planogram, generate_summary, process_user_input, load_products
)
from planogram_schema import Planogram
from gemini_agent import generate_planogram_with_ai

app = Flask(__name__, template_folder="templates", static_folder="static")

# Store the current planogram in memory
current_planogram = None
current_summary = None


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
