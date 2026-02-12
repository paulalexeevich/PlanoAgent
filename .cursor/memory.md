# Planogram Agent — Learnings & Memory

## v0.1 — Initial Prototype (2026-02-12)

### Key Architecture Decisions
- **Data model follows industry standard**: Blue Yonder Space Planning hierarchy (Project > Planogram > Equipment > Bay > Shelf > Position). This mirrors how real planogram software works and makes future integration easier.
- **Placement algorithm uses weight-based tiering**: Heavy/large packs on bottom shelves, premium items at eye level. This is standard retail merchandising practice.
- **Flask + vanilla JS chosen over React/etc.**: For prototype speed. The HTML template is self-contained — no build step needed. Can migrate to React later if complexity grows.

### What Went Well
- Using `dataclass` for the schema made serialization/deserialization clean with `asdict()`.
- Color-coded product blocks based on brand `color_hex` creates immediate visual differentiation.
- The scale slider (px-per-inch) lets users zoom in/out on the planogram naturally.

### What Went Wrong & Fixes
- `python` not found on macOS — must use `python3`. Always use `python3` for commands on this system.
- 9 of 50 products unplaced (fill rate 53.8%) — the placement algorithm is greedy (left-to-right, one pass per shelf tier). Products that don't fit in first bay's shelves get skipped. **TODO**: Add multi-pass placement and overflow to next bay.
- Product labels get clipped when blocks are too small at low scale — used CSS `-webkit-line-clamp` and `overflow: hidden` to handle gracefully.

### Technical Notes
- Product dimensions use inches (industry standard for US retail). All shelf/bay dimensions in inches.
- Beer package sizes reference: 12oz can ~2.6"x4.83", 6-pack cans ~7.5"x5"x5", 12-pack cans ~10.5"x5"x7.5", 6-pack bottles ~7.5"x9.5"x5".
- Standard gondola: 48" wide bays, 72" tall, 24" deep, typically 5 shelves.
- Port 5001 used (5000 often conflicts with macOS AirPlay Receiver).
