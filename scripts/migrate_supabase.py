#!/usr/bin/env python3
"""Migrate data between two Supabase projects using the REST API."""

import requests
import json
import time
import sys

SOURCE_URL = "https://mrbevgewrtgalaahcjog.supabase.co"
SOURCE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1yYmV2Z2V3cnRnYWxhYWhjam9nIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIzOTgwMTQsImV4cCI6MjA4Nzk3NDAxNH0.3kpL6Sen3X9bCFledYobgahOj3te5ZZmY6AJygdPvdc"

TARGET_URL = "https://zcciroutarcpkwpnynyh.supabase.co"
TARGET_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpjY2lyb3V0YXJjcGt3cG55bnloIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI3MjIzMTAsImV4cCI6MjA4ODI5ODMxMH0.LFnJ8WoxlNhZ06MBQm-1mmJK4mtkBLZAPd4UoPtGrkE"

TABLES_IN_ORDER = [
    "stores",
    "products",
    "recognition_photos",
    "recognition_raw_shelves",
    "recognition_raw_products",
    "recognition_assortment",
    "summary_data",
    "source_data",
]

BATCH_READ = 1000
BATCH_WRITE = 200
MAX_RETRIES = 5
DELAY_BETWEEN_BATCHES = 0.3


def read_all_rows(table: str) -> list[dict]:
    """Read all rows from a source table using pagination."""
    headers = {"apikey": SOURCE_KEY, "Authorization": f"Bearer {SOURCE_KEY}"}
    all_rows = []
    offset = 0
    while True:
        url = f"{SOURCE_URL}/rest/v1/{table}?select=*&order=id&limit={BATCH_READ}&offset={offset}"
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(url, headers=headers, timeout=60)
                break
            except requests.exceptions.RequestException as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** (attempt + 1)
                    print(f"  Read retry {attempt+1} after {wait}s: {e}")
                    time.sleep(wait)
                else:
                    print(f"  FATAL read error: {e}")
                    return all_rows
        if resp.status_code != 200:
            print(f"  ERROR reading {table} offset={offset}: {resp.status_code} {resp.text[:200]}")
            break
        rows = resp.json()
        if not rows:
            break
        all_rows.extend(rows)
        offset += len(rows)
        if offset % 10000 == 0:
            print(f"  Read {offset} rows so far...")
        if len(rows) < BATCH_READ:
            break
    return all_rows


def write_rows(table: str, rows: list[dict], start_from: int = 0) -> int:
    """Write rows to target table in batches with retry. Returns count of rows written."""
    headers = {
        "apikey": TARGET_KEY,
        "Authorization": f"Bearer {TARGET_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    total = start_from
    for i in range(start_from, len(rows), BATCH_WRITE):
        batch = rows[i : i + BATCH_WRITE]
        url = f"{TARGET_URL}/rest/v1/{table}"
        success = False
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.post(url, headers=headers, json=batch, timeout=60)
                if resp.status_code in (200, 201):
                    success = True
                    break
                elif resp.status_code == 409:
                    print(f"  Duplicate key at batch {i//BATCH_WRITE}, skipping")
                    success = True
                    break
                else:
                    print(f"  Write error {resp.status_code}, retry {attempt+1}")
                    time.sleep(2 ** (attempt + 1))
            except requests.exceptions.RequestException as e:
                wait = 2 ** (attempt + 1)
                print(f"  Connection error at batch {i//BATCH_WRITE}, retry {attempt+1} after {wait}s")
                time.sleep(wait)
        if not success:
            print(f"  FATAL: failed to write batch starting at row {i}")
            return total
        total += len(batch)
        if total % 5000 == 0 or total == len(rows):
            print(f"  {table}: {total}/{len(rows)} rows written")
        time.sleep(DELAY_BETWEEN_BATCHES)
    return total


def get_target_count(table: str) -> int:
    """Get current row count in target table."""
    headers = {"apikey": TARGET_KEY, "Authorization": f"Bearer {TARGET_KEY}", "Prefer": "count=exact"}
    url = f"{TARGET_URL}/rest/v1/{table}?select=id&limit=0"
    resp = requests.head(url, headers=headers, timeout=30)
    cr = resp.headers.get("content-range", "")
    if "/" in cr:
        return int(cr.split("/")[1])
    return 0


def migrate_table(table: str, resume: bool = False):
    print(f"\n--- Migrating {table} ---")
    t0 = time.time()

    start_from = 0
    if resume:
        start_from = get_target_count(table)
        if start_from > 0:
            print(f"  Resuming from row {start_from}")

    rows = read_all_rows(table)
    print(f"  Read {len(rows)} rows from source ({time.time()-t0:.1f}s)")
    if not rows:
        print("  Nothing to migrate.")
        return

    if start_from >= len(rows):
        print(f"  Already complete ({start_from} rows in target).")
        return

    written = write_rows(table, rows, start_from=start_from)
    elapsed = time.time() - t0
    print(f"  Wrote {written}/{len(rows)} rows to target ({elapsed:.1f}s)")


def main():
    resume = "--resume" in sys.argv
    tables = [a for a in sys.argv[1:] if not a.startswith("--")] or TABLES_IN_ORDER
    print(f"Migrating tables: {tables} (resume={resume})")
    print(f"Source: {SOURCE_URL}")
    print(f"Target: {TARGET_URL}\n")

    for table in tables:
        migrate_table(table, resume=resume)

    print("\n=== Migration complete ===")


if __name__ == "__main__":
    main()
