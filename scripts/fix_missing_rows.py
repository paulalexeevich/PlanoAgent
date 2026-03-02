#!/usr/bin/env python3
"""Find and upload missing rows from source_data."""

import time
import openpyxl
import requests

SUPABASE_URL = "https://mrbevgewrtgalaahcjog.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1yYmV2Z2V3cnRnYWxhYWhjam9nIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIzOTgwMTQsImV4cCI6MjA4Nzk3NDAxNH0.3kpL6Sen3X9bCFledYobgahOj3te5ZZmY6AJygdPvdc"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}
EXCEL_PATH = "Demo data/ММ_данные_для_теста (1).xlsx"
BATCH_SIZE = 200


def safe_num(val):
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_int(val):
    if val is None or str(val).strip() == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def safe_str(val):
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def parse_date(val):
    if val is None:
        return None
    s = str(val).strip()
    if " " in s:
        s = s.split(" ")[0]
    return s


def post_batch_with_verify(table, rows, batch_num):
    """Post batch sequentially with retry and verification."""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    for attempt in range(5):
        try:
            resp = requests.post(url, headers=HEADERS, json=rows, timeout=180)
            if resp.status_code in (200, 201, 204):
                return True
            print(f"  ERROR batch#{batch_num} status={resp.status_code}: {resp.text[:200]}", flush=True)
            if resp.status_code == 429:
                time.sleep(3)
                continue
            return False
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            print(f"  {type(e).__name__} batch#{batch_num} attempt {attempt+1}/5, retrying in {2**attempt}s...", flush=True)
            time.sleep(2 ** attempt)
    return False


def get_existing_ids():
    """Fetch all existing (whs_id, art_id, visit_date) combos from DB."""
    url = f"{SUPABASE_URL}/rest/v1/source_data?select=whs_id,art_id,visit_date"
    existing = set()
    offset = 0
    limit = 10000
    while True:
        resp = requests.get(
            f"{url}&offset={offset}&limit={limit}",
            headers={**HEADERS, "Prefer": "count=exact"},
            timeout=120,
        )
        if resp.status_code != 200:
            print(f"Error fetching existing: {resp.status_code} {resp.text[:200]}", flush=True)
            break
        rows = resp.json()
        if not rows:
            break
        for r in rows:
            existing.add((r["whs_id"], r["art_id"], r["visit_date"]))
        offset += limit
        print(f"  Loaded {offset} existing records...", flush=True)
    return existing


def main():
    print("Step 1: Loading existing records from DB...", flush=True)
    existing = get_existing_ids()
    print(f"  Found {len(existing)} unique (whs_id, art_id, visit_date) in DB", flush=True)

    print("\nStep 2: Reading Excel file...", flush=True)
    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
    ws = wb["Исходник"]
    headers_list = None
    missing = []

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            headers_list = list(row)
            col = {h: idx for idx, h in enumerate(headers_list)}
            continue

        whs = str(row[col["WHS_ID"]])
        art = str(row[col["ART_ID"]])
        dt = parse_date(row[col["day_id"]])
        key = (whs, art, dt)

        if key not in existing:
            record = {
                "whs_id": whs,
                "store_name": str(row[col["name_tt"]]),
                "store_code": str(row[col["code_tt"]]),
                "zone_name": str(row[col["zone_name"]]),
                "visit_date": dt,
                "art_id": art,
                "product_name": str(row[col["name_sku"]]),
                "product_code": str(row[col["code_sku"]]),
                "category_l0": safe_str(row[col["ART_GRP_LVL_0_NAME"]]),
                "category_l1": safe_str(row[col["ART_GRP_LVL_1_NAME"]]),
                "category_l2": safe_str(row[col["ART_GRP_LVL_2_NAME"]]),
                "category_l3": safe_str(row[col["ART_GRP_LVL_3_NAME"]]),
                "week_id": safe_str(row[col["WEEK_ID_2"]]),
                "is_test_week": safe_int(row[col["pr_test_week"]]),
                "sale_amount": safe_num(row[col["sale"]]),
                "sale_qty": safe_num(row[col["sale_qnty"]]),
                "stock_qty": safe_num(row[col["rest_qnty"]]),
                "days_count": safe_int(row[col["cnt_day"]]),
                "stock_qty_visit": safe_num(row[col["rest_qnty_vizit"]]),
                "in_target_assortment": safe_int(row[col["pr_ca"]]),
                "on_planogram": safe_int(row[col["pr_pg"]]),
                "sku_marker": safe_str(row[col["Признак SKU"]]),
                "face_width_planogram": safe_num(row[col["Фейс в шир по ПГ"]]),
                "face_width_actual": safe_num(row[col["Фейс в шир факт"]]),
            }
            missing.append(record)
            existing.add(key)  # Track to handle duplicates within the file

    wb.close()
    print(f"  Found {len(missing)} missing records to upload", flush=True)

    if not missing:
        print("Nothing to upload!", flush=True)
        return

    print(f"\nStep 3: Uploading {len(missing)} missing records sequentially...", flush=True)
    t0 = time.time()
    errors = 0
    done = 0
    for i in range(0, len(missing), BATCH_SIZE):
        batch = missing[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE
        if not post_batch_with_verify("source_data", batch, batch_num):
            errors += 1
        done += len(batch)
        if done % 2000 == 0 or done == len(missing):
            print(f"  Progress: {done:,}/{len(missing):,} rows...", flush=True)
        time.sleep(0.1)

    elapsed = time.time() - t0
    print(f"\n  Done: {done:,} rows uploaded in {elapsed:.1f}s ({errors} errors)", flush=True)


if __name__ == "__main__":
    main()
