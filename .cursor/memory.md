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
- Step labels (Step 1 / Step 2) with color-coded badges.
- "Fill Products" disabled until equipment exists.
- Source tags: "Empty Equipment" (orange), "Gemini AI" (blue), "Rule-based (fallback)" (purple), "Rule-based" (green).
- Color-coded product blocks by brand `color_hex`. Scale slider, unit toggle (in/cm).
- Bottom collapsible summary: metrics, category mix, fill rates, brands.

## Known Issues & TODOs
- Rule-based fallback achieves ~93% fill (improved from 53% via product_logic tier system).
- Gemini AI fill quality varies — sometimes truncates or adds extra fields, but fallback catches it.
- API key in `.env` file (gitignored). Never commit secrets.
- Flask debug mode restarts clear server state (current_equipment). Production needs persistent storage.
