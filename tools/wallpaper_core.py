"""Image processing for the Orca "ASCII · My Wallpaper" slots, with no user interface.

Everything the Wallpaper Studio window does to a picture lives here so it can be tested on its own:
input limits, rotate/flip/crop, brightness/blur/darken, encoding under a size budget, checking the
result against Orca's rules, writing the slot's theme files and keeping a library copy.
"""
import io
import json
import os
import shutil
import sqlite3
import subprocess
from dataclasses import asdict, dataclass, field

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageSequence

def _appdata():
    """%APPDATA%, or its usual location when a restricted environment (such as an Orca worker) drops it."""
    return os.environ.get('APPDATA') or os.path.join(os.environ.get('USERPROFILE', os.path.expanduser('~')), 'AppData', 'Roaming')


def themes_dir():
    """Folder of the ASCII Themes plugin that holds the My Wallpaper themes (a local copy of its `animated`
    branch). The Orca plugin passes its "ASCII Themes folder" setting as ASCII_THEMES_DIR; the desktop tool
    reads the same environment variable."""
    folder = os.environ.get('ASCII_THEMES_DIR', '').strip()
    if not folder or not os.path.isfile(os.path.join(folder, 'orca-plugin.json')):
        raise WallpaperError(msg('no_themes_dir'))
    return folder


# Saved copies of the user's pictures live outside the plugin, so updating or reinstalling it keeps them.
LIBRARY_DIR = os.environ.get('WALLPAPER_STUDIO_LIBRARY') or os.path.join(_appdata(), 'orca-wallpaper-studio', 'library')

# slot number -> (theme id prefix, image stem); each slot has three theme files (sidebar variants)
SLOTS = {1: ('my-wallpaper', 'custom'), 2: ('my-wallpaper-2', 'custom-2'), 3: ('my-wallpaper-3', 'custom-3')}
VARIANT_SUFFIXES = ('', '-sidebar-dark', '-sidebar-light')

# Input limits: refuse files that would freeze the tool before any heavy work starts.
MAX_INPUT_BYTES = 50 * 1024 * 1024
MAX_INPUT_SIDE = 8000
MAX_FRAMES = 900
MAX_SECONDS = 60
MAX_ANIMATED_PIXELS = 2_000_000_000  # width * height * frames held in memory

# Output rules. "stock" matches an unmodified Orca; "patched" matches the locally patched build.
MODES = {
    'patched': {'label': 'Orca đã vá: tĩnh hoặc động, tối đa 16 MB', 'max_bytes': 16 * 1024 * 1024, 'animated': True},
    'stock': {'label': 'Orca chuẩn: chỉ ảnh tĩnh, tối đa 2 MB', 'max_bytes': 2 * 1024 * 1024, 'animated': False},
}
MIN_W, MIN_H, MAX_SIDE = 640, 360, 4096
SIZES = ('cover', 'contain', 'tile')
POSITIONS = ('center', 'top', 'bottom', 'left', 'right')


