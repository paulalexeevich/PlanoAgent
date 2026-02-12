# Planogram Agent — Learnings & Memory

## Architecture & Technical Notes
- **Data model**: Blue Yonder hierarchy (Planogram > Equipment > Bay > Shelf > Position). `dataclass` with `asdict()` for serialization.
- **Tolerant deserialization**: `Planogram.from_dict()` uses `_safe()` helper to drop unknown fields — critical for Gemini AI which adds extra keys (e.g. `y_position` on Position). Always filter to known dataclass fields.
- **Flask + vanilla JS** (no build step). Port 5001 (5000 conflicts with macOS AirPlay).
- **Always use `python3`** on this macOS system (`python` not found).
- **Product dimensions in inches** (US retail standard). Standard gondola: 48"W x 72"H x 24"D, 5 shelves.

## Two-Step Generation (v0.3)
- **Step 1**: Structured equipment form → `/api/generate-equipment` → empty shelves (no products).
- **Step 2**: "Fill Products" → `/api/fill-products` → Gemini AI primary, rule-based fallback.
- **`product_logic.py`**: `ProductLogicRules` dataclass controls shelf-tier assignments, fill targets (85%), max facings (3), grouping strategy, top-seller brands.
- **Server state**: `current_equipment` (dict) persists between steps. Flask debug mode restarts clear it — re-generate equipment after code changes.
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

## Known Issues & TODOs
- Rule-based fallback achieves ~93% fill but only ~43% decision tree compliance (tier logic conflicts with tree grouping).
- Gemini AI fill quality varies — sometimes truncates, adds extra fields, or leaves shelves empty. Fallback catches most issues.
- API key in `.env` file (gitignored). Never commit secrets.
- Flask debug mode restarts clear server state (current_equipment). Production needs persistent storage.
- Some Gemini fills overfill shelves (>100% width). Need server-side width constraint validation.
