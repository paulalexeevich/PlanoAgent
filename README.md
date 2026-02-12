# Planogram Agent — Beer Category Prototype

A prototype planogram generation and visualization tool for the beer category.

## What It Does

1. **Accepts input** — JSON configuration or natural language text describing equipment layout
2. **Generates planogram** — Automatically places 50 real beer products onto shelves using intelligent placement logic
3. **Visualizes** — Interactive web-based planogram viewer with hover tooltips, scale control, and summary dashboard

## Data Model (Based on Industry Standards)

Follows the Blue Yonder Space Planning / GoPlanogram hierarchy:

```
Planogram
├── Equipment (gondola, cooler, endcap, etc.)
│   └── Bays (segments)
│       └── Shelves (fixtures)
│           └── Positions (product placements)
│               ├── product_id
│               ├── x_position
│               ├── facings_wide/high/deep
│               └── orientation
└── Products (catalog)
    ├── id, upc, name, brand
    ├── dimensions (width, height, depth in inches)
    ├── package_type, pack_size, unit_size_oz
    ├── price, cost, abv
    └── color_hex (for visualization)
```

## Product Catalog

50 real beer products across categories:
- **Domestic Light Lager** — Bud Light, Coors Light, Miller Lite, Michelob Ultra, Natural Light, Busch Light
- **Domestic Lager** — Budweiser, Yuengling, PBR, Miller High Life
- **Import Lager** — Corona, Modelo, Heineken, Stella Artois, Dos Equis, Tecate, Pacifico, Sapporo, Peroni
- **Import Stout** — Guinness
- **Craft IPA** — Sierra Nevada, Lagunitas, Dogfish Head, Stone, Voodoo Ranger, Goose Island, Bell's, Founders
- **Craft Wheat/Ale** — Blue Moon, Sam Adams, New Belgium Fat Tire, Kona Big Wave, Shiner Bock
- **Hard Cider** — Angry Orchard

## Quick Start

```bash
pip install -r requirements.txt
python app.py
# Open http://localhost:5001
```

## Input Examples

**Natural language:**
```
Create 4-bay cooler with 6 shelves, 48 inches wide
```

**JSON config:**
```json
{
  "equipment_type": "gondola",
  "num_bays": 3,
  "num_shelves": 5,
  "bay_width": 48,
  "bay_height": 72
}
```

## Placement Strategy

- Bottom shelves → Large/heavy packs (12+, 24-packs)
- Eye level → Craft & premium 6-packs (highest margin)
- Upper shelves → Import 6-packs and specialty
- Products grouped by subcategory for visual merchandising

## Tech Stack

- **Backend:** Python + Flask
- **Frontend:** Vanilla HTML/CSS/JS (no build step)
- **Data:** JSON files for product catalog and planogram output
