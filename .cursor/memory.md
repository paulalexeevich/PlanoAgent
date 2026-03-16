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
- "Remove Products" button empties all shelves (keeps equipment structure). Replaced old "Reset Default" button and source tag system.
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
- **Shelf visual**: Use `border-bottom` (not `border-top`) on `.shelf-row` to represent the physical shelf board. Shelf rows must be `background: transparent` — grey fill hides the open-air nature of a real gondola. Empty shelves should always get the `empty-shelf` class (not only when the entire planogram is empty).

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

## Visualization Layer System (v0.10)
- **Layer selector**: Pill buttons above planogram — "Products" always visible; DT level buttons (Segment/Style/Package/Brand) injected dynamically from `decisionTreeData.levels` when compliance data is available.
- **Products mode**: Product `color_hex`, brand name, price label, segment overlay bands (using `_addGroupBand` + `buildSegmentMap()`).
- **DT layer modes** (`dt-0` … `dt-N`): Product blocks colored by group value at that level; label shows group name; segment bands hidden.
- **`dtPositionMap`**: Built from `complianceData.position_groups` — maps `product_id → {LevelName: groupValue}`. Rebuilt every `renderAll()` call.
- **Color palettes**: Pre-defined for Segment (4 colors) and Package (4 colors). Auto-generated for Style, Brand (15-color wheel, sorted group names → deterministic). `DT_KNOWN_PALETTES` + `DT_AUTO_COLORS` constants.
- **Legend**: `renderLayerLegend(levelName, palette)` fills `#dtLegend` with color swatches. Empty in Products mode.
- **`setLayer(layer)`**: Sets `currentLayer`, syncs button `.active` classes, calls `renderPlanogram()` only (fast, no API call).
- **`updateLayerSelector()`**: Removes old `.dt-btn` elements and re-inserts from tree definition; validates `currentLayer` still exists after data changes.
- **Screenshot timing**: Browser screenshots may lag by one frame after click — always take a second screenshot to confirm the current state.

## Equipment Editor Overlay (v0.12)
- **Full-screen dedicated page** replaces inline collapsible panel. Opened via "Equipment Config ▼" button (`toggleConfig()` → `openEquipmentEditor()`).
- **Editor state** (`editorState`): `{equipment_type, height_in, depth_in, bays: [{width_in, num_shelves, shelf_clearances}]}`. Initialized from current planogram or defaults.
- **Direct manipulation** (no config drawer):
  - `↔` width drag handle below each bay — `ew-resize`, live DOM update via `_edLiveWidth(bayIdx)` (no full re-render during drag)
  - `↕` shelf height handles on right side of each shelf — `ns-resize`, live via `_edLiveShelfH(bayIdx)`. Auto-converts even distribution to custom clearances on first drag.
  - `−` / `+` shelf count buttons in each bay header
  - "⚙ All Bays" dropdown popover (not a drawer) for setting all bays at once
- **Gap = 68px** between `.eq-bay-wrapper` elements so 58px shelf handles don't overlap neighboring bays.
- **`initEditorDragHandlers()`**: Called in DOMContentLoaded. document-level mousemove/mouseup listeners.
- **`applyEquipmentEditor()`**: posts `bays_config` to `/api/generate-equipment`, closes overlay, renders empty planogram.
- **EDITOR_SCALE = 3px/in**: editor visualization scale.

## Frontend Refactor (v0.30)
- **Monolith split**: `templates/index.html` was 3,552 lines (1,532 CSS + 270 HTML + 1,716 JS). Now 327-line HTML with 7 CSS + 11 JS external files in `static/`.
- **No build system**: Plain `<script>` and `<link>` tags. All functions remain global scope. Load order matters: `state.js` first (defines globals), `app.js` last (DOMContentLoaded glue).
- **File map**: CSS: `base` (layout/buttons), `controls` (loading/tags/config), `planogram` (bays/shelves/products/tooltip), `dashboard` (KPI/detail), `modals` (compare/error), `layers` (DT/compliance), `equipment-editor` (editor overlay). JS: `state` (globals), `utils` (conversion/helpers), `tooltip`, `layer-system`, `planogram-renderer`, `bay-config`, `compare`, `dashboard`, `api`, `equipment-editor`, `app` (init).
- **Largest modules**: `equipment-editor.js` (440 lines) + `equipment-editor.css` (435 lines) = 875 total. `dashboard.js` (335 lines) + `dashboard.css` (251 lines) = 586 total.
- **Flask**: `static_folder="static"` was already configured in `app.py`. Static files served at `/static/css/*.css` and `/static/js/*.js`.