# ---------- user-facing messages ----------
# Each entry is (Vietnamese, English). The Orca panel passes Orca's UI language in the edit settings
# ("lang"); the desktop tool and the tests keep the Vietnamese default.
LANG = 'vi'
_MESSAGES = {
    'not_found': ('Không tìm thấy file.', 'File not found.'),
    'file_too_big': ('File lớn hơn {mb} MB.', 'The file is larger than {mb} MB.'),
    'cannot_read': ('Không đọc được ảnh: {error}', 'Could not read the image: {error}'),
    'image_too_big': ('Ảnh lớn hơn {side}×{side} px.', 'The image is larger than {side}×{side} px.'),
    'anim_frames': ('Ảnh động có {frames} khung, tối đa {max}.', 'The animation has {frames} frames; the limit is {max}.'),
    'anim_long': ('Ảnh động dài {seconds} giây, tối đa {max} giây.', 'The animation is {seconds} seconds long; the limit is {max} seconds.'),
    'anim_huge': ('Ảnh động quá lớn để xử lý. Hãy dùng file nhỏ hoặc ngắn hơn.', 'The animation is too large to process. Use a smaller or shorter file.'),
    'reduced_stock': ('chế độ Orca chuẩn chỉ nhận ảnh tĩnh, nên lấy khung đầu tiên', 'stock Orca accepts still images only, so the first frame is used'),
    'exporting': ('Đang xuất: {w}×{h}, chất lượng {q}…', 'Exporting: {w}×{h}, quality {q}…'),
    'reduced_quality': ('giảm chất lượng xuống {q}', 'quality lowered to {q}'),
    'reduced_size': ('thu nhỏ còn {w}×{h}', 'scaled down to {w}×{h}'),
    'reduced_frames': ('bỏ bớt một nửa số khung hình', 'dropped half of the frames'),
    'cannot_compress': ('Không thể nén xuống dưới {mb} MB. Hãy cắt ngắn hoặc giảm kích thước.', 'Could not compress it below {mb} MB. Trim it or reduce its size.'),
    'out_not_webp': ('ảnh xuất không phải WebP', 'the exported file is not WebP'),
    'out_over': ('ảnh xuất {size} MB, vượt {mb} MB', 'the exported file is {size} MB, over {mb} MB'),
    'out_range': ('ảnh xuất {w}×{h}, ngoài khoảng {minw}×{minh} đến {max}×{max}', 'the exported size {w}×{h} is outside {minw}×{minh} to {max}×{max}'),
    'out_stock_anim': ('chế độ Orca chuẩn không nhận ảnh động', 'stock Orca does not accept animated images'),
    'out_invalid': ('Ảnh xuất không hợp lệ: {problem}', 'The exported image is not valid: {problem}'),
    'reloading': ('Đang nạp lại plugin trong Orca…', 'Reloading the plugin in Orca…'),
    'kind_animated': ('động, {n} khung', 'animated, {n} frames'),
    'kind_still': ('tĩnh', 'still'),
    'bad_params': ('Thông số không hợp lệ.', 'Invalid settings.'),
    'bad_slot': ('Ô hình nền không hợp lệ.', 'Invalid wallpaper slot.'),
    'no_themes_dir': ('Chưa chọn thư mục plugin ASCII Themes. Hãy đặt ô "ASCII Themes folder" trong cài đặt plugin (một bản sao nhánh animated có sẵn các theme My Wallpaper).', 'The ASCII Themes folder is not set. Set "ASCII Themes folder" in the plugin settings (a local copy of the animated branch, which has the My Wallpaper themes).'),
    'no_python': ('Không tìm thấy Python có Pillow. Hãy cài Python 3 rồi chạy "pip install Pillow", hoặc nhập đường dẫn python.exe trong cài đặt plugin.', 'No Python with Pillow was found. Install Python 3 and run "pip install Pillow", or enter the path of python.exe in the plugin settings.'),
    'usage': ('Cách dùng: wallpaper_cli.py apply <ảnh> <ô> <edit.json> | env', 'Usage: wallpaper_cli.py apply <image> <slot> <edit.json> | env'),
}


def set_language(code):
    """Vietnamese for "vi", English for every other language."""
    global LANG
    LANG = 'vi' if str(code or 'vi').lower().startswith('vi') else 'en'


def msg(key, **values):
    vietnamese, english = _MESSAGES[key]
    return (vietnamese if LANG == 'vi' else english).format(**values)



class WallpaperError(Exception):
    """A problem the user can fix (bad file, over a limit); its message is shown as is."""


