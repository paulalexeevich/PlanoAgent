#!/usr/bin/env python3
"""
Populate test_coffee_product_map and test_coffee_planogram_positions
from CSV files + existing Supabase tables.

Data flow:
  1. Read product_code_external_id_map.csv for dimensions, tiny_name, external_id
  2. Join with Supabase products table (art_id) for categories
  3. Join with source_data_617533 for recognition_product_id mapping
  4. Join with recognition_assortment for miniature_url / barcode
  5. Upload merged rows to test_coffee_product_map
  6. Read plano_617533_coffee_mm.csv → upload to test_coffee_planogram_positions
"""

import csv
import json
import os
import re
import sys
import time
from collections import defaultdict

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DIR = os.path.join(BASE_DIR, "Demo data")

SUPABASE_URL = "https://zcciroutarcpkwpnynyh.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpjY2lyb3V0YXJjcGt3cG55bnloIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3NzI3MjIzMTAsImV4cCI6MjA4ODI5ODMxMH0."
    "LFnJ8WoxlNhZ06MBQm-1mmJK4mtkBLZAPd4UoPtGrkE"
)
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}


def sb_get(table, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def sb_post_batch(table, rows, batch_size=50):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    hdrs = {**HEADERS, "Content-Type": "application/json", "Prefer": "return=representation"}
    inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        resp = requests.post(url, headers=hdrs, json=batch, timeout=30)
        resp.raise_for_status()
        inserted += len(batch)
        print(f"  Inserted {inserted}/{len(rows)}")
    return inserted


# ── Step 1: Load CSV data ─────────────────────────────────────────────────────

def load_external_id_map():
    """product_code_external_id_map.csv → dict keyed by external_id."""
    path = os.path.join(DEMO_DIR, "product_code_external_id_map.csv")
    result = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            eid = (row.get("external_id") or "").strip()
            if not eid:
                continue
            result[eid] = {
                "id_field": (row.get("id") or "").strip(),
                "tiny_name": (row.get("tiny_name") or "").strip(),
                "name": (row.get("name") or "").strip(),
                "code": (row.get("code") or "").strip(),
                "width_cm": float(row.get("width") or 0),
                "height_cm": float(row.get("height") or 0),
            }
    print(f"  CSV external_id_map: {len(result)} products")
    return result


def load_planogram_csv():
    """plano_617533_coffee_mm.csv → list of row dicts."""
    path = os.path.join(DEMO_DIR, "plano_617533_coffee_mm.csv")
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("external_product_id"):
                continue
            rows.append(row)
    print(f"  CSV planogram positions: {len(rows)} rows")
    return rows


# ── Step 2: Fetch Supabase data ───────────────────────────────────────────────

def fetch_products_table():
    """products table → dict keyed by art_id."""
    rows = sb_get("products", {"select": "art_id,name_sku,code_sku,category_l0,category_l1,category_l2,category_l3"})
    result = {r["art_id"]: r for r in rows}
    print(f"  Supabase products: {len(result)} rows")
    return result


def fetch_sales_mapping():
    """source_data_617533 → dict keyed by art_id with product_code + recognition_product_id."""
    rows = sb_get("source_data_617533", {
        "select": "art_id,product_code,product_name,recognition_product_id",
    })
    by_art = {}
    for r in rows:
        aid = r.get("art_id")
        if not aid or aid in by_art:
            continue
        by_art[aid] = {
            "product_code": r.get("product_code", ""),
            "product_name": r.get("product_name", ""),
            "recognition_product_id": r.get("recognition_product_id"),
        }
    print(f"  Supabase source_data_617533: {len(by_art)} unique art_ids")
    return by_art


def fetch_recognition_info():
    """recognition_assortment → dict keyed by product_id with tiny_name, miniature_url, barcode."""
    rows = sb_get("recognition_assortment", {
        "select": "product_id,product_info",
    })
    by_pid = {}
    for r in rows:
        pid = r.get("product_id")
        if not pid or pid in by_pid:
            continue
        pi = r.get("product_info") or {}
        if isinstance(pi, str):
            try:
                pi = json.loads(pi)
            except (json.JSONDecodeError, TypeError):
                pi = {}
        by_pid[pid] = {
            "tiny_name": (pi.get("tiny_name") or "").strip(),
            "miniature_url": (pi.get("miniature_url") or "").strip(),
            "barcode": (pi.get("barcode") or "").strip(),
            "full_name": (pi.get("name") or "").strip(),
        }
    print(f"  Supabase recognition_assortment: {len(by_pid)} unique product_ids")
    return by_pid


# ── Package / weight extraction ───────────────────────────────────────────────

_PKG_PATTERNS = [
    (re.compile(r'дой[\s-]?пак', re.I), 'дой-пак'),
    (re.compile(r'стаб/бэг|ст/бэг', re.I), 'стабилбэг'),
    (re.compile(r'ст/бан', re.I), 'стеклянная банка'),
    (re.compile(r'Стеклянная бан', re.I), 'стеклянная банка'),
    (re.compile(r'Стеклянная бут', re.I), 'стеклянная бутылка'),
    (re.compile(r'ст/б(?!эг)', re.I), 'стеклянная банка'),
    (re.compile(r'с/б\b', re.I), 'стеклянная банка'),
    (re.compile(r'д/п', re.I), 'дой-пак'),
    (re.compile(r'мяг/у', re.I), 'мягкая упаковка'),
    (re.compile(r'м/уп', re.I), 'мягкая упаковка'),
    (re.compile(r'\bм/у\b', re.I), 'мягкая упаковка'),
    (re.compile(r'в/уп', re.I), 'вакуумная упаковка'),
    (re.compile(r'\bв/у\b', re.I), 'вакуумная упаковка'),
    (re.compile(r'к/уп', re.I), 'коробка'),
    (re.compile(r'\bк/у\b', re.I), 'коробка'),
    (re.compile(r'фл/п', re.I), 'флоу-пак'),
    (re.compile(r'пл/б', re.I), 'пластиковая банка'),
    (re.compile(r'\bкапс', re.I), 'коробка'),
]
_RE_WEIGHT_G = re.compile(r'(\d+[,.]?\d*)\s*г(?!о|л)', re.I)
_RE_WEIGHT_KG = re.compile(r'(\d+[,.]?\d*)\s*кг', re.I)
_RE_WEIGHT_DOT = re.compile(r',\s*\.(\d{2,4})\b')


def _extract_package_type(text: str) -> str | None:
    for pattern, pkg_type in _PKG_PATTERNS:
        if pattern.search(text):
            return pkg_type
    return None


def _extract_weight_g(text: str) -> float | None:
    m = _RE_WEIGHT_KG.search(text)
    if m:
        return round(float(m.group(1).replace(',', '.')) * 1000, 1)
    m = _RE_WEIGHT_G.search(text)
    if m:
        return round(float(m.group(1).replace(',', '.')), 1)
    m = _RE_WEIGHT_DOT.search(text)
    if m:
        val = float(m.group(1))
        return round(val * 1000 if val < 10 else val, 1)
    return None


# ── Step 3: Merge and upload ──────────────────────────────────────────────────

def build_product_map(csv_map, products_db, sales_db, recog_db):
    """Merge all sources into product_map rows."""
    rows = []

    code_to_art = {}
    for aid, sd in sales_db.items():
        pc = sd.get("product_code")
        if pc:
            code_to_art[pc] = aid

    for ext_id, csv_info in csv_map.items():
        art_id = code_to_art.get(ext_id)
        if not art_id:
            for aid, sd in sales_db.items():
                if sd.get("product_code") == ext_id:
                    art_id = aid
                    break

        prod = products_db.get(art_id, {}) if art_id else {}
        sale = sales_db.get(art_id, {}) if art_id else {}
        recog_id = sale.get("recognition_product_id")
        recog = recog_db.get(recog_id, {}) if recog_id else {}

        tiny = csv_info.get("tiny_name") or recog.get("tiny_name") or ""
        product_name = sale.get("product_name") or csv_info.get("name") or recog.get("full_name") or ""

        name_for_parse = product_name or csv_info.get("name") or ""
        row = {
            "art_id": art_id or f"_EXT_{ext_id}",
            "product_code": ext_id,
            "recognition_id": recog_id,
            "tiny_name": tiny,
            "product_name": product_name,
            "name_sku": prod.get("name_sku") or "",
            "category_l0": prod.get("category_l0") or "",
            "category_l1": prod.get("category_l1") or "",
            "category_l2": prod.get("category_l2") or "",
            "width_cm": csv_info.get("width_cm", 0),
            "height_cm": csv_info.get("height_cm", 0),
            "miniature_url": recog.get("miniature_url") or None,
            "barcode": recog.get("barcode") or None,
            "package_type": _extract_package_type(name_for_parse) or _extract_package_type(csv_info.get("name") or ""),
            "weight_g": _extract_weight_g(name_for_parse) or _extract_weight_g(csv_info.get("name") or ""),
        }
        rows.append(row)

    # Add products from sales that are NOT in the CSV (extra coverage)
    csv_codes = {r["product_code"] for r in rows}
    for aid, sd in sales_db.items():
        pc = sd.get("product_code", "")
        if pc in csv_codes or not pc:
            continue
        prod = products_db.get(aid, {})
        recog_id = sd.get("recognition_product_id")
        recog = recog_db.get(recog_id, {}) if recog_id else {}

        sale_name = sd.get("product_name") or ""
        rows.append({
            "art_id": aid,
            "product_code": pc,
            "recognition_id": recog_id,
            "tiny_name": recog.get("tiny_name") or "",
            "product_name": sale_name,
            "name_sku": prod.get("name_sku") or "",
            "category_l0": prod.get("category_l0") or "",
            "category_l1": prod.get("category_l1") or "",
            "category_l2": prod.get("category_l2") or "",
            "width_cm": 0,
            "height_cm": 0,
            "miniature_url": recog.get("miniature_url") or None,
            "barcode": recog.get("barcode") or None,
            "package_type": _extract_package_type(sale_name),
            "weight_g": _extract_weight_g(sale_name),
        })

    print(f"\n  Merged product map: {len(rows)} rows")
    with_tiny = sum(1 for r in rows if r["tiny_name"])
    with_recog = sum(1 for r in rows if r["recognition_id"])
    with_dims = sum(1 for r in rows if r["width_cm"] > 0)
    with_img = sum(1 for r in rows if r["miniature_url"])
    print(f"    with tiny_name:     {with_tiny}")
    print(f"    with recognition_id:{with_recog}")
    print(f"    with dimensions:    {with_dims}")
    print(f"    with miniature_url: {with_img}")
    return rows


def build_planogram_positions(csv_rows):
    """Transform planogram CSV rows into table rows."""
    rows = []
    for r in csv_rows:
        try:
            rows.append({
                "store_id": (r.get("external_store_id") or "617533").strip(),
                "scene_group_id": int(r.get("scene_group_id") or 0),
                "external_product_id": r["external_product_id"].strip(),
                "external_product_name": (r.get("external_product_name") or "").strip(),
                "eq_num_in_scene_group": int(r.get("eq_num_in_scene_group") or 0),
                "shelf_number": int(r.get("shelf_number") or 0),
                "on_shelf_position": int(r.get("on_shelf_position") or 0),
                "faces_width": int(r.get("faces_width") or 1),
                "faces_height": int(r.get("faces_height") or 1),
                "faces_depth": int(r.get("faces_depth") or 1),
                "address": (r.get("address") or "").strip(),
            })
        except (ValueError, KeyError) as e:
            print(f"  Skipping row: {e}")
    return rows


def main():
    print("=" * 70)
    print("  Coffee Data Migration → Supabase")
    print("=" * 70)

    print("\n[1/5] Loading CSV data...")
    csv_map = load_external_id_map()
    plano_csv = load_planogram_csv()

    print("\n[2/5] Fetching Supabase data...")
    products_db = fetch_products_table()
    sales_db = fetch_sales_mapping()
    recog_db = fetch_recognition_info()

    print("\n[3/5] Merging product map...")
    product_rows = build_product_map(csv_map, products_db, sales_db, recog_db)

    print("\n[4/5] Uploading test_coffee_product_map...")
    n1 = sb_post_batch("test_coffee_product_map", product_rows)
    print(f"  Done: {n1} rows inserted")

    print("\n[5/5] Uploading test_coffee_planogram_positions...")
    position_rows = build_planogram_positions(plano_csv)
    n2 = sb_post_batch("test_coffee_planogram_positions", position_rows)
    print(f"  Done: {n2} rows inserted")

    print("\n" + "=" * 70)
    print(f"  Migration complete!")
    print(f"    test_coffee_product_map:          {n1} rows")
    print(f"    test_coffee_planogram_positions:   {n2} rows")
    print("=" * 70)


if __name__ == "__main__":
    main()
