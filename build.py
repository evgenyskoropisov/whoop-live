#!/usr/bin/env python3
"""
Генерирует AppIcon.icns и собирает WHOOP Live.app
Запуск: python build.py
"""
import subprocess, sys, os, struct, zlib, shutil
from pathlib import Path

DIR = Path(__file__).parent

# ── 1. Генерируем PNG иконку через Python (без внешних зависимостей) ───────────

def make_png(size):
    """Рисуем минималистичную иконку: тёмный круг + сердце."""
    import math

    W = H = size
    img = []

    def lerp(a, b, t): return a + (b - a) * t
    def clamp(v, lo, hi): return max(lo, min(hi, v))

    for y in range(H):
        row = []
        for x in range(W):
            cx, cy = x - W/2, y - H/2
            dist = math.sqrt(cx*cx + cy*cy) / (W/2)

            # Background gradient: deep navy
            bg_r = int(lerp(7,  14, clamp(dist, 0, 1)))
            bg_g = int(lerp(8,  15, clamp(dist, 0, 1)))
            bg_b = int(lerp(15, 26, clamp(dist, 0, 1)))

            # Outer circle alpha mask
            alpha = 255
            if dist > 1.0:
                alpha = 0
            elif dist > 0.92:
                alpha = int(255 * (1.0 - dist) / 0.08)

            # Heart shape (normalized coords -1..1)
            nx = cx / (W * 0.32)
            ny = -(cy / (H * 0.32)) + 0.18   # shift up slightly

            # Heart formula
            hv = (nx*nx + ny*ny - 1)**3 - nx*nx * ny*ny*ny
            in_heart = hv <= 0

            if in_heart:
                # Heart gradient: coral -> orange-red
                heart_t = clamp((ny + 1) / 2, 0, 1)
                r = int(lerp(255, 220, heart_t))
                g = int(lerp(77,  50,  heart_t))
                b = int(lerp(109, 80,  heart_t))

                # Glow blend
                glow = clamp(1.0 - hv * 2, 0, 1) * 0.3
                r = clamp(int(r + glow * 255), 0, 255)
                g = clamp(int(g + glow * 100), 0, 255)
                b = clamp(int(b + glow * 120), 0, 255)
            else:
                r, g, b = bg_r, bg_g, bg_b

            row.append((r, g, b, alpha))
        img.append(row)

    # Encode as PNG
    def png_chunk(tag, data):
        c = zlib.crc32(tag + data) & 0xffffffff
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", c)

    raw = b""
    for row in img:
        raw += b"\x00"  # filter type none
        for r, g, b, a in row:
            raw += bytes([r, g, b, a])
    compressed = zlib.compress(raw, 9)

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0)
    png  = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", ihdr)
    png += png_chunk(b"IDAT", compressed)
    png += png_chunk(b"IEND", b"")
    return png


print("🎨 Generating icon...")

sizes = [16, 32, 64, 128, 256, 512, 1024]
iconset_dir = DIR / "AppIcon.iconset"
iconset_dir.mkdir(exist_ok=True)

for s in sizes:
    png_data = make_png(s)
    (iconset_dir / f"icon_{s}x{s}.png").write_bytes(png_data)
    if s <= 512:
        (iconset_dir / f"icon_{s}x{s}@2x.png").write_bytes(make_png(s * 2))

# Convert iconset → icns using macOS iconutil
result = subprocess.run(
    ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(DIR / "AppIcon.icns")],
    capture_output=True, text=True
)
if result.returncode != 0:
    print(f"⚠  iconutil failed: {result.stderr}")
    print("   Continuing without .icns (app will use default icon)")
else:
    print("✅ AppIcon.icns created")

shutil.rmtree(iconset_dir, ignore_errors=True)

# ── 2. Устанавливаем зависимости ───────────────────────────────────────────────
print("\n📦 Installing dependencies...")
deps = ["flask", "bleak", "pywebview", "py2app"]
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q"] + deps)
print("✅ Dependencies ready")

# ── 3. Собираем .app ──────────────────────────────────────────────────────────
print("\n🔨 Building WHOOP Live.app ...")
os.chdir(DIR)

# Clean previous build
for d in ["build", "dist"]:
    if Path(d).exists():
        shutil.rmtree(d)

result = subprocess.run(
    [sys.executable, "setup.py", "py2app"],
    capture_output=False
)

app_path = DIR / "dist" / "WHOOP Live.app"
if app_path.exists():
    print(f"\n✅  Done!  App is at:\n    {app_path}")
    print("\n   To install: drag to /Applications")
    print("   To run now: open dist/WHOOP\\ Live.app\n")
else:
    print("\n❌  Build failed. Check errors above.")
    sys.exit(1)
