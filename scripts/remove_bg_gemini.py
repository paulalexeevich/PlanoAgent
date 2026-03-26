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
    """
    Remove background while preserving original pixels.

    IMPORTANT:
    Gemini image generation often "re-renders" the product even with strict prompts.
    To keep the exact original product pixels, we ask Gemini to output a *mask* only,
    then apply that mask as alpha onto the original image.
    """
    prompt = (
        "Create a precise, FILLED segmentation MASK for this product photo.\n"
        "- Output ONLY a mask image (no text).\n"
        "- White (255): the ENTIRE product silhouette (solid fill, NO holes).\n"
        "- Black (0): background.\n"
        "- The mask must cover all product parts (cap, label, glass, contents) as one solid region.\n"
        "- Keep the mask aligned pixel-perfect with the input (no crop / no resize).\n"
        "- Do NOT redraw or enhance the product; this is a mask only.\n"
        "- Clean edges; no halos.\n"
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
                    mask_img = Image.open(io.BytesIO(part.inline_data.data))
                    return _apply_mask_best_effort(image, mask_img)

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


def _mask_to_soft_alpha(m_gray):
    """Turn a grayscale mask into soft alpha. Avoid binary_opening — it eats thin jars/labels."""
    import numpy as np

    try:
        from scipy.ndimage import binary_closing, gaussian_filter

        hard = m_gray > 127
        # Closing fills small holes inside the product; no opening (that shrinks foreground).
        hard = binary_closing(hard, iterations=1)
        soft = gaussian_filter(hard.astype(np.float32), sigma=0.65)
        return (soft * 255.0).clip(0, 255).astype(np.uint8)
    except Exception:
        return (m_gray > 127).astype(np.uint8) * 255


def _score_rgba_foreground(rgba):
    """Higher = more plausible product cutout (coverage + not empty white sheet)."""
    import numpy as np

    h, w = rgba.shape[:2]
    a = rgba[:, :, 3]
    opaque = a > 28
    frac = opaque.mean()
    if frac < 0.025 or frac > 0.93:
        return -1.0
    if opaque.sum() < max(80, (h * w) // 500):
        return -1.0
    rgb = rgba[:, :, :3].astype(np.float32)
    gray = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2])
    # Studio background is ~255; real pack pixels are usually darker / more saturated.
    mean_l = float(gray[opaque].mean())
    std_l = float(gray[opaque].std())
    if mean_l > 249 and std_l < 8:
        return -0.5
    score = frac * (1.0 - mean_l / 255.0) * (1.0 + min(std_l / 64.0, 2.0))
    return score


def _apply_mask_to_original(original: Image.Image, mask_img: Image.Image, invert_mask: bool) -> Image.Image:
    """Apply mask as alpha. If invert_mask, use 255 - mask before thresholding."""
    import numpy as np

    orig = original.convert("RGBA")
    m = mask_img.convert("L")
    if m.size != orig.size:
        m = m.resize(orig.size, Image.BILINEAR)

    orig_a = np.array(orig, dtype=np.uint8)
    m_a = np.array(m, dtype=np.uint8)
    if invert_mask:
        m_a = 255 - m_a

    alpha = _mask_to_soft_alpha(m_a)
    out = orig_a.copy()
    out[:, :, 3] = alpha
    return Image.fromarray(out)


def _apply_mask_best_effort(original: Image.Image, mask_img: Image.Image) -> Image.Image:
    """
    Gemini mask convention varies (white=FG vs white=BG). Try both polarities, score
    composites, and compare to white-edge flood fill (good for studio white BG).
    """
    import numpy as np

    best_img = None
    best_score = -1.0
    for inv in (False, True):
        comp = _apply_mask_to_original(original, mask_img, invert_mask=inv)
        sc = _score_rgba_foreground(np.array(comp))
        if sc > best_score:
            best_score = sc
            best_img = comp

    flood = _white_to_transparent(original.convert("RGBA"))
    flood_sc = _score_rgba_foreground(np.array(flood))

    if flood_sc > best_score:
        return flood
    if best_score < 0.035:
        return flood
    return best_img


