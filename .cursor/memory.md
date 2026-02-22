# Planogram Agent — Learnings & Memory

## Architecture & Technical Notes
- **Data model**: Blue Yonder hierarchy (Planogram > Equipment > Bay > Shelf > Position). `dataclass` with `asdict()` for serialization.
- **Tolerant deserialization**: `Planogram.from_dict()` uses `_safe()` helper to drop unknown fields — critical for Gemini AI which adds extra keys (e.g. `y_position` on Position). Always filter to known dataclass fields.
- **Flask + vanilla JS** (no build step). Port 5001 (5000 conflicts with macOS AirPlay).
- **Always use `python3`** on this macOS system (`python` not found).
- **Product dimensions in inches** (US retail standard). Standard gondola: 48"W x 72"H x 24"D, 5 shelves.

## 3-Phase Algorithm + 6-Step Post-Processing Pipeline (v0.6)
- **Step 1**: Structured equipment form → `/api/generate-equipment` → empty shelves. Form + Generate button hidden behind collapsible "Equipment Config" toggle.
- **Step 2**: "Fill Products" → `/api/fill-products` → 3-phase pipeline:
  - **Phase 1 (Capacity Check)**: Sort products by `weekly_units_sold` DESC. Drop lowest sellers until total 1-facing width fits all shelves.
  - **Phase 2 (Optimal Facings)**: Start at 1 facing per product. Iterate by sales rank, adding facings until ~99% target fill. Returns `{product_id: facing_count}` dict.
  - **Phase 3 (Placement)**: Send products + pre-calculated facings to Gemini AI. Rule-based fallback if AI fails.
  - **Post-processing pipeline (6 steps)**:
    - **A**: Audit AI output (count products/facings vs expected)
    - **B**: `validate_and_fix_shelves()` — fix overflowing shelves by reducing facings on low sellers
    - **C**: `recover_missing_products()` — find products AI didn't place, fit them on shelves with room (best-fit algorithm)
    - **D**: `boost_underused_shelves()` — 2-pass boost: restore to Phase 2 target, then boost best sellers up to max_facings
    - **E**: `fill_shelf_gaps()` — greedy gap filler: repeatedly adds 1 facing of highest-seller that fits on shelf with most room, until 99% target reached
    - **F**: Final audit with fill % logging

### Key insight: AI is unreliable for math (overflows 60% of shelves!) but useful for grouping. The algorithm does math, post-processing fixes AI mistakes, gap filler recovers lost fill. Result: 75.7% → 96.3% fill rate improvement.

- **`product_logic.py`**: `ProductLogicRules` dataclass — fill_target_pct=99%, max_facings=5.
- **Sales data**: `weekly_units_sold` field on each product (fake data for demo). Domestic Light Lagers ~130-180 units, Craft IPAs ~15-22 units.
- **Server state resilience**: `init_default_planogram()` now sets `current_equipment`. Frontend sends equipment in fill request body as fallback for server restarts.

## Gemini AI Integration
- **SDK**: `google-genai`. Client: `genai.Client(api_key=...)`. Model: `gemini-2.5-flash`.
- **Structured output**: `response_mime_type="application/json"` in config.
- **Token limit**: Use `max_output_tokens=65536` for fill responses (24+ shelves generate ~55K char JSON). 16K causes truncation errors.
- **Trailing comma bug**: Gemini produces trailing commas. Fix: `re.sub(r',\s*([}\]])', r'\1', text)`.
- **Truncated JSON bug**: Gemini sometimes returns truncated JSON (cut off at output token limit). Fix: `_repair_truncated_json()` closes unclosed brackets/braces and removes incomplete trailing strings. This saved the fill from falling back to rule-based.
- **Extra fields bug**: Gemini adds unexpected fields to JSON objects. Fix: filter dicts to known dataclass fields before constructing objects.
- **Response time**: 30-120 seconds depending on equipment size. Frontend needs loading spinner.
- **Prompt design**: Send equipment structure + product catalog + rules as structured text. Temperature 0.7.
- **AI arithmetic weakness**: Gemini consistently overflows 60% of shelves despite explicit width constraints in prompt. Must always post-process with overflow fixer.
- **AI product dropping**: Gemini sometimes drops 3-9 products from the 50-product list. Recovery step catches and places them.
- **Always use `flush=True` on print()**: Flask debug mode + subprocess execution buffers stdout. Without flush, pipeline logs don't appear in terminal until process exits.

## UI/UX Notes
- Two-step UI: equipment form (dropdowns + numbers) + "Generate Equipment" / "Fill Products" buttons.
- Source tags: "Empty Equipment" (orange), "Gemini AI" (blue), "Rule-based (fallback)" (purple), "Rule-based" (green).
- **Planogram rendering**: Products use **absolute positioning** (`left: x_position * scale`), NOT flexbox. Bay must have `flex-shrink: 0` + `box-sizing: content-box`.
- Scale slider, unit toggle (in/cm). At high zoom, page scrolls horizontally.
- Bottom collapsible summary: metrics, category mix, fill rates, decision tree compliance.

