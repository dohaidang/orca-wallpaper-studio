"""Set the wallpaper of the "ASCII · My Wallpaper" Orca theme from any image file.

Usage: python -I set-wallpaper.py <image> [plugin-dir]

Accepts JPEG, PNG, WebP, BMP and GIF, static or animated. The image is converted to WebP inside the
plugin (Orca only reads theme backgrounds from inside the plugin folder), scaled to fit Orca's limits,
and the plugin is reloaded so the new wallpaper shows at once.
"""
import os
import subprocess
import sys

from PIL import Image, ImageSequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # isolated mode does not add it
import wallpaper_core as core  # noqa: E402

# Limits of the locally patched Orca build: animated WebP allowed, at most 16 MB.
# A stock Orca accepts only static images of at most 2 MB.
MAX_BYTES = 16 * 1024 * 1024
MIN_W, MIN_H, MAX_SIDE = 640, 360, 1920
MAX_FRAMES = 900


def fit(frame, max_side):
    frame = frame.convert('RGB')
    w, h = frame.size
    scale = min(1.0, max_side / max(w, h))
    scale = max(scale, MIN_W / w, MIN_H / h)
    if abs(scale - 1.0) > 1e-3:
        frame = frame.resize((max(MIN_W, round(w * scale)), max(MIN_H, round(h * scale))), Image.LANCZOS)
    return frame


def save_animated(src, out):
    durations, frames = [], []
    for i, frame in enumerate(ImageSequence.Iterator(src)):
        if i >= MAX_FRAMES:
            break
        frames.append(frame.copy())
        durations.append(max(20, int(frame.info.get('duration', src.info.get('duration', 50)) or 50)))
    for max_side in (MAX_SIDE, 1280, 960):
        fitted = [fit(f, max_side) for f in frames]
        for quality in (80, 65, 50, 40):
            fitted[0].save(out, save_all=True, append_images=fitted[1:], duration=durations, loop=0,
                           quality=quality, method=4)
            if os.path.getsize(out) <= MAX_BYTES:
                return len(fitted), fitted[0].size, quality
    raise SystemExit('The animation is too large even after shrinking. Try a shorter or smaller file.')


def save_static(src, out):
    for max_side in (MAX_SIDE, 1280):
        image = fit(src, max_side)
        for quality in (90, 75, 60):
            image.save(out, quality=quality, method=4)
            if os.path.getsize(out) <= MAX_BYTES:
                return 1, image.size, quality
    raise SystemExit('The image is too large even after shrinking.')


def main():
    if len(sys.argv) < 2:
        raise SystemExit('Drag an image file onto Doi-hinh-nen.bat, or run: python -I set-wallpaper.py <image>')
    source = sys.argv[1]
    # The My Wallpaper theme folder: the second argument, else WALLPAPER_THEMES_DIR, else the default folder in your home.
    plugin = core.ensure_theme_plugin(sys.argv[2]) if len(sys.argv) > 2 else core.themes_dir()
    out = os.path.join(plugin, 'images', 'custom.webp')
    tmp = out + '.tmp.webp'
    with Image.open(source) as src:
        animated = getattr(src, 'is_animated', False) and getattr(src, 'n_frames', 1) > 1
        frames, size, quality = (save_animated if animated else save_static)(src, tmp)
    os.replace(tmp, out)
    kind = f'animated, {frames} frames' if animated else 'static'
    print(f'Wallpaper set: {os.path.basename(source)} -> images/custom.webp '
          f'({size[0]}x{size[1]}, {kind}, quality {quality}, {os.path.getsize(out) / 1048576:.2f} MB)')
    print(core.reload_in_orca(plugin))
    print('In Orca, pick "My Wallpaper" (or re-pick it) under Settings > Appearance > Dark theme.')


if __name__ == '__main__':
    # Why: the Windows console may use a legacy code page that cannot print every character.
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