def _refine_cutout(img: Image.Image) -> Image.Image:
    """
    Clean edges for UI on dark backgrounds:
    - Drop semi-transparent near-white pixels (classic Gemini / flood-fill halos).
    - Light 1px alpha erosion to shave residual white rings.
    - Straighten RGB where alpha is 0 (avoid black premultiply confusion in some viewers).
    """
    import numpy as np

    data = np.array(img.convert("RGBA"), dtype=np.uint8)
    r, g, b, a = data[:, :, 0], data[:, :, 1], data[:, :, 2], data[:, :, 3]
    L = (0.299 * r + 0.587 * g + 0.114 * b).astype(np.float32)

    # Matte / halo: partly opaque but still "background white"
    halo = (a > 4) & (a < 254) & (L > 236)
    data[halo, 3] = 0

    # Very bright fringe with medium alpha
    halo2 = (a >= 40) & (a < 255) & (L > 245)
    data[halo2, 3] = 0

    try:
        from scipy.ndimage import binary_erosion

        hard = data[:, :, 3] > 200
        if hard.any() and hard.sum() > 30:
            eroded = binary_erosion(hard, iterations=1)
            trim = hard & ~eroded
            data[trim, 3] = 0
    except Exception:
        pass

    data[data[:, :, 3] == 0, 0:3] = 0
    return Image.fromarray(data)


def _strip_bright_surround_from_edges(img: Image.Image) -> Image.Image:
    """
    After masking, borders are often transparent so a plain white-edge flood never starts.
    Flood from the image rim through: transparent pixels OR bright neutral (studio matte),
    and clear alpha for the whole connected region. Removes opaque white rectangles around
    the product without re-downloading the source.
    """
    import numpy as np

    data = np.array(img.convert("RGBA"), dtype=np.uint8)
    h, w = data.shape[:2]
    r, g, b, a = data[:, :, 0], data[:, :, 1], data[:, :, 2], data[:, :, 3]
    rgb_max = np.maximum(np.maximum(r, g), b)
    rgb_min = np.minimum(np.minimum(r, g), b)
    chroma = (rgb_max - rgb_min).astype(np.int16)
    L = (0.299 * r + 0.587 * g + 0.114 * b).astype(np.float32)

    def is_clearable(y: int, x: int) -> bool:
        if a[y, x] < 42:
            return True
        if L[y, x] > 228 and chroma[y, x] < 38:
            return True
        return False

    visited = np.zeros((h, w), dtype=bool)
    queue = []
    for x in range(w):
        for y in (0, h - 1):
            if is_clearable(y, x) and not visited[y, x]:
                visited[y, x] = True
                queue.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if is_clearable(y, x) and not visited[y, x]:
                visited[y, x] = True
                queue.append((y, x))

    while queue:
        cy, cx = queue.pop()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = cy + dy, cx + dx
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and is_clearable(ny, nx):
                visited[ny, nx] = True
                queue.append((ny, nx))

    data[visited, 3] = 0
    data[visited, 0:3] = 0
    return Image.fromarray(data)


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

    # 1px boundary: make fully transparent (soft white fringe reads as halo on dark UI)
    from scipy.ndimage import binary_dilation
    dilated = binary_dilation(bg_mask, iterations=1)
    fringe = dilated & ~bg_mask
    data[fringe, 3] = 0

    return Image.fromarray(data)


def _bbox_for_opaque_core(img: Image.Image, alpha_floor: int = 56, pad: int = 2):
    """
    Tighter than Image.getbbox(): ignores very faint alpha (soft-mask dust / halos)
    so the product fills more of the export canvas and thumbnails don't look tiny.
    """
    import numpy as np

    a = np.array(img.convert("RGBA"))[:, :, 3]
    ys, xs = np.where(a > alpha_floor)
    if ys.size == 0:
        return img.getbbox()
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    h, w = a.shape
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(w, x1 + pad)
    y1 = min(h, y1 + pad)
    return (x0, y0, x1, y1)


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

    bbox = _bbox_for_opaque_core(img)
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

    # 2. Remove background via Gemini (mask on original pixels), or white-edge fallback
    print("  [2/4] Removing background via Gemini...", end=" ", flush=True)
    t0 = time.time()
    try:
        no_bg = remove_background(client, original)
    except RuntimeError as e:
        err = str(e).lower()
        if any(
            x in err
            for x in (
                "no candidates",
                "no image data",
                "malformed response",
                "failed after all retries",
            )
        ):
            print(f"\n  [2/4] Gemini unavailable ({e}); white-edge flood fill...", end=" ", flush=True)
            no_bg = _white_to_transparent(original.convert("RGBA"))
        else:
            raise
    elapsed = time.time() - t0
    print(f"OK ({no_bg.size[0]}×{no_bg.size[1]}, {elapsed:.1f}s)")

    no_bg = _refine_cutout(no_bg)
    no_bg = _strip_bright_surround_from_edges(no_bg)

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