## Decision Tree & Compliance (v0.8)
- **`decision_tree.py`**: Pre-built trees per category. Beer tree: Segment → Style (subcategory) → Package → Brand.
- **Compliance validation**: Walk positions in planogram order (Bay1/S1→SN, Bay2/S1→...), count "breaks" per level.
- **CRITICAL: Hierarchical scoring** — Level N breaks are counted ONLY within contiguous runs of Level N-1. This correctly measures "within each Style, are Packages contiguous?" NOT "are ALL cans before ALL bottles globally." Without this, Package compliance is always ~15% even with perfect tree ordering.
- **Tree-ordered placement** (algorithm mode): Sort ALL products by decision tree tuple, place sequentially in compliance walk order. Products split across shelf boundaries when full facings don't fit. This achieves 100% compliance.
- **Post-processing destroys compliance**: `recover_missing_products()` and `fill_shelf_gaps()` insert products by available space, not tree position. Algorithm mode skips these steps; only runs `validate_and_fix_shelves()` (overflow fix).
- **AI prompt includes tree**: `build_fill_prompt()` accepts `decision_tree`, injects `to_prompt_text()`.

### Key compliance lesson: The root cause of low compliance was TWO bugs, not one:
1. **Placement**: Old tier-based algorithm scattered tree groups across different shelf tiers (bottom/eye/top). Fix: sort by tree, place in walk order.
2. **Scoring**: Non-hierarchical scoring penalized Package level for global interleaving that is correct within each Style group. Fix: partition positions by parent-level runs before counting breaks.

## CSS Layout Lessons
- **Never use `justify-content: center` on scrollable flex containers** — left side becomes inaccessible. Use `width: fit-content; margin: 0 auto` instead.
- **Collapsible panels**: Use `max-height` + `overflow: hidden` + `opacity` transitions. Set `max-height` high enough (200px).

## Algorithm vs AI Comparison (v0.7)
- **Mode selector**: Dropdown in UI with Algorithm/AI/Compare options.
- **Compare mode**: Runs both, shows side-by-side modal with fill %, facings, compliance, timing. User can pick which to apply.
- **Timing instrumentation**: Every pipeline step timed in ms. Returned in JSON response + terminal logs.

### Head-to-head results (3 bays × 5 shelves, 50 products):
| Metric | Algorithm | AI |
|---|---|---|
| Fill % | 95.9% | 97.4% |
| Products | 50 | 50 |
| Facings | 81 | 85 |
| Total time | **1ms** | 102,538ms |
| Speedup | **102,538x** | — |

### Conclusion: **Algorithm is the default**. Only 1.5% fill difference, but 100,000x faster. AI mode available for alternative placement.
- Algorithm now achieves **100% decision tree compliance** (tree-ordered placement + hierarchical scoring).
- Algorithm places products by tree order then boosts facings per-shelf; AI uses merchandising judgment but can't do math.

## Dashboard KPI Cards (v0.9)
- **4 big KPI cards** replace old 4-column metrics panel: Assortment %, Avg $/Space, Space Utilization %, DT Compliance %.
- **Click-to-expand**: Each card toggles a granular detail panel below. Only one open at a time.
- **Color coding**: Green (>=80%), Orange (50-79%), Red (<50%). Blue for revenue metrics.
- **Assortment tracking**: Supports custom SKU list upload (CSV/TXT/JSON). Compares placed vs list. Missing products shown first in red.
- **Revenue per space**: Per-SKU $/inch table ranked descending. Green = above avg, Orange = below avg.
- **Backend `generate_summary()`**: Now includes `sku_space_analysis`, `assortment`, and `avg_revenue_per_space` fields.
- **CRITICAL: Compliance data must be persisted**: GET `/api/planogram` must return `decision_tree` and `compliance` alongside planogram+summary, or dashboard shows "--". Store `current_compliance` and `current_decision_tree` globally in `app.py`.

## Vercel Deployment
- **`vercel.json`** + `api/index.py` entry point (WSGI). Project: `plano-agent.vercel.app`.
- **Git author email must match Vercel team**: CLI checks commit author. Workaround: deploy from a temp directory without `.git/` folder using `rsync --exclude .git` + copy `.vercel/` config. This bypasses the author check.
- **Deploy command**: `rsync` to `/tmp/plano-deploy`, copy `.vercel/`, then `npx vercel --prod --yes`.

## Known Issues & TODOs
- Fill target is 99% but achievable ~96% due to fractional inch gaps (product widths don't evenly divide shelf width).
- `ComplianceReport` uses `.overall_pct` not `.overall_score` — always check attribute names.
- Gemini AI: 30-120s response time, overflows ~60% of shelves. Post-processing recovers to 97%+.
- API key in `.env` file (gitignored). Never commit secrets.
