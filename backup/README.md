# Backup: Pre-Migration Data Files

These files were the original CSV/JSON/XLSX data used by the app before migrating to Supabase (March 2026).

**All data now lives in Supabase tables:**
- `test_coffee_product_map` — product dimensions, names, images, barcodes
- `test_coffee_planogram_positions` — shelf positions for store 617533
- `recognition_assortment` / `recognition_raw_shelves` — photo recognition data

**This directory is excluded from Vercel deployment** (via `.vercelignore`).

## Contents

### demo_data/
| File | Description |
|------|-------------|
| `coffee_*_assortment.json` | Recognition assortment data per photo |
| `coffee_*_raw_products.json` | Raw product detections per photo |
| `coffee_*_raw_shelves.json` | Raw shelf detections per photo |
| `plano_617533_coffee_mm.csv` | Planogram positions (shelf layout) |
| `product_art_mapping.csv` | recognition_id → product name mapping |
| `product_code_external_id_map.csv` | product_code → dimensions + tiny_name |
| `ММ_данные_для_теста (1).xlsx` | Original source Excel from MM |

### data/
| File | Description |
|------|-------------|
| `coffee_*_assortment.json` | Copies of assortment data |
| `coffee_default_planogram.json` | Pre-built coffee planogram JSON |
| `sample_planogram.json` | Generator output (beer) |
| `planogram_summary.json` | Generator summary output |
