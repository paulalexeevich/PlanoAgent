#!/usr/bin/env python3
"""
Remove product image backgrounds using Gemini image generation.

Downloads product images from miniature_url, sends them to Gemini
for background removal, resizes to match physical cm proportions,
uploads PNGs to Supabase Storage, and saves the public URL.

Usage:
  python scripts/remove_bg_gemini.py              # process all
  python scripts/remove_bg_gemini.py --limit 3    # test with 3 products
  python scripts/remove_bg_gemini.py --art-id 329464 15309951  # specific products
"""

import argparse
import io
import os
import sys
import time

import requests
from PIL import Image
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://zcciroutarcpkwpnynyh.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpjY2lyb3V0YXJjcGt3cG55bnloIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3NzI3MjIzMTAsImV4cCI6MjA4ODI5ODMxMH0."
    "LFnJ8WoxlNhZ06MBQm-1mmJK4mtkBLZAPd4UoPtGrkE"
))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BUCKET = "product-images-no-bg"
TABLE = "test_coffee_product_map"
GEMINI_MODEL = "gemini-2.5-flash-image"
PIXELS_PER_CM = 40  # output resolution: 40px per cm → 14cm = 560px

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}


def get_gemini_client():
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set in environment / .env")
        sys.exit(1)
    return genai.Client(api_key=GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------
def fetch_products(limit=None, art_ids=None):
    """Fetch products that have a miniature_url and dimensions but no no-bg image yet."""
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    params = {
        "select": "id,art_id,tiny_name,width_cm,height_cm,miniature_url,image_no_bg_url",
        "miniature_url": "not.is.null",
        "width_cm": "gt.0",
        "height_cm": "gt.0",
    }
    if art_ids:
        params["art_id"] = f"in.({','.join(art_ids)})"
    else:
        params["image_no_bg_url"] = "is.null"

    if limit:
        params["limit"] = str(limit)

    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def upload_to_storage(file_bytes: bytes, path: str, content_type="image/png"):
    """Upload a file to Supabase Storage and return the public URL."""
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}"
    hdrs = {
        **HEADERS,
        "Content-Type": content_type,
        "x-upsert": "true",
    }
    resp = requests.post(url, headers=hdrs, data=file_bytes, timeout=60)
    resp.raise_for_status()
    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path}"
    return public_url


def update_product_url(row_id: int, public_url: str):
    """Update the image_no_bg_url column for a product."""
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}?id=eq.{row_id}"
    hdrs = {**HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"}
    resp = requests.patch(url, headers=hdrs, json={"image_no_bg_url": public_url}, timeout=30)
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------
def download_image(image_url: str) -> Image.Image:
    """Download an image from URL and return as PIL Image."""
    resp = requests.get(image_url, timeout=30)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content))


def remove_background(client, image: Image.Image, max_retries: int = 3) -> Image.Image:
    """Send image to Gemini for background removal, then convert white bg to transparent."""
    prompt = (
        "Remove the background from this product image completely. "
        "Keep ONLY the product itself with no background. "
        "Output the product on a pure white background. "
        "Do not crop or resize the product, preserve its original shape and details."
    )

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[prompt, image],
                config=types.GenerateContentConfig(
                    response_modalities=["Text", "Image"],
                ),
            )

            if not response.candidates or not response.candidates[0].content:
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
                raise RuntimeError("Gemini returned no candidates (safety filter or empty response)")

            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    gemini_img = Image.open(io.BytesIO(part.inline_data.data))
                    return _white_to_transparent(gemini_img)

            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            raise RuntimeError("Gemini response contained no image data")

        except AttributeError:
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            raise RuntimeError("Gemini returned malformed response after retries")

    raise RuntimeError("Failed after all retries")


