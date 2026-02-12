# Planogram Agent — Learnings & Memory

## Architecture & Technical Notes
- **Data model**: Blue Yonder hierarchy (Planogram > Equipment > Bay > Shelf > Position). `dataclass` with `asdict()` for serialization.
- **Tolerant deserialization**: `Planogram.from_dict()` uses `_safe()` helper to drop unknown fields — critical for Gemini AI which adds extra keys (e.g. `y_position` on Position). Always filter to known dataclass fields.
- **Flask + vanilla JS** (no build step). Port 5001 (5000 conflicts with macOS AirPlay).
- **Always use `python3`** on this macOS system (`python` not found).
- **Product dimensions in inches** (US retail standard). Standard gondola: 48"W x 72"H x 24"D, 5 shelves.

## Two-Step Generation (v0.3) → 3-Phase Algorithm (v0.5)
- **Step 1**: Structured equipment form → `/api/generate-equipment` → empty shelves. Form + Generate button hidden behind collapsible "Equipment Config" toggle.
- **Step 2**: "Fill Products" → `/api/fill-products` → 3-phase pipeline:
  - **Phase 1 (Capacity Check)**: Sort products by `weekly_units_sold` DESC. If total width at 1 facing each > total shelf width, drop lowest sellers until they fit.
  - **Phase 2 (Optimal Facings)**: Start at 1 facing per product. Iterate through products by sales rank, adding 1 facing if it fits, until ~95% target fill. Returns `{product_id: facing_count}` dict.
  - **Phase 3 (Placement)**: Send products + pre-calculated facings to Gemini AI (it only decides *where* to place, not *how many*). Rule-based fallback if AI fails.
  - **Post-processing**: `validate_and_fix_shelves()` catches any AI shelf overflows — reduces facings on low sellers, removes excess products, recalculates x_positions.
- **`product_logic.py`**: `ProductLogicRules` dataclass — fill_target_pct=95%, max_facings=5.
- **Sales data**: `weekly_units_sold` field on each product (fake data for demo). Domestic Light Lagers ~130-180 units, Craft IPAs ~15-22 units.
- **Server state resilience**: `init_default_planogram()` now sets `current_equipment`. Frontend sends equipment in fill request body as fallback for server restarts.
- **Empty shelf visualization**: CSS class `empty-shelf` with dashed border + dimension labels.

## Gemini AI Integration
- **SDK**: `google-genai`. Client: `genai.Client(api_key=...)`. Model: `gemini-2.5-flash`.
- **Structured output**: `response_mime_type="application/json"` in config.
- **Token limit**: Use `max_output_tokens=65536` for fill responses (24+ shelves generate ~55K char JSON). 16K causes truncation errors.
- **Trailing comma bug**: Gemini produces trailing commas. Fix: `re.sub(r',\s*([}\]])', r'\1', text)`.
- **Extra fields bug**: Gemini adds unexpected fields to JSON objects. Fix: filter dicts to known dataclass fields before constructing objects.
- **Response time**: 30-120 seconds depending on equipment size. Frontend needs loading spinner.
- **Validation**: Always validate product_id references exist in products array.
- **Prompt design**: Send equipment structure + product catalog + rules as structured text. Temperature 0.7.

## UI/UX Notes
- Two-step UI: equipment form (dropdowns + numbers) + "Generate Equipment" / "Fill Products" buttons.
- Source tags: "Empty Equipment" (orange), "Gemini AI" (blue), "Rule-based (fallback)" (purple), "Rule-based" (green).
- **Planogram rendering**: Products use **absolute positioning** (`left: x_position * scale`), NOT flexbox. Bay must have `flex-shrink: 0` + `box-sizing: content-box` to prevent flex container from shrinking bays below their actual width. Shelf has `overflow: visible`, bay-body clips at boundary.
- Scale slider, unit toggle (in/cm). At high zoom, page scrolls horizontally.
- Bottom collapsible summary: metrics, category mix, fill rates, decision tree compliance.

## Decision Tree (v0.4)
- **`decision_tree.py`**: Pre-built trees per category. Beer tree: Segment → Style (subcategory) → Package → Brand.
- **Derivation functions**: `_derive_beer_segment()` maps subcategory prefix to Domestic/Craft/Import/Specialty. Stored by name in `_DERIVE_REGISTRY` (JSON-safe).
- **Compliance validation**: Walk positions in planogram order (bay→shelf→left-to-right). Count "breaks" — group reappearing after interruption. Score: 0-100% per level, weighted average for overall.
- **Rule-based sort by tree**: `fill_equipment_rule_based()` accepts optional `decision_tree` param. Products within each tier bucket sorted by `get_product_group_tuple()` — improves in-tier grouping but tier logic (heavy items low) still disrupts pure tree order.
- **AI prompt includes tree**: `build_fill_prompt()` accepts `decision_tree`, injects `to_prompt_text()` — instructs Gemini to follow hierarchical grouping. AI compliance much higher than rule-based.
- **UI**: Bottom panel shows tree levels as L1→L2→L3→L4 pills, overall % score (color-coded), per-level compliance bars, and break count.
- **Shelf overlays**: Colored bands + labels (Domestic/Craft/Import/Specialty) drawn behind product groups using `SEGMENT_COLORS` and `_addGroupBand()`.

## CSS Layout Lessons
- **Never use `justify-content: center` on scrollable flex containers** — when content overflows, left side becomes inaccessible. Use `width: fit-content; margin: 0 auto` instead for centering that scrolls correctly.
- **Collapsible panels**: Use `max-height` + `overflow: hidden` + `opacity` transitions. Set `max-height` high enough for content (200px for form + button). Toggle `.open` class on wrapper, not content.

## Known Issues & TODOs
- Rule-based fallback achieves ~93% fill but ~43% decision tree compliance (tier logic conflicts with tree grouping).
- Gemini AI: 30-120s response time, sometimes ignores constraints. Post-processing validator now catches shelf overflows.
- API key in `.env` file (gitignored). Never commit secrets.
- 3-phase algorithm separates "how many facings" (math) from "where to place" (AI). This is the right separation of concerns — AI is unreliable for math constraints but good for merchandising logic.
