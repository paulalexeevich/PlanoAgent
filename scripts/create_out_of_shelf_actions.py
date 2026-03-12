#!/usr/bin/env python3
"""
Create planogram_actions for out-of-shelf products.

Replicates the frontend logic: products in the planogram that have 0 photo facings
are "out of shelf". For each, inserts a task into planogram_actions with sales data.
"""

import os
import sys
from collections import defaultdict

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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
PLANOGRAM_ID = "PLN-CSV-COFFEE-617533"


def supabase_get(table, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def supabase_post(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    hdrs = {**HEADERS, "Content-Type": "application/json", "Prefer": "return=representation"}
    resp = requests.post(url, headers=hdrs, json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def load_product_sizes():
    """Load product sizes from Supabase test_coffee_product_map."""
    rows = supabase_get("test_coffee_product_map", {
        "select": "product_code,tiny_name,product_name,width_cm,height_cm,category_l1,category_l2",
    })
    size_map = {}
    for r in rows:
        pc = r.get("product_code")
        if not pc:
            continue
        size_map[pc] = {
            "width_cm": float(r.get("width_cm") or 0),
            "height_cm": float(r.get("height_cm") or 0),
            "name": r.get("product_name") or "",
            "tiny_name": r.get("tiny_name") or "",
            "category_l1": r.get("category_l1") or "",
            "category_l2": r.get("category_l2") or "",
        }
    return size_map


def build_planogram_facings(planogram_data, size_map):
    """Build tiny_name → {facings_wide, positions, name, brand, width_cm, height_cm}."""
    ext_to_tiny = {eid: info["tiny_name"] for eid, info in size_map.items() if info.get("tiny_name")}

    prod_lookup = {}
    for p in planogram_data.get("products", []):
        prod_lookup[p.get("id", "")] = p

    facings = {}
    equipment = planogram_data.get("equipment", {})
    for bay in equipment.get("bays", []):
        for shelf in bay.get("shelves", []):
            for pos in shelf.get("positions", []):
                pid = pos.get("product_id", "")
                if pos.get("_phantom"):
                    continue
                ext_id = pid.replace("CSV-", "") if pid.startswith("CSV-") else pid
                tiny = ext_to_tiny.get(ext_id, "")
                if not tiny:
                    continue
                fw = pos.get("facings_wide", 1)
                if tiny not in facings:
                    prod = prod_lookup.get(pid, {})
                    sz = size_map.get(ext_id, {})
                    facings[tiny] = {
                        "facings_wide": 0,
                        "positions": 0,
                        "name": prod.get("name", ""),
                        "brand": prod.get("brand", ""),
                        "image_url": prod.get("image_url", ""),
                        "width_cm": sz.get("width_cm", 0),
                        "height_cm": sz.get("height_cm", 0),
                        "product_code": ext_id,
                        "category_l1": sz.get("category_l1", ""),
                        "category_l2": sz.get("category_l2", ""),
                    }
                facings[tiny]["facings_wide"] += fw
                facings[tiny]["positions"] += 1
    return facings


def get_photo_facings():
    """Get dict of tiny_name → facing count across all photos."""
    import json as json_mod
    photos = supabase_get("recognition_photos", {"select": "photo_name"})
    tiny_counts = defaultdict(int)

    for photo in photos:
        photo_name = photo["photo_name"]
        assortment = supabase_get("recognition_assortment", {
            "select": "product_info",
            "photo_name": f"eq.{photo_name}",
        })
        for item in assortment:
            pi = item.get("product_info")
            if isinstance(pi, str):
                try:
                    pi = json_mod.loads(pi)
                except (json_mod.JSONDecodeError, AttributeError):
                    continue
            if isinstance(pi, dict):
                tiny = pi.get("tiny_name", "")
                if tiny:
                    tiny_counts[tiny] += 1

    return tiny_counts


def get_sales_data(size_map):
    """Get sales data keyed by tiny_name using product map for mapping."""
    ext_to_tiny = {eid: info["tiny_name"] for eid, info in size_map.items() if info.get("tiny_name")}

    rows = supabase_get("source_data_617533", {
        "select": "product_code,product_name,recognition_product_id,"
                  "sale_amount,sale_qty,stock_qty,on_planogram,"
                  "face_width_planogram,in_target_assortment",
    })

    agg = defaultdict(lambda: {"amounts": [], "qty": [], "stock": [],
                               "product_name": "", "product_code": ""})
    for r in rows:
        tiny = ext_to_tiny.get(r.get("product_code", ""), "")
        pid = r.get("recognition_product_id") or ""
        if not tiny and not pid:
            continue
        key = tiny or pid
        amt = r.get("sale_amount")
        qty = r.get("sale_qty")
        stk = r.get("stock_qty")
        if amt is not None:
            agg[key]["amounts"].append(float(amt))
        if qty is not None:
            agg[key]["qty"].append(float(qty))
        if stk is not None:
            agg[key]["stock"].append(float(stk))
        agg[key]["product_name"] = r.get("product_name", "")
        agg[key]["product_code"] = r.get("product_code", "")

    result = {}
    for key, v in agg.items():
        result[key] = {
            "avg_sale_amount": round(sum(v["amounts"]) / len(v["amounts"]), 2) if v["amounts"] else 0,
            "avg_sale_qty": round(sum(v["qty"]) / len(v["qty"]), 2) if v["qty"] else 0,
            "avg_stock_qty": round(sum(v["stock"]) / len(v["stock"]), 2) if v["stock"] else 0,
            "weeks": len(v["amounts"]),
            "product_name": v["product_name"],
            "product_code": v["product_code"],
        }
    return result


def main():
    print("Loading product sizes...")
    size_map = load_product_sizes()
    print(f"  {len(size_map)} products in size map")

    print("Loading planogram from Supabase...")
    plano_rows = supabase_get("planograms", {
        "select": "planogram_data",
        "planogram_id": f"eq.{PLANOGRAM_ID}",
        "limit": "1",
    })
    if not plano_rows:
        print("ERROR: No planogram found!")
        return
    planogram_data = plano_rows[0]["planogram_data"]
    print(f"  Planogram loaded: {PLANOGRAM_ID}")

    print("Building planogram facings...")
    plano_facings = build_planogram_facings(planogram_data, size_map)
    print(f"  {len(plano_facings)} unique products in planogram")

    print("Getting photo facings from recognition data...")
    photo_facings = get_photo_facings()
    print(f"  {len(photo_facings)} unique products found in photos")
    print(f"  Total facings across photos: {sum(photo_facings.values())}")

    print("Getting sales data...")
    sales = get_sales_data(size_map)
    print(f"  {len(sales)} products with sales data")

    out_of_shelf = []
    for tiny, pf in plano_facings.items():
        pf_count = photo_facings.get(tiny, 0)
        if pf_count == 0:
            sd = sales.get(tiny, {})
            out_of_shelf.append({
                "tiny_name": tiny,
                "product_name": pf["name"] or sd.get("product_name", ""),
                "brand": pf.get("brand", ""),
                "product_code": pf.get("product_code", "") or sd.get("product_code", ""),
                "planogram_facings": pf["facings_wide"],
                "width_cm": pf["width_cm"],
                "height_cm": pf["height_cm"],
                "avg_sale_amount": sd.get("avg_sale_amount", 0),
                "avg_sale_qty": sd.get("avg_sale_qty", 0),
                "avg_stock_qty": sd.get("avg_stock_qty", 0),
                "weeks": sd.get("weeks", 0),
                "category_l1": pf.get("category_l1", ""),
                "category_l2": pf.get("category_l2", ""),
            })

    out_of_shelf.sort(key=lambda x: x["avg_sale_amount"], reverse=True)

    print(f"\n{'='*80}")
    print(f"OUT-OF-SHELF PRODUCTS: {len(out_of_shelf)}")
    print(f"{'='*80}")
    for i, p in enumerate(out_of_shelf, 1):
        print(f"  {i:2d}. {p['tiny_name']:20s} | plano:{p['planogram_facings']} | "
              f"sale:{p['avg_sale_amount']:>8.1f}₽ | qty:{p['avg_sale_qty']:.1f} | "
              f"stock:{p['avg_stock_qty']:.1f}")

    with_sales = [p for p in out_of_shelf if p["avg_sale_amount"] > 0]
    print(f"\nWith sales > 0: {len(with_sales)}")

    print(f"\nInserting {len(out_of_shelf)} actions into planogram_actions...")
    for p in out_of_shelf:
        priority = "high" if p["avg_sale_amount"] >= 500 else ("medium" if p["avg_sale_amount"] >= 100 else "low")
        row = {
            "planogram_id": PLANOGRAM_ID,
            "action_type": "place_on_shelf",
            "status": "pending",
            "tiny_name": p["tiny_name"],
            "product_name": p["product_name"],
            "brand": p["brand"],
            "product_code": p["product_code"],
            "planogram_facings": p["planogram_facings"],
            "photo_facings": 0,
            "width_cm": p["width_cm"],
            "height_cm": p["height_cm"],
            "avg_sale_amount": p["avg_sale_amount"],
            "avg_sale_qty": p["avg_sale_qty"],
            "avg_stock_qty": p["avg_stock_qty"],
            "weeks": p["weeks"],
            "priority": priority,
            "category_l1": p.get("category_l1", ""),
            "category_l2": p.get("category_l2", ""),
            "notes": f"Product in planogram ({p['planogram_facings']} facings) but missing from shelf photos. "
                     f"Weekly avg sales: {p['avg_sale_amount']}₽",
        }
        result = supabase_post("planogram_actions", row)
        print(f"  ✓ {p['tiny_name']} (priority: {priority})")

    print(f"\nDone! {len(out_of_shelf)} actions created.")


if __name__ == "__main__":
    main()
