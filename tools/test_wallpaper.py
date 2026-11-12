"""Tests for wallpaper_core and a smoke test of the Wallpaper Studio window.

Run: python -I test_wallpaper.py
Works on a temporary copy of the plugin's theme files, so the real plugin is never touched.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw  # noqa: E402

import wallpaper_core as core  # noqa: E402


def make_plugin(root):
    """A minimal copy of the plugin: the nine My Wallpaper theme files and an images folder."""
    os.makedirs(os.path.join(root, 'themes'))
    os.makedirs(os.path.join(root, 'images'))
    for n in (1, 2, 3):
        stem = 'custom' if n == 1 else f'custom-{n}'
        for suffix in core.VARIANT_SUFFIXES:
            with open(os.path.join(root, 'themes', f'{stem}{suffix}.json'), 'w', encoding='utf8') as f:
                json.dump({'schemaVersion': 1, 'base': 'dark', 'tokens': {'--background': '#111214', '--foreground': '#ececef'},
                           'background': {'path': f'images/{stem}.webp', 'opacity': 1, 'size': 'cover', 'position': 'center'}}, f)
    return root


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.plugin = make_plugin(os.path.join(self.tmp, 'plugin'))
        core.LIBRARY_DIR = os.path.join(self.tmp, 'library')
        self.big = os.path.join(self.tmp, 'big.jpg')
        noisy = Image.effect_noise((4000, 2600), 90).convert('RGB')  # noise compresses badly: forces size budgeting
        noisy.save(self.big, quality=95)
        self.gif = os.path.join(self.tmp, 'anim.gif')
        frames = []
        for i in range(30):
            im = Image.new('RGB', (900, 600), (10, 20, 40))
            ImageDraw.Draw(im).ellipse((40 + i * 25, 250, 140 + i * 25, 350), fill=(255, 140, 60))
            frames.append(im)
        frames[0].save(self.gif, save_all=True, append_images=frames[1:], duration=60, loop=0)
        self.small = os.path.join(self.tmp, 'small.png')
        Image.new('RGB', (300, 200), (200, 80, 80)).save(self.small)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def apply(self, path, slot=1, **changes):
        info = core.inspect_source(path)
        ow, oh = info.width, info.height
        edit = core.Edit(crop=core.centered_crop(ow, oh, 16 / 9), **changes)
        edit.out_w, edit.out_h = core.clamp_output(edit.out_w, round(edit.out_w * 9 / 16))
        return core.apply_to_slot(slot, info, edit, plugin_dir=self.plugin, reload=False), info, edit

    def test_input_limits(self):
        missing = os.path.join(self.tmp, 'nope.png')
        with self.assertRaises(core.WallpaperError):
            core.inspect_source(missing)
        not_image = os.path.join(self.tmp, 'text.png')
        with open(not_image, 'w') as f:
            f.write('not an image')
        with self.assertRaises(core.WallpaperError):
            core.inspect_source(not_image)
        old = core.MAX_INPUT_SIDE
        core.MAX_INPUT_SIDE = 3000
        try:
            with self.assertRaises(core.WallpaperError):
                core.inspect_source(self.big)
        finally:
            core.MAX_INPUT_SIDE = old

    def test_stock_mode_static_under_2mb(self):
        (summary, reduced, _), _, _ = self.apply(self.big, mode='stock', out_w=3840)
        out = os.path.join(self.plugin, 'images', 'custom.webp')
        self.assertLessEqual(os.path.getsize(out), 2 * 1024 * 1024)
        self.assertIsNone(core.check_output(out, 'stock'))
        self.assertTrue(reduced, 'a noisy 3840 px image should need reducing to fit 2 MB')

    def test_animated_kept_in_patched_mode(self):
        (summary, _, _), _, _ = self.apply(self.gif, slot=2)
        with Image.open(os.path.join(self.plugin, 'images', 'custom-2.webp')) as im:
            self.assertTrue(im.is_animated)
            self.assertEqual(im.n_frames, 30)
            self.assertGreaterEqual(im.size[0], core.MIN_W)

    def test_animated_flattened_in_stock_mode(self):
        (_, reduced, _), _, _ = self.apply(self.gif, slot=3, mode='stock')
        with Image.open(os.path.join(self.plugin, 'images', 'custom-3.webp')) as im:
            self.assertFalse(getattr(im, 'is_animated', False))
        self.assertTrue(any('tĩnh' in r for r in reduced))

    def test_small_image_scaled_up_to_minimum(self):
        self.apply(self.small, out_w=320)
        with Image.open(os.path.join(self.plugin, 'images', 'custom.webp')) as im:
            self.assertGreaterEqual(im.size[0], core.MIN_W)
            self.assertGreaterEqual(im.size[1], core.MIN_H)

    def test_trim_step_speed(self):
        info = core.inspect_source(self.gif)
        frames = core.source_frames(self.gif, core.Edit(first_frame=5, last_frame=24, frame_step=2, speed=2.0))
        self.assertEqual(len(frames), 10)
        self.assertEqual(frames[0][1], 60)  # two 60 ms frames merged, then played twice as fast
        self.assertTrue(info.animated)

    def test_rotate_and_crop(self):
        info = core.inspect_source(self.gif)
        edit = core.Edit(rotate=90)
        self.assertEqual(core.oriented_size(info, edit), (600, 900))
        self.assertEqual(core.centered_crop(900, 600, 16 / 9), [0, 47, 900, 553])
        frame = core.render_frame(Image.open(self.gif), core.Edit(rotate=90, crop=[0, 0, 600, 338], out_w=1280, out_h=720))
        self.assertEqual(frame.size, (1280, 720))

    def test_theme_files_and_library(self):
        _, info, edit = self.apply(self.gif, slot=2, opacity=0.6, size='contain', position='top', darken=0.3)
        for suffix in core.VARIANT_SUFFIXES:
            with open(os.path.join(self.plugin, 'themes', f'custom-2{suffix}.json'), encoding='utf8') as f:
                bg = json.load(f)['background']
            self.assertEqual(bg, {'path': 'images/custom-2.webp', 'opacity': 0.6, 'size': 'contain', 'position': 'top'})
        source, saved = core.load_library(2)
        self.assertTrue(os.path.isfile(source))
        self.assertEqual((saved.darken, saved.size, saved.crop), (0.3, 'contain', edit.crop))
        self.assertIsNone(core.load_library(3))

    def test_clamp_output(self):
        self.assertEqual(core.clamp_output(8000, 4500), (4096, 2304))
        self.assertEqual(core.clamp_output(320, 180), (640, 360))

    def test_creates_its_own_theme_plugin(self):
        folder = os.path.join(self.tmp, 'my-themes')
        self.assertEqual(core.ensure_theme_plugin(folder), folder)
        with open(os.path.join(folder, 'orca-plugin.json'), encoding='utf8') as f:
            manifest = json.load(f)
        themes = manifest['contributes']['themes']
        self.assertEqual(len(themes), 9)  # three slots, each with the theme and its two sidebar variants
        self.assertEqual(len({t['id'] for t in themes}), 9)
        self.assertEqual(themes[0]['title'], 'My Wallpaper')
        for theme in themes:
            path = os.path.join(folder, theme['path'])
            self.assertTrue(os.path.isfile(path), theme['path'])
            with open(path, encoding='utf8') as f:
                background = json.load(f)['background']['path']
            self.assertTrue(os.path.isfile(os.path.join(folder, background)), background)
        for stem in ('custom', 'custom-2', 'custom-3'):
            with Image.open(os.path.join(folder, 'images', f'{stem}.webp')) as placeholder:
                self.assertGreaterEqual(placeholder.size, (640, 360))

    def test_existing_theme_files_are_never_overwritten(self):
        folder = os.path.join(self.tmp, 'my-themes')
        core.ensure_theme_plugin(folder)
        marker = os.path.join(folder, 'themes', 'custom.json')
        with open(marker, 'w', encoding='utf8') as f:
            f.write('{"edited": true}')
        core.ensure_theme_plugin(folder)
        with open(marker, encoding='utf8') as f:
            self.assertEqual(json.load(f), {'edited': True})

    def test_applies_into_a_fresh_theme_folder_without_any_other_plugin(self):
        folder = os.path.join(self.tmp, 'fresh')
        old = os.environ.get('WALLPAPER_THEMES_DIR')
        os.environ['WALLPAPER_THEMES_DIR'] = folder
        try:
            self.assertEqual(core.themes_dir(), folder)
            info = core.inspect_source(self.small)
            edit = core.Edit(crop=core.centered_crop(info.width, info.height, 16 / 9), mode='stock')
            edit.out_w, edit.out_h = core.clamp_output(edit.out_w, round(edit.out_w * 9 / 16))
            summary, _, _ = core.apply_to_slot(1, info, edit, reload=False)
        finally:
            if old is None:
                os.environ.pop('WALLPAPER_THEMES_DIR', None)
            else:
                os.environ['WALLPAPER_THEMES_DIR'] = old
        self.assertIn('MB', summary)
        with Image.open(os.path.join(folder, 'images', 'custom.webp')) as written:
            self.assertGreaterEqual(written.size, (640, 360))

    def test_generated_plugin_passes_orcas_validator(self):
        if not shutil.which('orca'):
            self.skipTest('the orca command is not installed')
        folder = os.path.join(self.tmp, 'validated')
        core.ensure_theme_plugin(folder)
        done = subprocess.run(f'orca plugin validate "{folder}"', shell=True, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


    def test_default_folder_is_the_plugin_itself_unless_it_is_an_installed_copy(self):
        old_root, old_env = core.PLUGIN_ROOT, {k: os.environ.pop(k, None) for k in ('WALLPAPER_THEMES_DIR', 'ASCII_THEMES_DIR')}
        try:
            dev = os.path.join(self.tmp, 'dev-plugin')
            os.makedirs(os.path.join(dev, 'tools'))
            with open(os.path.join(dev, 'orca-plugin.json'), 'w', encoding='utf8') as f:
                json.dump({'contributes': {'themes': [{'id': 'x'}]}}, f)
            core.PLUGIN_ROOT = dev
            self.assertTrue(core.own_folder_usable())
            self.assertEqual(core.themes_dir(), dev)
            installed = os.path.join(self.tmp, 'plugins', 'author.name', 'a' * 64)  # how Orca names an installed copy
            os.makedirs(installed)
            with open(os.path.join(installed, 'orca-plugin.json'), 'w', encoding='utf8') as f:
                json.dump({'contributes': {'themes': [{'id': 'x'}]}}, f)
            core.PLUGIN_ROOT = installed
            self.assertFalse(core.own_folder_usable())
            no_themes = os.path.join(self.tmp, 'no-themes')
            os.makedirs(no_themes)
            with open(os.path.join(no_themes, 'orca-plugin.json'), 'w', encoding='utf8') as f:
                json.dump({'contributes': {}}, f)
            core.PLUGIN_ROOT = no_themes
            self.assertFalse(core.own_folder_usable())
        finally:
            core.PLUGIN_ROOT = old_root
            for key, value in old_env.items():
                if value is not None:
                    os.environ[key] = value

    def test_detached_run_reports_through_the_job_file_and_cleans_up(self):
        upload = os.path.join(self.tmp, 'upload')
        os.makedirs(upload)
        shutil.copy(self.small, os.path.join(upload, 'source.png'))
        edit = os.path.join(upload, 'edit.json')
        with open(edit, 'w', encoding='utf8') as f:
            json.dump({'lang': 'en', 'mode': 'stock', 'crop': [0, 0, 300, 200], 'out_w': 1280, 'out_h': 720}, f)
        folder = os.path.join(self.tmp, 'themes-out')
        core.ensure_theme_plugin(folder)
        job = os.path.join(self.tmp, 'job.json')
        env = dict(os.environ, WALLPAPER_JOB_FILE=job, WALLPAPER_CLEANUP_DIR=upload, WALLPAPER_THEMES_DIR=folder,
                   WALLPAPER_STUDIO_LIBRARY=os.path.join(self.tmp, 'lib'), WALLPAPER_NO_RELOAD='1')
        cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wallpaper_cli.py')
        done = subprocess.run([sys.executable, '-I', cli, 'apply', os.path.join(upload, 'source.png'), '1', edit],
                              env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertEqual(done.returncode, 0)
        with open(job, encoding='utf8') as f:
            record = json.load(f)
        self.assertEqual(record['state'], 'done')
        self.assertTrue(record['result']['ok'], record)
        self.assertEqual(record['result']['folder'], folder)
        self.assertTrue(record['pid'] > 0)
        self.assertFalse(os.path.exists(upload), 'the uploaded picture folder should be removed by the tool')
        with Image.open(os.path.join(folder, 'images', 'custom.webp')) as written:
            self.assertEqual(written.size, (1280, 720))


class StudioSmokeTest(unittest.TestCase):
    """Builds the real window off-screen, opens an image, drags and zooms the crop, and renders previews."""

    def test_window(self):
        import tkinter as tk
        import wallpaper_studio
        tmp = tempfile.mkdtemp()
        try:
            gif = os.path.join(tmp, 'a.gif')
            frames = [Image.new('RGB', (1200, 800), (i * 8, 40, 90)) for i in range(10)]
            frames[0].save(gif, save_all=True, append_images=frames[1:], duration=80, loop=0)
            root = tk.Tk()
            root.withdraw()
            studio = wallpaper_studio.Studio(root, gif)
            studio.redraw()
            before = list(studio.edit.crop)
            studio.on_press(type('E', (), {'x': 400, 'y': 250})())
            studio.on_drag(type('E', (), {'x': 300, 'y': 250})())
            studio.on_wheel(type('E', (), {'delta': 120})())
            studio.rotate(90)
            studio.flip('h')
            studio.vars['aspect'].set('21:9')
            studio.reset_crop()
            studio.redraw()
            edit = studio._collect_edit()
            self.assertNotEqual(before, edit.crop)
            self.assertAlmostEqual((edit.crop[2] - edit.crop[0]) / (edit.crop[3] - edit.crop[1]), 21 / 9, delta=0.02)
            self.assertGreaterEqual(edit.out_w, core.MIN_W)
            root.destroy()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