@dataclass
class Edit:
    """Every choice the user makes for one wallpaper; saved with the library copy."""
    rotate: int = 0               # 0, 90, 180, 270 degrees clockwise
    flip_h: bool = False
    flip_v: bool = False
    crop: list = field(default_factory=list)  # [left, top, right, bottom] in rotated-image pixels; empty = whole image
    out_w: int = 1920
    out_h: int = 1080
    brightness: float = 1.0       # 0.5 .. 1.5
    darken: float = 0.0           # 0 .. 0.8, blends towards black so terminal text stays readable
    blur: float = 0.0             # 0 .. 10 px gaussian radius, at output size
    opacity: float = 1.0          # theme background.opacity
    size: str = 'cover'
    position: str = 'center'
    mode: str = 'patched'
    speed: float = 1.0            # animated only: 2.0 plays twice as fast
    first_frame: int = 0          # animated only: trim
    last_frame: int = -1          # animated only: -1 = last frame
    frame_step: int = 1           # animated only: keep every Nth frame


@dataclass
class SourceInfo:
    path: str
    width: int
    height: int
    frames: int
    seconds: float
    animated: bool


def inspect_source(path):
    """Open an image just far enough to check it against the input limits."""
    if not os.path.isfile(path):
        raise WallpaperError(msg('not_found'))
    if os.path.getsize(path) > MAX_INPUT_BYTES:
        raise WallpaperError(msg('file_too_big', mb=MAX_INPUT_BYTES // 1048576))
    try:
        with Image.open(path) as im:
            w, h = im.size
            frames = getattr(im, 'n_frames', 1)
            animated = bool(getattr(im, 'is_animated', False)) and frames > 1
            seconds = 0.0
            if animated:
                for frame in ImageSequence.Iterator(im):
                    seconds += (frame.info.get('duration', im.info.get('duration', 50)) or 50) / 1000
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise WallpaperError(msg('cannot_read', error=error)) from error
    if max(w, h) > MAX_INPUT_SIDE:
        raise WallpaperError(msg('image_too_big', side=MAX_INPUT_SIDE))
    if animated and frames > MAX_FRAMES:
        raise WallpaperError(msg('anim_frames', frames=frames, max=MAX_FRAMES))
    if animated and seconds > MAX_SECONDS:
        raise WallpaperError(msg('anim_long', seconds=f'{seconds:.0f}', max=MAX_SECONDS))
    if animated and w * h * frames > MAX_ANIMATED_PIXELS:
        raise WallpaperError(msg('anim_huge'))
    return SourceInfo(path, w, h, frames, seconds, animated)


def oriented_size(info, edit):
    return (info.height, info.width) if edit.rotate in (90, 270) else (info.width, info.height)


def orient(frame, edit):
    frame = frame.convert('RGB')
    if edit.rotate:
        frame = frame.rotate(-edit.rotate, expand=True)
    if edit.flip_h:
        frame = ImageOps.mirror(frame)
    if edit.flip_v:
        frame = ImageOps.flip(frame)
    return frame


def centered_crop(width, height, aspect):
    """The largest crop of the given aspect (width / height) centred in the image."""
    if aspect is None or aspect <= 0:
        return [0, 0, width, height]
    if width / height > aspect:
        cw, ch = round(height * aspect), height
    else:
        cw, ch = width, round(width / aspect)
    left, top = (width - cw) // 2, (height - ch) // 2
    return [left, top, left + cw, top + ch]


def clamp_output(width, height):
    """Scale an output size into Orca's 640×360 .. 4096×4096 window, keeping its aspect."""
    scale = min(1.0, MAX_SIDE / max(width, height))
    scale = max(scale, MIN_W / width, MIN_H / height)
    width, height = round(width * scale), round(height * scale)
    return min(MAX_SIDE, max(MIN_W, width)), min(MAX_SIDE, max(MIN_H, height))


def render_frame(frame, edit, scale=1.0):
    """Apply orientation, crop and adjustments; scale < 1 renders a smaller copy for previews."""
    image = orient(frame, edit)
    if edit.crop:
        image = image.crop(tuple(edit.crop))
    size = (max(1, round(edit.out_w * scale)), max(1, round(edit.out_h * scale)))
    image = image.resize(size, Image.LANCZOS)
    if abs(edit.brightness - 1.0) > 1e-3:
        image = ImageEnhance.Brightness(image).enhance(edit.brightness)
    if edit.blur > 0:
        image = image.filter(ImageFilter.GaussianBlur(edit.blur * scale))
    if edit.darken > 0:
        image = Image.blend(image, Image.new('RGB', image.size, (0, 0, 0)), edit.darken)
    return image


def source_frames(path, edit):
    """(frame, duration ms) pairs after trimming, frame stepping and the speed change."""
    with Image.open(path) as im:
        items = [(frame.copy(), frame.info.get('duration', im.info.get('duration', 50)) or 50)
                 for frame in ImageSequence.Iterator(im)]
    last = len(items) - 1 if edit.last_frame < 0 else min(edit.last_frame, len(items) - 1)
    first = max(0, min(edit.first_frame, last))
    step = max(1, edit.frame_step)
    picked = []
    for i in range(first, last + 1, step):
        duration = sum(d for _, d in items[i:i + step])
        picked.append((items[i][0], max(20, round(duration / max(0.1, edit.speed)))))
    return picked


def encode(info, edit, out_path, progress=lambda text: None):
    """Write a WebP that fits the mode's rules, shrinking quality, size and frames as needed.

    Returns a list of what was reduced, for the user. Raises WallpaperError if nothing fits.
    """
    mode = MODES[edit.mode]
    animated = info.animated and mode['animated']
    reduced = []
    frames = source_frames(info.path, edit) if animated else None
    if info.animated and not mode['animated']:
        reduced.append(msg('reduced_stock'))
    with Image.open(info.path) as im:
        if not animated:
            im.seek(min(max(0, edit.first_frame), getattr(im, 'n_frames', 1) - 1) if info.animated else 0)
            still = im.copy()
    for scale in (1.0, 0.85, 0.7, 0.55):
        for quality in (90, 80, 70, 60, 50, 40):
            progress(msg('exporting', w=round(edit.out_w * scale), h=round(edit.out_h * scale), q=quality))
            if animated:
                rendered = [render_frame(f, edit, scale) for f, _ in frames]
                rendered[0].save(out_path, 'WEBP', save_all=True, append_images=rendered[1:],
                                 duration=[d for _, d in frames], loop=0, quality=quality, method=4)
            else:
                render_frame(still, edit, scale).save(out_path, 'WEBP', quality=quality, method=4)
            if os.path.getsize(out_path) <= mode['max_bytes'] and round(edit.out_w * scale) >= MIN_W and round(edit.out_h * scale) >= MIN_H:
                if quality < 90:
                    reduced.append(msg('reduced_quality', q=quality))
                if scale < 1:
                    reduced.append(msg('reduced_size', w=round(edit.out_w * scale), h=round(edit.out_h * scale)))
                return reduced
        if animated and len(frames) > 2 and scale >= 0.7:
            frames = [(f, d * 2) for f, d in frames[::2]]
            reduced.append(msg('reduced_frames'))
    raise WallpaperError(msg('cannot_compress', mb=mode["max_bytes"] // 1048576))


def check_output(path, mode_name):
    """Re-open the written file and check it against the mode's rules; returns None or the problem."""
    mode = MODES[mode_name]
    size = os.path.getsize(path)
    with Image.open(path) as im:
        w, h = im.size
        animated = bool(getattr(im, 'is_animated', False))
        fmt = im.format
    if fmt != 'WEBP':
        return msg('out_not_webp')
    if size > mode['max_bytes']:
        return msg('out_over', size=f'{size / 1048576:.2f}', mb=mode["max_bytes"] // 1048576)
    if w < MIN_W or h < MIN_H or max(w, h) > MAX_SIDE:
        return msg('out_range', w=w, h=h, minw=MIN_W, minh=MIN_H, max=MAX_SIDE)
    if animated and not mode['animated']:
        return msg('out_stock_anim')
    return None


def write_slot_themes(slot, edit, plugin_dir=None):
    plugin_dir = plugin_dir or themes_dir()
    prefix, stem = SLOTS[slot]
    file_stem = 'custom' if slot == 1 else f'custom-{slot}'
    for suffix in VARIANT_SUFFIXES:
        path = os.path.join(plugin_dir, 'themes', f'{file_stem}{suffix}.json')
        with io.open(path, encoding='utf8') as f:
            theme = json.load(f)
        theme['background'] = {'path': f'images/{stem}.webp', 'opacity': round(edit.opacity, 2),
                               'size': edit.size, 'position': edit.position}
        with io.open(path, 'w', encoding='utf8') as f:
            f.write(json.dumps(theme, indent=2, ensure_ascii=False) + '\n')


def save_library(slot, info, edit):
    folder = os.path.join(LIBRARY_DIR, f'slot-{slot}')
    os.makedirs(folder, exist_ok=True)
    ext = os.path.splitext(info.path)[1].lower() or '.img'
    target = os.path.join(folder, 'source' + ext)
    for name in os.listdir(folder):
        if name.startswith('source') and os.path.join(folder, name) != target:
            os.remove(os.path.join(folder, name))
    if os.path.abspath(info.path) != os.path.abspath(target):
        shutil.copyfile(info.path, target)
    with io.open(os.path.join(folder, 'settings.json'), 'w', encoding='utf8') as f:
        json.dump({'source': os.path.basename(target), 'original': info.path, 'edit': asdict(edit)}, f, indent=2, ensure_ascii=False)
    return target


def load_library(slot):
    """(source path, Edit) saved for a slot, or None."""
    folder = os.path.join(LIBRARY_DIR, f'slot-{slot}')
    settings = os.path.join(folder, 'settings.json')
    if not os.path.isfile(settings):
        return None
    with io.open(settings, encoding='utf8') as f:
        data = json.load(f)
    source = os.path.join(folder, data['source'])
    if not os.path.isfile(source):
        return None
    known = Edit.__dataclass_fields__
    return source, Edit(**{k: v for k, v in data['edit'].items() if k in known})


def apply_to_slot(slot, info, edit, progress=lambda text: None, plugin_dir=None, reload=True):
    """Encode, verify, install into the slot, update its theme files, keep a library copy, reload Orca."""
    plugin_dir = plugin_dir or themes_dir()
    _, stem = SLOTS[slot]
    out = os.path.join(plugin_dir, 'images', f'{stem}.webp')
    tmp = out + '.tmp.webp'
    try:
        reduced = encode(info, edit, tmp, progress)
        problem = check_output(tmp, edit.mode)
        if problem:
            raise WallpaperError(msg('out_invalid', problem=problem))
        os.replace(tmp, out)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    write_slot_themes(slot, edit, plugin_dir)
    save_library(slot, info, edit)
    message = ''
    if reload:
        progress(msg('reloading'))
        result = subprocess.run(f'orca plugin dev reload "{plugin_dir}"', shell=True, capture_output=True, text=True)
        message = (result.stdout or result.stderr).strip().splitlines()[0] if (result.stdout or result.stderr).strip() else ''
    with Image.open(out) as im:
        kind = msg('kind_animated', n=getattr(im, 'n_frames', 1)) if getattr(im, 'is_animated', False) else msg('kind_still')
        summary = f'{im.size[0]}×{im.size[1]}, {kind}, {os.path.getsize(out) / 1048576:.2f} MB'
    return summary, reduced, message


def terminal_opacity():
    """The user's terminal Background Opacity from Orca's settings (read-only), for the preview."""
    try:
        root = os.path.join(_appdata(), 'orca')
        with io.open(os.path.join(root, 'orca-profile-index.json'), encoding='utf8') as f:
            profile = json.load(f).get('activeProfileId', 'local-default')
        db = os.path.join(root, 'profiles', profile, 'profile-state.db')
        con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
        try:
            row = con.execute("select payload from profile_state_documents where domain='settings'").fetchone()
        finally:
            con.close()
        value = json.loads(row[0]).get('terminalBackgroundOpacity', 1)
        return float(value) if isinstance(value, (int, float)) else 1.0
    except (OSError, KeyError, ValueError, TypeError, sqlite3.Error):
        return 0.6
