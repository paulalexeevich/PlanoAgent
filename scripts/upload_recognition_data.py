#!/usr/bin/env python3
"""Upload recognition JSON results (raw products, raw shelves, assortment) to Supabase."""

import json
import sys
import time
import requests

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
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

PHOTO_SETS = [
    {
        "name": "coffee_1",
        "raw_products": "Demo data/coffee_1_raw_products.json",
        "raw_shelves": "Demo data/coffee_1_raw_shelves.json",
        "assortment": "data/coffee_1_assortment.json",
    },
    {
        "name": "coffee_2",
        "raw_products": "Demo data/coffee_2_raw_products.json",
        "raw_shelves": "Demo data/coffee_2_raw_shelves.json",
        "assortment": "data/coffee_2_assortment.json",
    },
    {
        "name": "coffee_3",
        "raw_products": "Demo data/coffee_3_raw_products.json",
        "raw_shelves": "Demo data/coffee_3_raw_shelves.json",
        "assortment": "data/coffee_3_assortment.json",
    },
]

MAX_RETRIES = 3


def post_rows(table, rows):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(url, headers=HEADERS, json=rows, timeout=60)
            if resp.status_code in (200, 201, 204):
                return True
            print(f"  ERROR {table} status={resp.status_code}: {resp.text[:300]}")
            if resp.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            return False
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            print(f"  {type(e).__name__}, retry {attempt + 1}/{MAX_RETRIES}")
            time.sleep(2 * (attempt + 1))
    return False


def collect_photo_ids(photo_set):
    """Extract unique photo_ids from all JSON files in a photo set."""
    photo_ids = {}
    with open(photo_set["assortment"]) as f:
        assortment = json.load(f)
    for item in assortment:
        pid = item["photo_id"]
        if pid not in photo_ids:
            photo_ids[pid] = {
                "visit_id": item.get("visit_id"),
                "scene_type": item.get("scene_type"),
            }

    with open(photo_set["raw_products"]) as f:
        raw_products = json.load(f)
    for item in raw_products:
        pid = item["photo_id"]
        if pid not in photo_ids:
            photo_ids[pid] = {"visit_id": None, "scene_type": None}

    return photo_ids


def upload_photos(photo_set):
    photo_ids = collect_photo_ids(photo_set)
    rows = []
    for pid, meta in photo_ids.items():
        rows.append({
            "photo_id": pid,
            "visit_id": meta.get("visit_id"),
            "scene_type": meta.get("scene_type"),
            "photo_name": photo_set["name"],
        })
    print(f"  Uploading {len(rows)} photo(s)...")
    return post_rows("recognition_photos", rows)


def upload_raw_products(photo_set):
    with open(photo_set["raw_products"]) as f:
        data = json.load(f)

    rows = []
    for item in data:
        rows.append({
            "external_id": item["_id"],
            "photo_id": item["photo_id"],
            "photo_name": photo_set["name"],
            "art": item.get("art"),
            "x1": item.get("x1"),
            "y1": item.get("y1"),
            "x2": item.get("x2"),
            "y2": item.get("y2"),
            "is_duplicated": item.get("is_duplicated", 0),
            "probability": item.get("probability"),
            "box_options": item.get("box_options"),
            "classification_score": item.get("classification_score"),
            "mb_hook": item.get("mb_hook", False),
            "photo_recognized_version": item.get("photo_recognized_version"),
            "cluster_id": item.get("cluster_id"),
        })

    print(f"  Uploading {len(rows)} raw products...")
    return post_rows("recognition_raw_products", rows)


