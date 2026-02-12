"""
Planogram Agent — Web Application
==================================
Flask-based web app that serves the planogram visualizer.
Provides API endpoints for generating and viewing planograms.
"""

from flask import Flask, render_template, jsonify, request
import json
import os

from planogram_generator import (
    generate_planogram, generate_summary, process_user_input, load_products
)

app = Flask(__name__, template_folder="templates", static_folder="static")

# Store the current planogram in memory
current_planogram = None
current_summary = None


def init_default_planogram():
    """Initialize with default beer planogram."""
    global current_planogram, current_summary
    current_planogram = generate_planogram()
    current_summary = generate_summary(current_planogram)


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
    """Generate a new planogram from user input."""
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
        "status": "success"
    })


@app.route("/api/products", methods=["GET"])
def get_products():
    """Return all available products."""
    products_file = os.path.join(os.path.dirname(__file__), "data", "beer_products.json")
    with open(products_file, 'r') as f:
        products = json.load(f)
    return jsonify(products)


if __name__ == "__main__":
    init_default_planogram()
    print("\n  Planogram Agent running at http://localhost:5001\n")
    app.run(debug=True, port=5001)
