# Planogram Agent — Learnings & Memory

## Architecture & Technical Notes
- **Data model**: Blue Yonder hierarchy (Planogram > Equipment > Bay > Shelf > Position). `dataclass` with `asdict()` for clean serialization. `Planogram.from_dict()` for deserialization.
- **Flask + vanilla JS** (no build step). Port 5001 (5000 conflicts with macOS AirPlay).
- **Always use `python3`** on this macOS system (`python` not found).
- **Product dimensions in inches** (US retail standard). Beer reference: 6-pack cans ~7.5"x5"x5", 12-pack cans ~10.5"x5"x7.5", 6-pack bottles ~7.5"x9.5"x5". Standard gondola: 48"W x 72"H x 24"D, 5 shelves.

## Gemini AI Integration (v0.2)
- **SDK**: `google-genai` (not `google-generativeai`). Client: `genai.Client(api_key=...)`. Model: `gemini-2.5-flash`.
- **Structured output**: Use `response_mime_type="application/json"` in `GenerateContentConfig` — Gemini returns JSON directly without markdown fences.
- **Trailing comma bug**: Even with JSON mode, Gemini sometimes produces trailing commas before `}` or `]`. Fix with regex: `re.sub(r',\s*([}\]])', r'\1', text)` before `json.loads()`.
- **Prompt design**: Send full product catalog (compact JSON) + exact schema description + merchandising rules. Temperature 0.7 works well for creative but valid layouts.
- **Response time**: Gemini 2.5 Flash takes ~30-60 seconds for planogram generation (large prompt ~8K chars + complex structured output ~10K chars). Frontend needs loading spinner.
- **Validation**: Always validate product_id references exist in products array — Gemini occasionally invents IDs.

## UI/UX Notes
- Color-coded product blocks by brand `color_hex` — instant visual differentiation.
- Scale slider (px/in) for zoom. Unit toggle (in/cm) for metric conversion.
- Bottom panel for summary (not sidebar) — gives planogram full width.
- Collapsible summary with 4-column grid: metrics, category mix, fill rates, brands.
- Source tag ("Gemini AI" / "Rule-based") shows generation method.

## Known Issues & TODOs
- Rule-based placement is greedy (one pass) — 9/50 products unplaced at 53.8% fill. Multi-pass would fix.
- Gemini AI placement achieves 87-97% fill — much better than rule-based.
- API key in `.env` file (gitignored). Never commit secrets.
