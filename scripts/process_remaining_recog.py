#!/usr/bin/env python3
"""Process recognition-only products that aren't in test_coffee_product_map."""
import json, io, os, time, sys
import requests
from PIL import Image
from dotenv import load_dotenv
from google import genai
from google.genai import types
import numpy as np
from scipy.ndimage import binary_dilation

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://zcciroutarcpkwpnynyh.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpjY2lyb3V0YXJjcGt3cG55bnloIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3NzI3MjIzMTAsImV4cCI6MjA4ODI5ODMxMH0."
    "LFnJ8WoxlNhZ06MBQm-1mmJK4mtkBLZAPd4UoPtGrkE"
))
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
BUCKET = "product-images-no-bg"
PPC = 40

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

with open("/tmp/missing_products.json") as f:
    products = json.load(f)


def white_to_transparent(img, tolerance=20):
    img = img.convert("RGBA")
    data = np.array(img)
    h, w = data.shape[:2]
    is_white = ((data[:,:,0] > 255 - tolerance) & (data[:,:,1] > 255 - tolerance)
                & (data[:,:,2] > 255 - tolerance) & (data[:,:,3] > 200))
    visited = np.zeros((h, w), dtype=bool)
    bg_mask = np.zeros((h, w), dtype=bool)
    queue = []
    for x in range(w):
        for y in [0, h - 1]:
            if is_white[y, x] and not visited[y, x]:
                queue.append((y, x)); visited[y, x] = True
    for y in range(h):
        for x in [0, w - 1]:
            if is_white[y, x] and not visited[y, x]:
                queue.append((y, x)); visited[y, x] = True
    while queue:
        batch = queue; queue = []
        for cy, cx in batch:
            bg_mask[cy, cx] = True
            for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and is_white[ny, nx]:
                    visited[ny, nx] = True; queue.append((ny, nx))
    data[bg_mask, 3] = 0
    dilated = binary_dilation(bg_mask, iterations=1)
    fringe = dilated & ~bg_mask
    data[fringe, 3] = (data[fringe, 3] * 0.4).astype(np.uint8)
    return Image.fromarray(data)


print(f"Processing {len(products)} recognition-only products...\n")
success = 0
errors = []

for i, p in enumerate(products, 1):
    rid = p["recognition_id"]
    safe_name = rid.replace("/", "_")
    print(f"[{i}/{len(products)}] {p['name']} ({rid[:25]})...", end=" ", flush=True)
    try:
        resp = requests.get(p["miniature_url"], timeout=30)
        resp.raise_for_status()
        orig = Image.open(io.BytesIO(resp.content))

        gemini_img = None
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash-image",
                    contents=["Remove the background from this product image. Keep only the product on a white background.", orig],
                    config=types.GenerateContentConfig(response_modalities=["Text", "Image"]),
                )
                if response.candidates and response.candidates[0].content:
                    for part in response.candidates[0].content.parts:
                        if part.inline_data:
                            gemini_img = Image.open(io.BytesIO(part.inline_data.data))
                            break
                if gemini_img:
                    break
            except Exception:
                pass
            time.sleep(3)

        if not gemini_img:
            raise RuntimeError("Gemini failed after 3 retries")

        no_bg = white_to_transparent(gemini_img)

        tw = max(int(round(p["width_cm"] * PPC)), 10)
        th = max(int(round(p["height_cm"] * PPC)), 10)
        no_bg = no_bg.convert("RGBA")
        bbox = no_bg.getbbox()
        if bbox:
            no_bg = no_bg.crop(bbox)
        sw, sh = no_bg.size
        scale = min(tw / sw, th / sh)
        nw, nh = int(round(sw * scale)), int(round(sh * scale))
        no_bg = no_bg.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        canvas.paste(no_bg, ((tw - nw) // 2, (th - nh) // 2), no_bg)

        buf = io.BytesIO()
        canvas.save(buf, format="PNG", optimize=True)
        png = buf.getvalue()

        storage_path = f"recog_{safe_name}.png"
        url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{storage_path}"
        r = requests.post(url, headers={**HEADERS, "Content-Type": "image/png", "x-upsert": "true"},
                         data=png, timeout=60)
        r.raise_for_status()
        pub_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{storage_path}"

        row = {
            "art_id": f"_RECOG_{safe_name}",
            "recognition_id": rid,
            "tiny_name": p["name"],
            "product_name": p["name"],
            "width_cm": p["width_cm"],
            "height_cm": p["height_cm"],
            "miniature_url": p["miniature_url"],
            "image_no_bg_url": pub_url,
        }
        r2 = requests.post(f"{SUPABASE_URL}/rest/v1/test_coffee_product_map",
            headers={**HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"},
            json=row, timeout=30)
        r2.raise_for_status()

        print(f"OK ({len(png) // 1024}KB)")
        success += 1
    except Exception as e:
        print(f"ERROR: {e}")
        errors.append((rid, str(e)))

    if i < len(products):
        time.sleep(2)

print(f"\nDone! {success}/{len(products)} processed")
if errors:
    print(f"Errors ({len(errors)}):")
    for rid, err in errors:
        print(f"  {rid}: {err}")
