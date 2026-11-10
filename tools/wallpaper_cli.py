"""Command-line entry used by the Wallpaper Studio Orca plugin's worker.

  python -I wallpaper_cli.py apply <image> <slot> <edit.json>
      Prints progress lines "PROGRESS <text>" on stderr and one JSON object on stdout:
      {"ok": true, "summary": "...", "reduced": [...], "reload": "..."} or {"ok": false, "error": "..."}.
  python -I wallpaper_cli.py env
      Prints {"terminalOpacity": <number>} so the panel preview matches Orca's terminal.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # isolated mode does not add it
import wallpaper_core as core  # noqa: E402


def emit(data):
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + '\n')
    sys.stdout.flush()


def apply(source, slot, edit_path):
    with open(edit_path, encoding='utf8') as f:
        raw = json.load(f)
    core.set_language(raw.get('lang', 'vi'))
    known = core.Edit.__dataclass_fields__
    edit = core.Edit(**{k: v for k, v in raw.items() if k in known})
    if edit.mode not in core.MODES or edit.size not in core.SIZES or edit.position not in core.POSITIONS:
        raise core.WallpaperError(core.msg('bad_params'))
    if slot not in core.SLOTS:
        raise core.WallpaperError(core.msg('bad_slot'))
    info = core.inspect_source(source)
    ow, oh = core.oriented_size(info, edit)
    if edit.crop:
        left, top, right, bottom = (int(round(v)) for v in edit.crop)
        left, top = max(0, min(left, ow - 1)), max(0, min(top, oh - 1))
        right, bottom = max(left + 1, min(right, ow)), max(top + 1, min(bottom, oh))
        edit.crop = [left, top, right, bottom]
    edit.out_w, edit.out_h = core.clamp_output(max(1, int(edit.out_w)), max(1, int(edit.out_h)))
    folder = core.themes_dir()
    summary, reduced, reload = core.apply_to_slot(
        slot, info, edit, plugin_dir=folder, progress=lambda text: print('PROGRESS ' + text, file=sys.stderr, flush=True))
    emit({'ok': True, 'summary': summary, 'reduced': reduced, 'reload': reload, 'reloaded': reload == '', 'folder': folder})


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    args = sys.argv[1:]
    try:
        if args[:1] == ['env']:
            emit({'terminalOpacity': core.terminal_opacity()})
        elif args[:1] == ['apply'] and len(args) == 4:
            apply(args[1], int(args[2]), args[3])
        else:
            emit({'ok': False, 'error': core.msg('usage')})
    except core.WallpaperError as error:
        emit({'ok': False, 'error': str(error)})
    except Exception as error:  # report, never fail silently
        emit({'ok': False, 'error': f'{type(error).__name__}: {error}'})


if __name__ == '__main__':
    main()
