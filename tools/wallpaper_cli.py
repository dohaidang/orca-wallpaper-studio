"""Command-line entry used by the Wallpaper Studio Orca plugin's worker.

  python -I wallpaper_cli.py apply <image> <slot> <edit.json>
      Prints progress lines "PROGRESS <text>" on stderr and one JSON object on stdout:
      {"ok": true, "summary": "...", "reduced": [...], "reload": "..."} or {"ok": false, "error": "..."}.
  python -I wallpaper_cli.py env
      Prints {"terminalOpacity": <number>} so the panel preview matches Orca's terminal.
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # isolated mode does not add it
import wallpaper_core as core  # noqa: E402


# Orca reloads a development plugin, and restarts its worker, whenever a file in the plugin folder changes. Studio
# writes the new picture into that folder, so the worker that started this process may be restarted before it
# finishes, and the worker's pipes to this process would break. So the worker starts it detached, with no pipes, and
# this process reports progress and the final answer in the job file instead (a file outside the plugin folder).
JOB_FILE = os.environ.get('WALLPAPER_JOB_FILE', '')


def write_job(state, text='', result=None):
    if not JOB_FILE:
        return
    tmp = JOB_FILE + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf8') as f:
            json.dump({'state': state, 'pid': os.getpid(), 'text': text, 'result': result}, f, ensure_ascii=False)
        os.replace(tmp, JOB_FILE)
    except OSError:
        pass


def say_progress(text):
    write_job('running', text)
    try:
        print('PROGRESS ' + text, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass  # the pipe is gone (or there never was one); the job file has it


def emit(data):
    if JOB_FILE:
        write_job('done', result=data)
    try:
        sys.stdout.write(json.dumps(data, ensure_ascii=False) + '\n')
        sys.stdout.flush()
    except (OSError, ValueError):
        pass


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
        slot, info, edit, plugin_dir=folder, progress=say_progress)
    emit({'ok': True, 'summary': summary, 'reduced': reduced, 'reload': reload, 'reloaded': reload == '', 'folder': folder, 'slot': slot})


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError, ValueError):
            pass
    args = sys.argv[1:]
    write_job('running', '')
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
    finally:
        cleanup = os.environ.get('WALLPAPER_CLEANUP_DIR', '')
        if cleanup:  # the worker's temp folder with the uploaded picture; a restarted worker cannot remove it
            shutil.rmtree(cleanup, ignore_errors=True)


if __name__ == '__main__':
    main()
