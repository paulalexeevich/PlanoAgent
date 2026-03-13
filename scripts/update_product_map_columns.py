#!/usr/bin/env python3
"""
Populate package_type and weight_g columns in test_coffee_product_map.

Parses packaging and weight info from product_name / name_sku fields.

Package type patterns (Russian abbreviations):
  д/п, дой-пак     → дой-пак (doypack)
  ст/б, ст/бан, с/б → стеклянная банка (glass jar)
  стаб/бэг, ст/бэг → стабилбэг (stabil bag)
  мяг/у, м/у, м/уп → мягкая упаковка (soft pack)
  в/у, в/уп        → вакуумная упаковка (vacuum pack)
  к/уп, к/у        → коробка (box)
  фл/п             → флоу-пак (flow pack)
  пл/б             → пластиковая банка (plastic jar)
  Стекл. бутылка   → стеклянная бутылка (glass bottle)
  капс              → коробка (capsules in box)
"""

import os
import re
import sys
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

PACKAGE_PATTERNS = [
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

RE_WEIGHT_GRAMS = re.compile(r'(\d+[,.]?\d*)\s*г(?!о|л)', re.I)
RE_WEIGHT_KG = re.compile(r'(\d+[,.]?\d*)\s*кг', re.I)
RE_WEIGHT_DOT = re.compile(r',\s*\.(\d{2,4})\b')
RE_TINY_WEIGHT = re.compile(r'\.(\d{2,4})$')

TINY_NAME_PKG_MAP = {
    'J': 'стеклянная банка',
    'W': 'дой-пак',
    'V': 'вакуумная упаковка',
    'C': 'коробка',
    'B': 'пластиковая банка',
    'D': 'дой-пак',
    'L': 'мягкая упаковка',
    'G': 'стеклянная бутылка',
}


def extract_package_type(text: str) -> str | None:
    for pattern, pkg_type in PACKAGE_PATTERNS:
        if pattern.search(text):
            return pkg_type
    return None


def extract_package_from_tiny(tiny: str) -> str | None:
    """Derive package type from tiny_name suffix letter (J/W/V/C/B/D/L/G)."""
    if not tiny:
        return None
    m = re.match(r'^[A-Za-z_]+([A-Z])[\.\d]', tiny)
    if m:
        return TINY_NAME_PKG_MAP.get(m.group(1))
    m = re.match(r'^[A-Za-z_]+([A-Z])\d+PC$', tiny)
    if m and m.group(1) == 'C':
        return 'коробка'
    return None


def extract_weight_g(text: str) -> float | None:
    m = RE_WEIGHT_KG.search(text)
    if m:
        return round(float(m.group(1).replace(',', '.')) * 1000, 1)

    m = RE_WEIGHT_GRAMS.search(text)
    if m:
        return round(float(m.group(1).replace(',', '.')), 1)

    m = RE_WEIGHT_DOT.search(text)
    if m:
        val = float(m.group(1))
        if val < 10:
            return round(val * 1000, 1)
        return round(val, 1)

    return None


def extract_weight_from_tiny(tiny: str) -> float | None:
    """Derive weight from tiny_name dot-suffix. Values are in kg: .235→235g, 1.000→1000g."""
    if not tiny:
        return None
    m = re.search(r'(\d*\.\d{1,4})$', tiny)
    if m:
        val_str = m.group(1)
        if val_str.startswith('.'):
            val_str = '0' + val_str
        val_kg = float(val_str)
        grams = round(val_kg * 1000, 1)
        if grams > 0:
            return grams
    return None


def sb_get(table, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def sb_patch(table, row_id, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{row_id}"
    hdrs = {**HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"}
    resp = requests.patch(url, headers=hdrs, json=data, timeout=30)
    resp.raise_for_status()


def main():
    print("=" * 70)
    print("  Update package_type & weight_g in test_coffee_product_map")
    print("=" * 70)

    print("\n[1/3] Fetching rows...")
    rows = sb_get("test_coffee_product_map", {
        "select": "id,product_name,name_sku,tiny_name",
        "order": "id",
    })
    print(f"  Found {len(rows)} rows")

    print("\n[2/3] Parsing package_type & weight_g...")
    updates = []
    stats = {"pkg_found": 0, "wgt_found": 0, "pkg_missing": [], "wgt_missing": []}

    for r in rows:
        text = r.get("product_name") or ""
        text_sku = r.get("name_sku") or ""
        tiny = r.get("tiny_name") or ""

        pkg = (extract_package_type(text)
               or extract_package_type(text_sku)
               or extract_package_from_tiny(tiny))
        wgt = (extract_weight_g(text)
               or extract_weight_g(text_sku)
               or extract_weight_from_tiny(tiny))

        if pkg:
            stats["pkg_found"] += 1
        else:
            stats["pkg_missing"].append(text or text_sku or f"id={r['id']}")

        if wgt:
            stats["wgt_found"] += 1
        else:
            stats["wgt_missing"].append(text or text_sku or f"id={r['id']}")

        update_data = {}
        if pkg:
            update_data["package_type"] = pkg
        if wgt:
            update_data["weight_g"] = wgt

        if update_data:
            updates.append((r["id"], update_data))

    print(f"  package_type found: {stats['pkg_found']}/{len(rows)}")
    print(f"  weight_g found:     {stats['wgt_found']}/{len(rows)}")

    if stats["pkg_missing"]:
        print(f"\n  Missing package_type ({len(stats['pkg_missing'])} rows):")
        for name in stats["pkg_missing"][:15]:
            print(f"    - {name[:80]}")
        if len(stats["pkg_missing"]) > 15:
            print(f"    ... and {len(stats['pkg_missing']) - 15} more")

    if stats["wgt_missing"]:
        print(f"\n  Missing weight_g ({len(stats['wgt_missing'])} rows):")
        for name in stats["wgt_missing"][:15]:
            print(f"    - {name[:80]}")
        if len(stats["wgt_missing"]) > 15:
            print(f"    ... and {len(stats['wgt_missing']) - 15} more")

    print(f"\n[3/3] Updating {len(updates)} rows in Supabase...")
    updated = 0
    for row_id, data in updates:
        sb_patch("test_coffee_product_map", row_id, data)
        updated += 1
        if updated % 20 == 0:
            print(f"  Updated {updated}/{len(updates)}")

    print(f"  Done: {updated} rows updated")

    print("\n  Package type distribution:")
    dist = {}
    for _, data in updates:
        pkg = data.get("package_type", "—")
        dist[pkg] = dist.get(pkg, 0) + 1
    for pkg, cnt in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"    {pkg:25s} {cnt}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