def _white_to_transparent(img: Image.Image, tolerance: int = 20) -> Image.Image:
    """
    Convert white/near-white background pixels to transparent using flood-fill
    from edges. This only removes connected white regions touching the border,
    so white areas inside the product (labels, text) are preserved.
    """
    import numpy as np

    img = img.convert("RGBA")
    data = np.array(img)
    h, w = data.shape[:2]

    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
    is_white = (r > 255 - tolerance) & (g > 255 - tolerance) & (b > 255 - tolerance) & (a > 200)

    visited = np.zeros((h, w), dtype=bool)
    bg_mask = np.zeros((h, w), dtype=bool)

    # Seed from all border pixels that are white
    queue = []
    for x in range(w):
        for y in [0, h - 1]:
            if is_white[y, x] and not visited[y, x]:
                queue.append((y, x))
                visited[y, x] = True
    for y in range(h):
        for x in [0, w - 1]:
            if is_white[y, x] and not visited[y, x]:
                queue.append((y, x))
                visited[y, x] = True

    # BFS flood fill
    while queue:
        batch = queue
        queue = []
        for cy, cx in batch:
            bg_mask[cy, cx] = True
            for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and is_white[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((ny, nx))

    # Apply: make background fully transparent
    data[bg_mask, 3] = 0

    # Soften edges: semi-transparent fringe (1px dilation of bg boundary)
    from scipy.ndimage import binary_dilation
    dilated = binary_dilation(bg_mask, iterations=1)
    fringe = dilated & ~bg_mask
    data[fringe, 3] = (data[fringe, 3] * 0.4).astype(np.uint8)

    return Image.fromarray(data)


def resize_to_proportions(image: Image.Image, width_cm: float, height_cm: float) -> Image.Image:
    """
    Resize image to match physical cm proportions.
    Target pixel size = cm × PIXELS_PER_CM, maintaining aspect ratio
    by fitting inside the target box and then placing on transparent canvas.
    """
    target_w = int(round(width_cm * PIXELS_PER_CM))
    target_h = int(round(height_cm * PIXELS_PER_CM))

    if target_w < 10 or target_h < 10:
        target_w = max(target_w, 10)
        target_h = max(target_h, 10)

    img = image.convert("RGBA")

    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)

    src_w, src_h = img.size
    scale = min(target_w / src_w, target_h / src_h)
    new_w = int(round(src_w * scale))
    new_h = int(round(src_h * scale))
    img = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    x_offset = (target_w - new_w) // 2
    y_offset = (target_h - new_h) // 2
    canvas.paste(img, (x_offset, y_offset), img)

    return canvas


def image_to_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def process_product(client, product: dict) -> str:
    """Process a single product: download → remove bg → resize → upload → update DB."""
    art_id = product["art_id"]
    tiny_name = product.get("tiny_name") or art_id
    width_cm = float(product["width_cm"])
    height_cm = float(product["height_cm"])
    image_url = product["miniature_url"]

    print(f"\n{'─' * 60}")
    print(f"  Product: {tiny_name} (art_id={art_id})")
    print(f"  Dimensions: {width_cm} × {height_cm} cm")
    print(f"  Source: {image_url[:80]}...")

    # 1. Download
    print("  [1/4] Downloading original image...", end=" ", flush=True)
    original = download_image(image_url)
    print(f"OK ({original.size[0]}×{original.size[1]})")

    # 2. Remove background via Gemini
    print("  [2/4] Removing background via Gemini...", end=" ", flush=True)
    t0 = time.time()
    no_bg = remove_background(client, original)
    elapsed = time.time() - t0
    print(f"OK ({no_bg.size[0]}×{no_bg.size[1]}, {elapsed:.1f}s)")

    # 3. Resize to physical proportions
    target_w = int(round(width_cm * PIXELS_PER_CM))
    target_h = int(round(height_cm * PIXELS_PER_CM))
    print(f"  [3/4] Resizing to {target_w}×{target_h}px ({width_cm}×{height_cm}cm @ {PIXELS_PER_CM}px/cm)...", end=" ", flush=True)
    final = resize_to_proportions(no_bg, width_cm, height_cm)
    png_bytes = image_to_png_bytes(final)
    size_kb = len(png_bytes) / 1024
    print(f"OK ({size_kb:.0f} KB)")

    # 4. Upload to Supabase Storage
    storage_path = f"{art_id}.png"
    print(f"  [4/4] Uploading to storage/{BUCKET}/{storage_path}...", end=" ", flush=True)
    public_url = upload_to_storage(png_bytes, storage_path)
    print("OK")

    # 5. Update DB
    update_product_url(product["id"], public_url)
    print(f"  ✅ Saved: {public_url}")

    return public_url


def main():
    parser = argparse.ArgumentParser(description="Remove backgrounds from product images using Gemini")
    parser.add_argument("--limit", type=int, help="Max number of products to process")
    parser.add_argument("--art-id", nargs="+", help="Specific art_id(s) to process")
    args = parser.parse_args()

    print("=" * 60)
    print("  Product Image Background Removal (Gemini)")
    print("=" * 60)

    client = get_gemini_client()
    products = fetch_products(limit=args.limit, art_ids=args.art_id)

    if not products:
        print("\nNo products found to process.")
        print("(All products may already have image_no_bg_url set)")
        return

    print(f"\nFound {len(products)} products to process")

    success = 0
    errors = []

    for i, product in enumerate(products, 1):
        print(f"\n[{i}/{len(products)}]", end="")
        try:
            process_product(client, product)
            success += 1
        except Exception as e:
            art_id = product.get("art_id", "?")
            print(f"\n  ❌ ERROR for {art_id}: {e}")
            errors.append((art_id, str(e)))

        if i < len(products):
            time.sleep(2)

    print(f"\n{'=' * 60}")
    print(f"  Done! {success}/{len(products)} processed successfully")
    if errors:
        print(f"  Errors ({len(errors)}):")
        for art_id, err in errors:
            print(f"    - {art_id}: {err}")
    print("=" * 60)


if __name__ == "__main__":
    main()