def upload_raw_shelves(photo_set):
    with open(photo_set["raw_shelves"]) as f:
        data = json.load(f)

    rows = []
    for item in data:
        rows.append({
            "external_id": item["_id"],
            "photo_id": item["photo_id"],
            "photo_name": photo_set["name"],
            "x1": item.get("x1"),
            "y1": item.get("y1"),
            "x2": item.get("x2"),
            "y2": item.get("y2"),
            "line_type": item.get("line_type"),
            "approved": item.get("approved", False),
            "shelf_idx": item.get("shelf_idx") or None,
            "internal_idx": item.get("internal_idx") or None,
            "is_hook": item.get("is_hook", False),
            "photo_recognized_version": item.get("photo_recognized_version"),
        })

    print(f"  Uploading {len(rows)} raw shelves...")
    return post_rows("recognition_raw_shelves", rows)


def upload_assortment(photo_set):
    with open(photo_set["assortment"]) as f:
        data = json.load(f)

    rows = []
    for item in data:
        rows.append({
            "external_id": item["_id"],
            "photo_id": item["photo_id"],
            "photo_name": photo_set["name"],
            "product_id": item.get("product_id"),
            "x1": item.get("x1"),
            "y1": item.get("y1"),
            "x2": item.get("x2"),
            "y2": item.get("y2"),
            "numgroup": item.get("numgroup"),
            "line": item.get("line"),
            "product_realo_status_id": item.get("product_realo_status_id"),
            "face_raw_id": item.get("face_raw_id"),
            "posm_id": item.get("posm_id") or None,
            "size_algorithm": item.get("size_algorithm"),
            "is_duplicated": item.get("is_duplicated", False),
            "kma": item.get("kma"),
            "cluster_id": item.get("cluster_id"),
            "visit_id": item.get("visit_id"),
            "scene_type": item.get("scene_type"),
            "product_info": item.get("product"),
            "facing": item.get("facing"),
            "group_data": item.get("group"),
            "start_group": item.get("start_group"),
            "assortment_group": item.get("assortment_group"),
            "price": item.get("price"),
            "price_type": item.get("price_type"),
            "price_status": item.get("price_status") or None,
            "is_support": item.get("is_support", False),
            "photo_computed_version": item.get("photo_computed_version"),
        })

    print(f"  Uploading {len(rows)} assortment items...")
    return post_rows("recognition_assortment", rows)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    t0 = time.time()
    total = {"photos": 0, "raw_products": 0, "raw_shelves": 0, "assortment": 0}
    errors = 0

    sets_to_upload = PHOTO_SETS
    if target != "all":
        sets_to_upload = [s for s in PHOTO_SETS if s["name"] == target]
        if not sets_to_upload:
            print(f"Unknown photo set: {target}. Available: {[s['name'] for s in PHOTO_SETS]}")
            return

    for photo_set in sets_to_upload:
        name = photo_set["name"]
        print(f"\n=== {name} ===")

        if not upload_photos(photo_set):
            print(f"  FAILED: photos for {name}")
            errors += 1
            continue

        with open(photo_set["assortment"]) as f:
            total["photos"] += len(collect_photo_ids(photo_set))

        if upload_raw_products(photo_set):
            with open(photo_set["raw_products"]) as f:
                total["raw_products"] += len(json.load(f))
        else:
            print(f"  FAILED: raw_products for {name}")
            errors += 1

        if upload_raw_shelves(photo_set):
            with open(photo_set["raw_shelves"]) as f:
                total["raw_shelves"] += len(json.load(f))
        else:
            print(f"  FAILED: raw_shelves for {name}")
            errors += 1

        if upload_assortment(photo_set):
            with open(photo_set["assortment"]) as f:
                total["assortment"] += len(json.load(f))
        else:
            print(f"  FAILED: assortment for {name}")
            errors += 1

    elapsed = time.time() - t0
    print(f"\n--- Summary ---")
    print(f"Photos:       {total['photos']}")
    print(f"Raw products: {total['raw_products']}")
    print(f"Raw shelves:  {total['raw_shelves']}")
    print(f"Assortment:   {total['assortment']}")
    print(f"Errors:       {errors}")
    print(f"Time:         {elapsed:.1f}s")


if __name__ == "__main__":
    main()
