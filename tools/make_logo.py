"""
Draws the Firewatch logo and every icon size the app needs. Run from the project folder:

    python tools/make_logo.py

Writes into assets/ (Flet serves that folder, and files there replace Flet's own favicon,
app icons and loading-screen image):

    logo.png, logo_mark.png, logo_wordmark.png     badge, flame only, badge + name
    favicon.png, icon.png, icon.ico, splash.png    browser tab, desktop window, packaged apps
    icons/icon-192.png, icon-512.png               installable-app icons
    icons/icon-maskable-192.png, -512.png          same, full-bleed for Android
    icons/apple-touch-icon-192.png                 iPhone home screen
    icons/loading-animation.png                    shown while the app loads
    manifest.json                                  app name and colours for "install app"

Needs Pillow (pip install pillow). Change the colours below to restyle the logo.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SS = 4                                   # draw 4x bigger, then shrink for smooth edges

NAVY_TOP, NAVY_BOTTOM = (28, 48, 108), (9, 20, 52)
FLAME_OUTER = ((255, 59, 48), (255, 140, 26))        # top -> bottom
FLAME_MID = ((255, 140, 26), (255, 196, 61))
FLAME_INNER = ((255, 214, 102), (255, 245, 200))


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vgradient(size, top, bottom):
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    for y in range(size[1]):
        d.line([(0, y), (size[0], y)], fill=lerp(top, bottom, y / max(1, size[1] - 1)))
    return img


def flame_points(cx, base_y, height, width, lean, n=160):
    """Outline of one flame: round at the bottom, curved to a point at the top, tip leaning right."""
    left, right = [], []
    for i in range(n + 1):
        u = i / n
        y = base_y - height * u
        w = width * 2.43 * (u ** 0.5) * ((1 - u) ** 0.85)
        xc = cx + lean * (u ** 2.2)
        left.append((xc - w, y))
        right.append((xc + w, y))
    return left + right[::-1]


def fill_shape(canvas, points, top, bottom, bbox):
    """Paint a polygon with a vertical colour gradient."""
    mask = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    grad = Image.new("RGB", canvas.size)
    y0, y1 = bbox
    grad.paste(vgradient((canvas.size[0], max(1, int(y1 - y0))), top, bottom), (0, int(y0)))
    canvas.paste(grad, (0, 0), mask)


def draw_flame(size):
    """The flame on a transparent square of `size` pixels."""
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    cx, base = s * 0.5, s * 0.93
    h, w = s * 0.86, s * 0.235
    # main flame and a smaller lick on the left, same colour so they merge into one shape
    layers = [
        (flame_points(cx, base, h, w, s * 0.10), FLAME_OUTER, (base - h, base)),
        (flame_points(cx - s * 0.205, base - s * 0.01, h * 0.52, w * 0.52, -s * 0.07), FLAME_OUTER, (base - h * 0.62, base)),
        (flame_points(cx + s * 0.015, base - s * 0.035, h * 0.64, w * 0.60, s * 0.055), FLAME_MID, (base - h * 0.7, base)),
        (flame_points(cx + s * 0.01, base - s * 0.07, h * 0.37, w * 0.34, s * 0.025), FLAME_INNER, (base - h * 0.45, base)),
    ]
    for pts, (top, bottom), bbox in layers:
        layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        fill_shape(layer, pts, top, bottom, bbox)
        img = Image.alpha_composite(img, layer)
    return img.resize((size, size), Image.LANCZOS)


def badge(size, full_bleed=False, flame_scale=0.68):
    """Navy rounded square with the flame. full_bleed=True fills the whole square (maskable icons)."""
    s = size * SS
    bg = vgradient((s, s), NAVY_TOP, NAVY_BOTTOM).convert("RGBA")
    if not full_bleed:
        mask = Image.new("L", (s, s), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.225), fill=255)
        bg.putalpha(mask)
    ring = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    if not full_bleed:
        ImageDraw.Draw(ring).rounded_rectangle([SS, SS, s - SS - 1, s - SS - 1], radius=int(s * 0.225) - SS,
                                               outline=(255, 255, 255, 38), width=SS * 2)
    bg = Image.alpha_composite(bg, ring).resize((size, size), Image.LANCZOS)
    fsize = int(size * flame_scale)
    flame = draw_flame(fsize)
    bg.alpha_composite(flame, ((size - fsize) // 2, int(size * 0.5 - fsize * 0.5 - size * 0.015)))
    return bg


def wordmark(height=240):
    """Badge + the word Firewatch, for the README and the sign-in screens."""
    mark = badge(height)
    font_path = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"
    try:
        font = ImageFont.truetype(font_path, int(height * 0.5))
    except OSError:
        font = ImageFont.load_default()
    text = "Firewatch"
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    tw = probe.textlength(text, font=font)
    img = Image.new("RGBA", (int(height + height * 0.18 + tw + 10), height), (0, 0, 0, 0))
    img.alpha_composite(mark, (0, 0))
    ImageDraw.Draw(img).text((height + height * 0.18, height * 0.5), text, font=font, fill=(14, 27, 63, 255), anchor="lm")
    return img


def main():
    (ASSETS / "icons").mkdir(parents=True, exist_ok=True)
    save = lambda im, name: im.save(ASSETS / name, optimize=True)

    save(draw_flame(512), "logo_mark.png")
    save(badge(512), "logo.png")
    save(wordmark(240), "logo_wordmark.png")
    save(badge(64, flame_scale=0.76), "favicon.png")
    save(badge(256), "icon.png")
    save(badge(512), "splash.png")
    badge(256).save(ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    save(badge(192), "icons/icon-192.png")
    save(badge(512), "icons/icon-512.png")
    save(badge(192, full_bleed=True, flame_scale=0.5), "icons/icon-maskable-192.png")
    save(badge(512, full_bleed=True, flame_scale=0.5), "icons/icon-maskable-512.png")
    badge(192, full_bleed=True, flame_scale=0.56).convert("RGB").save(ASSETS / "icons/apple-touch-icon-192.png", optimize=True)
    save(badge(512), "icons/loading-animation.png")

    manifest = {
        "name": "Firewatch", "short_name": "Firewatch", "start_url": ".", "display": "standalone",
        "background_color": "#F5F7FB", "theme_color": "#0E1B3F",
        "description": "Live wildfire detection and alerts for South Africa",
        "orientation": "natural", "prefer_related_applications": False,
        "icons": [
            {"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "icons/icon-maskable-192.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": "icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    (ASSETS / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Wrote the logo and icons to", ASSETS)


if __name__ == "__main__":
    main()
