"""
Gemini AI Planogram Agent
=========================
Connects to Google Gemini 2.5 Flash to generate planogram layouts
from natural language user requests.

Sends: user request + product catalog + JSON schema instructions
Receives: complete planogram JSON ready for visualization
"""

import json
import os
import re
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------
_client = None

def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set in environment / .env")
        _client = genai.Client(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# JSON schema that Gemini must follow
# ---------------------------------------------------------------------------
PLANOGRAM_SCHEMA_DESCRIPTION = """
You must return a single JSON object with this exact structure:

{
  "id": "PLN-BEER-001",
  "name": "<planogram name>",
  "category": "Beer",
  "store_type": "<store type>",
  "effective_date": "<YYYY-MM-DD>",
  "metadata": {
    "version": "1.0",
    "generated_by": "Gemini Planogram Agent",
    "placement_strategy": "<brief description>"
  },
  "equipment": {
    "id": "EQ-001",
    "name": "<equipment name>",
    "equipment_type": "<gondola|cooler|endcap|wall_section|island>",
    "bays": [
      {
        "bay_number": 1,
        "width_in": <number>,
        "height_in": <number>,
        "depth_in": <number>,
        "shelves": [
          {
            "shelf_number": 1,
            "width_in": <same as bay width>,
            "height_in": <usable clearance in inches>,
            "depth_in": <number>,
            "y_position": <distance from floor in inches>,
            "shelf_type": "standard",
            "positions": [
              {
                "product_id": "<must match a product id from the catalog>",
                "x_position": <offset from left edge in inches>,
                "facings_wide": <int, typically 1-3>,
                "facings_high": 1,
                "facings_deep": 1,
                "orientation": "front"
              }
            ]
          }
        ]
      }
    ]
  },
  "products": [<include ONLY the products that are placed on shelves, copied from the catalog>]
}

CRITICAL RULES:
1. Every product_id in positions MUST exist in the products array.
2. The products array must contain ONLY products that appear in at least one position.
3. Products must physically fit: total width of positions on a shelf must not exceed shelf width_in.
4. Product height must not exceed shelf clearance (height_in).
5. x_position must be calculated correctly: each product's x_position = previous product's x_position + (previous product's width_in * facings_wide).
6. Shelves are numbered bottom-to-top. y_position increases from floor up.
7. Use the actual product dimensions from the catalog — do not invent dimensions.
8. Aim for 70-90% shelf fill rate. Leave some realistic gaps.
9. Group similar subcategories together on the same shelf when possible.
10. Place heavier/larger packs on lower shelves, premium items at eye level (shelves 3-4).
"""


def _build_prompt(user_request: str, products_json: list) -> str:
    """Build the full prompt for Gemini."""

    products_compact = json.dumps(products_json, indent=None, separators=(",", ":"))

    return f"""You are a retail planogram expert AI. Your job is to create optimal beer category planograms.

## USER REQUEST
{user_request}

## AVAILABLE PRODUCT CATALOG ({len(products_json)} products)
Each product has: id, name, brand, subcategory, beer_type, package_type, pack_size, unit_size_oz, width_in, height_in, depth_in, price, cost, abv, color_hex.

{products_compact}

## OUTPUT FORMAT
{PLANOGRAM_SCHEMA_DESCRIPTION}

## MERCHANDISING GUIDELINES
- Bottom shelves (1-2): Large/heavy packs (12-pack, 15-pack, 24-pack). These are bulky and heavy.
- Eye-level shelves (3-4): Craft beers, premium 6-packs — highest margin items get best visibility.
- Upper shelves (4-5): Import 6-packs, specialty items.
- Group products by subcategory (all Domestic Light Lager together, all Craft IPA together, etc.)
- Give top-selling domestic brands (Bud Light, Coors Light, Miller Lite) more facings (2-3).
- Ensure a mix of brands across the planogram for category variety.

Now generate the complete planogram JSON. Return ONLY valid JSON, no markdown fences, no explanation."""


def _extract_json(text: str) -> dict:
    """Extract JSON from Gemini response, handling common issues."""
    text = text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r'^```\w*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
        text = text.strip()

    # Fix trailing commas before } or ] (common Gemini issue)
    text = re.sub(r',\s*([}\]])', r'\1', text)

    # Try to parse
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Last resort: try to find the outermost JSON object
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            cleaned = re.sub(r',\s*([}\]])', r'\1', match.group(0))
            return json.loads(cleaned)
        raise e


def fill_products_with_ai(
    equipment_json: dict,
    products_json: list,
    rules_prompt: str,
) -> dict:
    """
    Call Gemini 2.5 Flash to fill an existing empty equipment with products.

    This is Step 2 of the two-step approach: equipment is already defined,
    Gemini only populates positions on each shelf.

    Args:
        equipment_json: Empty equipment dict (bays/shelves with no positions)
        products_json:  Full product catalog
        rules_prompt:   Pre-built prompt from product_logic.build_fill_prompt()

    Returns:
        dict with "equipment" (filled) and "products" (placed subset)
    """
    client = _get_client()

    print(f"[Gemini-Fill] Sending fill prompt ({len(rules_prompt)} chars) ...")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=rules_prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=65536,
            response_mime_type="application/json",
        ),
    )

    raw_text = response.text
    print(f"[Gemini-Fill] Received response ({len(raw_text)} chars)")

    result = _extract_json(raw_text)

    # Validate structure
    if "equipment" not in result:
        raise ValueError("Gemini response missing 'equipment' key")
    if "products" not in result:
        raise ValueError("Gemini response missing 'products' key")

    # Validate product references
    product_ids = {p["id"] for p in result["products"]}
    for bay in result["equipment"].get("bays", []):
        for shelf in bay.get("shelves", []):
            for pos in shelf.get("positions", []):
                if pos["product_id"] not in product_ids:
                    raise ValueError(
                        f"Position references unknown product_id: {pos['product_id']}"
                    )

    return result


def generate_planogram_with_ai(user_request: str, products_json: list) -> dict:
    """
    Call Gemini 2.5 Flash to generate a planogram.

    Args:
        user_request: Natural language description of desired planogram
        products_json: List of product dicts from the catalog

    Returns:
        dict: Complete planogram data matching our schema

    Raises:
        Exception: If Gemini call fails or response is invalid JSON
    """
    client = _get_client()
    prompt = _build_prompt(user_request, products_json)

    print(f"[Gemini] Sending prompt ({len(prompt)} chars) ...")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=16000,
            response_mime_type="application/json",
        ),
    )

    raw_text = response.text
    print(f"[Gemini] Received response ({len(raw_text)} chars)")

    # Parse JSON
    planogram_data = _extract_json(raw_text)

    # Validate basic structure
    _validate_planogram(planogram_data)

    return planogram_data


def _validate_planogram(data: dict):
    """Basic validation of the returned planogram structure."""
    required_keys = ["id", "name", "equipment", "products"]
    for key in required_keys:
        if key not in data:
            raise ValueError(f"Missing required key: {key}")

    if not data["equipment"].get("bays"):
        raise ValueError("Equipment must have at least one bay")

    # Build set of product IDs in catalog
    product_ids = {p["id"] for p in data["products"]}

    # Validate all positions reference valid products
    for bay in data["equipment"]["bays"]:
        for shelf in bay.get("shelves", []):
            for pos in shelf.get("positions", []):
                if pos["product_id"] not in product_ids:
                    raise ValueError(
                        f"Position references unknown product_id: {pos['product_id']}"
                    )