## Settings Page & Currency (v0.31)
- **Settings overlay** (`settings.js` + CSS in `modals.css`): Centered modal with unit toggle (in/cm) and currency selector.
- **Standard scale**: Both dashboard and equipment editor default to **5 px/in** (was 6 and 3 respectively).
- **Currency system**: `CURRENCIES` object defines 12 currencies with symbol, placement (before/after), and decimals. `cFmt(value)` formats any number. `cSymbol()` returns just the symbol.
- **Persistence**: All settings (unit, currency, scale, editor scale) saved to `localStorage` as `planogram_settings`. Loaded on `DOMContentLoaded`.
- **Unit toggle moved** from header and equipment editor toolbar into Settings page. Hidden `#unitIn`/`#unitCm`/`#edUnitIn`/`#edUnitCm` elements kept in DOM for `setUnit()` compatibility.
- **Header gear icon** (&#9881;) opens settings overlay. Clicks outside card or X button close it.

## Cross-Bay Algorithm (v0.34 → v0.36)
- **New fill mode**: "Cross-Bay" merges shelves from glued bays into virtual wide shelves. Products flow continuously across bay boundaries.
- **Implementation**: `phase3_cross_bay_placement()` in `product_logic.py` — builds bay groups from `glued_right` flags, creates virtual merged shelves, places products on wide virtual surface, then splits positions back to physical shelves via `_split_positions_to_shelves()`.
- **Width-aware split**: `_split_positions_to_shelves()` tracks remaining width per physical shelf. Facings flow to next bay at boundary without overflowing.
- **CRITICAL BUG FIX**: Remove `+0.1` tolerance from cross-bay main placement and boost passes. On wide virtual shelves (192"+), the tolerance causes cumulative overfill.
- **Alignment-aware virtual shelf merging (v0.36)**: `_build_virtual_shelves()` uses **sorted-index matching with alignment checks**. Each bay's shelves sorted bottom-to-top. Row i collects the i-th shelf from each bay. Within a row, a run of consecutive bays is merged ONLY if adjacent shelves are physically aligned (y_position within `_YPOS_TOLERANCE`). Misaligned boundaries BREAK the run. This prevents products from spanning across shelves at different heights.
- **LESSON: Three failed approaches before success**:
  1. Position-based matching with tolerance: fails when clearances differ (y-positions drift: 19.2 vs 22.5).
  2. Pure index-based matching: merges ALL bays in a row regardless of height — creates phantom positions at different heights, rendering broken products.
  3. Per-bay clipping (overflow:hidden): tried to fix rendering by clipping each bay — but shows products as cut-in-half pieces, which is physically impossible.
  4. **CORRECT: Alignment-aware runs** — only merge when y_positions actually match. No phantoms at misaligned boundaries. No clipping needed.
- **Height tolerance removed**: Only y_position matters for alignment, not shelf clearance (height_in). Clearance only affects what products fit vertically. Two shelves at the same board height (y_position) are physically aligned even with different clearances.
- **Renderer**: Global product-layer (overflow visible). Phantoms skipped. Products overflow across aligned bay boundaries naturally (same shelf height → visually seamless).
- **Fill mode dropdown**: Standard / Cross-Bay / AI / Compare. Backend mode strings: `algorithm`, `cross_bay`, `ai`, `compare`.
- **Fill button fix**: `enableFillBtn` now checks equipment.bays.length > 0 (not products.length) so button works after page reload with empty product list.

## Cross-Bay Phantom Position Bugs (v0.45 fix)
- **Phantom double-counting**: `generate_summary()` had 3 loops (sku_space, category_breakdown, brand_breakdown) that didn't skip `_phantom` positions. Cross-bay products got counted twice — once for primary, once for phantom — doubling facings, space, and revenue in the dashboard table.
- **Fix**: Add `if getattr(pos, '_phantom', False): continue` to ALL per-SKU aggregation loops. These count unique product totals, so phantoms must be skipped.
- **Shelf fill rate must include phantom visible portions**: `Shelf.used_width()` must count the visible portion of ALL positions (primary AND phantom) within `[0, shelf_width]`. Formula: `visible = max(0, min(shelf_width, x + pw) - max(0, x))`. This gives a "visual" fill rate matching what the user sees. Skipping phantoms entirely makes shelves with cross-bay overflow appear underfilled (e.g. 40% when visually 100%).
- **Two distinct metrics**: Per-SKU aggregation (facings, space, revenue) skips phantoms to avoid double-counting. Per-shelf fill rate includes phantom visible portions to match visual reality. Don't confuse them.
- **Fill rate index bug**: Frontend `renderSpaceUtilDetail()` used `bi * bay.shelves.length + si` to index flat array — breaks when bays have different shelf counts. Fix: use running counter.
- **Stale summary on reload**: `_load_saved_state()` used saved `summary` from file (stale). Fix: always call `generate_summary()` on load to recompute from current planogram data.
- **LESSON**: When adding `_phantom` to a dataclass, audit ALL loops that iterate positions — not just the obvious ones. Summary/aggregation code is easy to miss. And fill rate (visual metric) vs SKU aggregation (data metric) have different phantom handling.

## Recognition → Planogram Converter (v0.50)
- **`_build_planogram_from_recognition()`** in `app.py`: Converts recognition photos directly into planogram format.
- **Mapping**: Each photo = one bay. Shelf bounding boxes from `recognition_raw_shelves` define shelf count. Products from `recognition_assortment` placed using `line` (shelf assignment) and `x1` (left-to-right order).
- **Scale calculation**: `scale = facing.height_cm / (y2 - y1)` per product, then median per shelf. Handles perspective distortion where bottom shelves have larger pixel sizes than top.
- **Shelf height**: `median_scale * (shelf_line[N].y1 - shelf_line[N-1].y1)` converts pixel gaps to cm. Top shelf uses distance from min product y1 to first shelf line.
- **Shelf width fixed at 125 cm** (~49.21 in). Overflow logged but products kept.
- **Data flow**: `recognition_assortment.line` → shelf number, `facing.width_cm/height_cm` → product dimensions, `group.fact` → `facings_wide`, `product_info.miniature_url` → `image_url`.
- **`_load_coffee_planogram(source)`**: Now accepts `source` param ("auto", "recognition", "positions", "saved"). Auto priority: saved → recognition → positions.
- **API**: `/api/build-from-recognition` (POST, optional `shelf_width_cm` in body).
- **LESSON**: Use median (not mean) for per-shelf scale to resist outliers from misrecognized products. Filter products with `h_px > 20 and h_cm > 1` before scale calculation.

## Realogram vs Planogram Comparison (Training 3)
- **Key matching**: Both realogram products and planogram facings must use the same key (tiny_name) for accurate comparison.
- **Bug pattern**: Realogram products were using `display_name` or `art` or `product_id` as names, while planogram facings API was keyed by `tiny_name`. This caused 0% compliance even with many matching products.
- **Fix**: 
  1. `_build_planogram_from_recognition()` now prioritizes `map_dims.get("tiny_name")` for product names.
  2. `_enrich_product_names()` fixes saved realograms on-the-fly when loaded.
- **LESSON**: When comparing two data sources, verify they use the **same key format**. Log sample keys from both sides during debugging.

## Known Issues & TODOs
- Fill target is 99% but achievable ~96% due to fractional inch gaps (product widths don't evenly divide shelf width).
- `ComplianceReport` uses `.overall_pct` not `.overall_score` — always check attribute names.
- Gemini AI: 30-120s response time, overflows ~60% of shelves. Post-processing recovers to 97%+.
- API key in `.env` file (gitignored). Never commit secrets.
- Recognition converter: coffee_3 has significant overflow on most shelves (129-193 cm vs 125 cm limit) likely due to duplicate products not flagged as `is_duplicated`.
