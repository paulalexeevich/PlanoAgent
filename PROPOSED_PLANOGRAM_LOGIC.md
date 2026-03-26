# Proposed Planogram Logic

This document describes how `placement_optimization.py` decides installs.

## Pipeline

1. Build shelf baseline from `realogram_positions`:
   - per-shelf used/free width
   - products on shelf
   - excess-facing reduction candidates
   - decision-tree groups
2. Load out-of-shelf actions (`planogram_actions` with `photo_facings = 0`), excluding `out_of_stock`.
3. Run strategies:
   - `sales_first_strict`
   - `sales_first_flexible`
   - `tree_first`
   - `min_time`
4. For each product in strategy order:
   - score shelf candidates by decision-tree depth
   - try fit (free space -> reduction -> relocation)
   - pick best option (tree score, then time)
   - apply only selected action
5. Opportunistic pass:
   - retry still-unplaced products with relaxed shelf selection
6. Pick best strategy by weighted score and build output.

## Observability

Each action in API output includes `decision_trace`:

- `needed_cm`
- `product_group`
- `candidates` (shelf-level fit attempts and metrics)
- `selected` (chosen shelf and source)

Summary includes `logic_steps` and `opportunistic_added_count`.

## Important invariant

Candidate evaluation must not mutate global shelf state.
Only the selected option is applied.
