"""Wallpaper Studio: pick any image, crop and adjust it, and install it as an Orca theme wallpaper.

Usage: python -I wallpaper_studio.py [image]

Left: the crop editor (drag to move the crop, mouse wheel to zoom it). Right: crop shape, output
size, adjustments, how Orca shows it, animation options and a preview under a simulated terminal.
"Áp dụng vào Orca" writes the slot's wallpaper, updates its three theme files and reloads Orca.
All image work happens in wallpaper_core.py.
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

# Why: isolated mode (python -I) does not put the script's folder on sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wallpaper_core as core  # noqa: E402

CANVAS_W, CANVAS_H = 880, 495
PREVIEW_W, PREVIEW_H = 384, 216
EDITOR_MAX_SIDE = 1600  # the crop editor works on a reduced copy; export always uses full resolution


class Studio:
    def __init__(self, root, initial_path=None):
        self.root = root
        root.title('Orca Wallpaper Studio')
        root.minsize(1300, 760)
        self.screen = (root.winfo_screenwidth(), root.winfo_screenheight())
        self.info = None
        self.edit = core.Edit()
        self.editor_image = None   # oriented, reduced copy shown in the crop editor
        self.editor_scale = 1.0    # editor pixels per oriented full-resolution pixel
        self.still = None          # the source frame being previewed
        self.drag_from = None
        self.pending = None
        self.busy = False
        self.terminal_opacity = core.terminal_opacity()
        self._build()
        if initial_path:
            self.open_path(initial_path)

    # ---------- layout ----------
    def _build(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill='x')
        ttk.Button(top, text='Mở ảnh…', command=self.choose_file).pack(side='left')
        self.source_label = ttk.Label(top, text='Chưa chọn ảnh. Nhận JPG, PNG, WebP, BMP, GIF (kể cả ảnh động).')
        self.source_label.pack(side='left', padx=10)

        body = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        body.pack(fill='both', expand=True)
        left = ttk.Frame(body)
        left.pack(side='left', fill='both', expand=True)
        self.canvas = tk.Canvas(left, width=CANVAS_W, height=CANVAS_H, bg='#202124', highlightthickness=0, cursor='fleur')
        self.canvas.pack()
        ttk.Label(left, text='Kéo để di chuyển khung cắt · cuộn chuột để phóng to hoặc thu nhỏ khung').pack(anchor='w', pady=4)
        ttk.Label(left, text='Xem trước trong Orca (có lớp terminal mô phỏng theo Background Opacity '
                             f'{self.terminal_opacity:g} của bạn):').pack(anchor='w', pady=(8, 2))
        self.preview = tk.Canvas(left, width=PREVIEW_W, height=PREVIEW_H, bg='#111214', highlightthickness=0)
        self.preview.pack(anchor='w')

        right = ttk.Frame(body, padding=(12, 0, 0, 0))
        right.pack(side='right', fill='y')
        self.vars = {}

        box = self._group(right, 'Ô hình nền trong Orca')
        self.vars['slot'] = tk.IntVar(value=1)
        for n in core.SLOTS:
            ttk.Radiobutton(box, text=f'My Wallpaper{"" if n == 1 else " " + str(n)}', value=n, variable=self.vars['slot']).pack(side='left')
        ttk.Button(box, text='Mở lại ảnh đã lưu', command=self.load_slot).pack(side='right')

        box = self._group(right, 'Chế độ (giới hạn ảnh xuất)')
        self.vars['mode'] = tk.StringVar(value='patched')
        for key, mode in core.MODES.items():
            ttk.Radiobutton(box, text=mode['label'], value=key, variable=self.vars['mode'], command=self.schedule).pack(anchor='w')

        box = self._group(right, 'Khung cắt')
        ratio = self.screen[0] / self.screen[1]
        self.aspects = {f'Màn hình ({self.screen[0]}×{self.screen[1]})': ratio, '16:9': 16 / 9, '16:10': 1.6,
                        '21:9': 21 / 9, '4:3': 4 / 3, 'Toàn bộ ảnh (không cắt)': None}
        self.vars['aspect'] = tk.StringVar(value=next(iter(self.aspects)))
        combo = ttk.Combobox(box, values=list(self.aspects), textvariable=self.vars['aspect'], state='readonly', width=30)
        combo.pack(anchor='w')
        combo.bind('<<ComboboxSelected>>', lambda e: self.reset_crop())
        row = ttk.Frame(box)
        row.pack(anchor='w', pady=4)
        for text, command in (('⟲ Xoay trái', lambda: self.rotate(-90)), ('⟳ Xoay phải', lambda: self.rotate(90)),
                              ('⇋ Lật ngang', lambda: self.flip('h')), ('⇵ Lật dọc', lambda: self.flip('v')),
                              ('Đặt lại', self.reset_crop)):
            ttk.Button(row, text=text, command=command).pack(side='left', padx=1)

        box = self._group(right, 'Kích thước xuất')
        widths = [f'Màn hình ({min(core.MAX_SIDE, self.screen[0])} px ngang)', '1280 px', '1920 px', '2560 px', '3840 px']
        self.vars['width'] = tk.StringVar(value=widths[0])
        combo = ttk.Combobox(box, values=widths, textvariable=self.vars['width'], state='readonly', width=30)
        combo.pack(anchor='w')
        combo.bind('<<ComboboxSelected>>', lambda e: self.schedule())
        self.size_label = ttk.Label(box, text='')
        self.size_label.pack(anchor='w')

        box = self._group(right, 'Chỉnh ảnh')
        self._slider(box, 'brightness', 'Độ sáng', 0.5, 1.5, 1.0)
        self._slider(box, 'darken', 'Làm tối (để chữ dễ đọc)', 0.0, 0.8, 0.0)
        self._slider(box, 'blur', 'Làm mờ (px)', 0.0, 10.0, 0.0)

        box = self._group(right, 'Hiển thị trong Orca')
        self._slider(box, 'opacity', 'Độ đậm hình nền', 0.2, 1.0, 1.0)
        row = ttk.Frame(box)
        row.pack(anchor='w')
        self.vars['size'] = tk.StringVar(value='cover')
        self.vars['position'] = tk.StringVar(value='center')
        ttk.Label(row, text='Kiểu:').pack(side='left')
        size_box = ttk.Combobox(row, values=core.SIZES, textvariable=self.vars['size'], state='readonly', width=8)
        size_box.pack(side='left', padx=4)
        ttk.Label(row, text='Neo:').pack(side='left')
        position_box = ttk.Combobox(row, values=core.POSITIONS, textvariable=self.vars['position'], state='readonly', width=8)
        position_box.pack(side='left', padx=4)
        for widget in (size_box, position_box):
            widget.bind('<<ComboboxSelected>>', lambda e: self.schedule())

        self.anim_box = self._group(right, 'Ảnh động')
        self._slider(self.anim_box, 'speed', 'Tốc độ (×)', 0.25, 2.0, 1.0)
        row = ttk.Frame(self.anim_box)
        row.pack(anchor='w')
        self.vars['first'] = tk.IntVar(value=0)
        self.vars['last'] = tk.IntVar(value=0)
        self.vars['step'] = tk.IntVar(value=1)
        ttk.Label(row, text='Từ khung').pack(side='left')
        self.first_spin = ttk.Spinbox(row, from_=0, to=0, textvariable=self.vars['first'], width=5, command=self.on_first_frame)
        self.first_spin.pack(side='left', padx=2)
        ttk.Label(row, text='đến').pack(side='left')
        self.last_spin = ttk.Spinbox(row, from_=0, to=0, textvariable=self.vars['last'], width=5, command=self.schedule)
        self.last_spin.pack(side='left', padx=2)
        ttk.Label(row, text='mỗi').pack(side='left')
        ttk.Spinbox(row, from_=1, to=4, textvariable=self.vars['step'], width=3, command=self.schedule).pack(side='left', padx=2)
        ttk.Label(row, text='khung lấy 1').pack(side='left')

        self.apply_button = ttk.Button(right, text='Áp dụng vào Orca', command=self.apply)
        self.apply_button.pack(fill='x', pady=(10, 4))
        self.status = ttk.Label(right, text='', wraplength=380, justify='left')
        self.status.pack(anchor='w')

        self.canvas.bind('<ButtonPress-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<MouseWheel>', self.on_wheel)
        self._set_anim_enabled(False)

    def _group(self, parent, title):
        frame = ttk.LabelFrame(parent, text=title, padding=6)
        frame.pack(fill='x', pady=3)
        return frame

    def _slider(self, parent, key, label, lo, hi, value):
        row = ttk.Frame(parent)
        row.pack(fill='x')
        self.vars[key] = tk.DoubleVar(value=value)
        ttk.Label(row, text=label, width=24).pack(side='left')
        text = ttk.Label(row, text=f'{value:.2f}', width=5)
        ttk.Scale(row, from_=lo, to=hi, variable=self.vars[key], length=170,
                  command=lambda v: (text.config(text=f'{float(v):.2f}'), self.schedule())).pack(side='left')
        text.pack(side='left')

    def _set_anim_enabled(self, enabled):
        state = '!disabled' if enabled else 'disabled'
        for child in self.anim_box.winfo_children():
            for widget in [child, *child.winfo_children()]:
                try:
                    widget.state([state])
                except (AttributeError, tk.TclError):
                    pass

    # ---------- opening ----------
    def choose_file(self):
        path = filedialog.askopenfilename(title='Chọn ảnh làm hình nền', filetypes=[
            ('Ảnh', '*.jpg *.jpeg *.png *.webp *.bmp *.gif'), ('Tất cả', '*.*')])
        if path:
            self.open_path(path)

    def open_path(self, path, edit=None):
        try:
            info = core.inspect_source(path)
        except core.WallpaperError as error:
            messagebox.showerror('Không mở được ảnh', str(error))
            return
        self.info = info
        self.edit = edit or core.Edit()
        kind = f'ảnh động, {info.frames} khung, {info.seconds:.1f} giây' if info.animated else 'ảnh tĩnh'
        self.source_label.config(text=f'{os.path.basename(path)}: {info.width}×{info.height}, {kind}, '
                                      f'{os.path.getsize(path) / 1048576:.2f} MB')
        self._set_anim_enabled(info.animated)
        self.first_spin.config(to=max(0, info.frames - 1))
        self.last_spin.config(to=max(0, info.frames - 1))
        if edit:
            self._load_edit_into_ui(edit)
        else:
            self.vars['first'].set(0)
            self.vars['last'].set(max(0, info.frames - 1))
        self._load_still()
        self._rebuild_editor(keep_crop=bool(edit))

    def _load_still(self):
        with Image.open(self.info.path) as im:
            if self.info.animated:
                try:
                    frame = int(self.vars['first'].get())
                except (tk.TclError, ValueError):
                    frame = 0
                im.seek(min(max(0, frame), self.info.frames - 1))
            self.still = im.copy()

    def on_first_frame(self):
        if self.info and self.info.animated:
            self._load_still()
            self._rebuild_editor(keep_crop=True)

    def load_slot(self):
        saved = core.load_library(self.vars['slot'].get())
        if not saved:
            messagebox.showinfo('Chưa có ảnh', 'Ô này chưa có ảnh đã lưu.')
            return
        self.open_path(saved[0], saved[1])

    def _load_edit_into_ui(self, edit):
        for key in ('brightness', 'darken', 'blur', 'opacity', 'speed'):
            self.vars[key].set(getattr(edit, key))
        self.vars['size'].set(edit.size)
        self.vars['position'].set(edit.position)
        self.vars['mode'].set(edit.mode)
        self.vars['first'].set(edit.first_frame)
        self.vars['last'].set(edit.last_frame if edit.last_frame >= 0 else max(0, self.info.frames - 1))
        self.vars['step'].set(edit.frame_step)

    # ---------- crop editor ----------
    def _aspect(self):
        return self.aspects[self.vars['aspect'].get()]

    def _rebuild_editor(self, keep_crop=False):
        if not self.info:
            return
        oriented = core.orient(self.still, self.edit)
        ow, oh = oriented.size
        self.editor_scale = min(1.0, EDITOR_MAX_SIDE / max(ow, oh))
        self.editor_image = oriented.resize((max(1, round(ow * self.editor_scale)), max(1, round(oh * self.editor_scale))), Image.LANCZOS)
        if not keep_crop or not self.edit.crop:
            self.edit.crop = core.centered_crop(ow, oh, self._aspect())
        self.schedule()

    def reset_crop(self):
        if self.info:
            ow, oh = core.oriented_size(self.info, self.edit)
            self.edit.crop = core.centered_crop(ow, oh, self._aspect())
            self.schedule()

    def rotate(self, degrees):
        if self.info:
            self.edit.rotate = (self.edit.rotate + degrees) % 360
            self._rebuild_editor()

    def flip(self, axis):
        if self.info:
            if axis == 'h':
                self.edit.flip_h = not self.edit.flip_h
            else:
                self.edit.flip_v = not self.edit.flip_v
            self._rebuild_editor()

    def _view(self):
        """Scale and offset that fit the editor image into the canvas."""
        ew, eh = self.editor_image.size
        fit = min(CANVAS_W / ew, CANVAS_H / eh)
        return fit, (CANVAS_W - ew * fit) / 2, (CANVAS_H - eh * fit) / 2

    def on_press(self, event):
        self.drag_from = (event.x, event.y)

    def on_drag(self, event):
        if not self.info or not self.drag_from or self._aspect() is None:
            return
        fit, _, _ = self._view()
        factor = 1 / (fit * self.editor_scale)  # canvas px -> oriented full-resolution px
        dx, dy = (event.x - self.drag_from[0]) * factor, (event.y - self.drag_from[1]) * factor
        self.drag_from = (event.x, event.y)
        self._move_crop(dx, dy)

    def on_wheel(self, event):
        if not self.info or self._aspect() is None:
            return
        left, top, right, bottom = self.edit.crop
        ow, oh = core.oriented_size(self.info, self.edit)
        factor = 0.9 if event.delta > 0 else 1.1
        cx, cy = (left + right) / 2, (top + bottom) / 2
        w = min(ow, max(64, (right - left) * factor))
        h = w / self._aspect()
        if h > oh:
            h = oh
            w = h * self._aspect()
        self.edit.crop = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
        self._move_crop(0, 0)

    def _move_crop(self, dx, dy):
        left, top, right, bottom = self.edit.crop
        ow, oh = core.oriented_size(self.info, self.edit)
        w, h = right - left, bottom - top
        left = min(max(0, left + dx), ow - w)
        top = min(max(0, top + dy), oh - h)
        self.edit.crop = [round(left), round(top), round(left + w), round(top + h)]
        self.schedule()

    # ---------- previews ----------
    def schedule(self, *_):
        if self.pending:
            self.root.after_cancel(self.pending)
        self.pending = self.root.after(60, self.redraw)

    def _collect_edit(self):
        edit = self.edit
        left, top, right, bottom = edit.crop
        width_text = self.vars['width'].get()
        out_w = min(core.MAX_SIDE, self.screen[0]) if width_text.startswith('Màn hình') else int(width_text.split()[0])
        out_h = round(out_w * (bottom - top) / max(1, right - left))
        edit.out_w, edit.out_h = core.clamp_output(out_w, out_h)
        for key in ('brightness', 'darken', 'blur', 'opacity', 'speed'):
            setattr(edit, key, round(float(self.vars[key].get()), 3))
        edit.size, edit.position, edit.mode = self.vars['size'].get(), self.vars['position'].get(), self.vars['mode'].get()
        try:
            edit.first_frame, edit.last_frame, edit.frame_step = int(self.vars['first'].get()), int(self.vars['last'].get()), int(self.vars['step'].get())
        except (tk.TclError, ValueError):
            pass
        return edit

    def redraw(self):
        self.pending = None
        if not self.info:
            return
        edit = self._collect_edit()
        # crop editor: whole oriented image, dimmed outside the crop, crop border on top
        fit, ox, oy = self._view()
        ew, eh = self.editor_image.size
        shown = self.editor_image.resize((max(1, round(ew * fit)), max(1, round(eh * fit))), Image.BILINEAR)
        dim = Image.blend(shown, Image.new('RGB', shown.size, (0, 0, 0)), 0.6)
        s = fit * self.editor_scale
        box = tuple(round(v * s) for v in edit.crop)
        dim.paste(shown.crop(box), box[:2])
        ImageDraw.Draw(dim).rectangle(box, outline=(138, 180, 255), width=2)
        self._editor_photo = ImageTk.PhotoImage(dim)
        self.canvas.delete('all')
        self.canvas.create_image(ox, oy, image=self._editor_photo, anchor='nw')
        self.size_label.config(text=f'Ảnh xuất: {edit.out_w}×{edit.out_h} px (Orca: {core.MIN_W}×{core.MIN_H} đến {core.MAX_SIDE}×{core.MAX_SIDE})')
        # result preview: the exported look, then a translucent terminal panel as Orca paints it
        scale = PREVIEW_W / edit.out_w
        result = core.render_frame(self.still, edit, scale)
        canvas = Image.new('RGB', (PREVIEW_W, PREVIEW_H), (17, 18, 20))
        if edit.size == 'tile':
            tile = result.resize((max(1, PREVIEW_W // 3), max(1, round(PREVIEW_W // 3 * result.height / result.width))))
            for x in range(0, PREVIEW_W, tile.width):
                for y in range(0, PREVIEW_H, tile.height):
                    canvas.paste(tile, (x, y))
        else:
            fit_scale = (min if edit.size == 'contain' else max)(PREVIEW_W / result.width, PREVIEW_H / result.height)
            result = result.resize((max(1, round(result.width * fit_scale)), max(1, round(result.height * fit_scale))))
            px = {'left': 0, 'right': PREVIEW_W - result.width}.get(edit.position, (PREVIEW_W - result.width) // 2)
            py = {'top': 0, 'bottom': PREVIEW_H - result.height}.get(edit.position, (PREVIEW_H - result.height) // 2)
            canvas.paste(result, (px, py))
        canvas = Image.blend(Image.new('RGB', canvas.size, (17, 18, 20)), canvas, edit.opacity)
        panel = Image.new('RGB', canvas.size, (17, 18, 20))
        mixed = Image.blend(canvas, panel, max(0.0, min(1.0, self.terminal_opacity)))
        draw = ImageDraw.Draw(mixed)
        for i, line in enumerate(['$ orca --version', '1.4.246', '$ git status', 'On branch main', 'nothing to commit']):
            draw.text((12, 14 + i * 16), line, fill=(236, 236, 239))
        self._preview_photo = ImageTk.PhotoImage(mixed)
        self.preview.delete('all')
        self.preview.create_image(0, 0, image=self._preview_photo, anchor='nw')

    # ---------- apply ----------
    def apply(self):
        if not self.info or self.busy:
            return
        edit = core.Edit(**vars(self._collect_edit()))
        slot = self.vars['slot'].get()
        self.busy = True
        self.apply_button.state(['disabled'])

        def progress(text):
            self.root.after(0, lambda: self.status.config(text=text))

        def work():
            try:
                summary, reduced, message = core.apply_to_slot(slot, self.info, edit, progress)
                note = ('\nĐã tự điều chỉnh: ' + '; '.join(reduced)) if reduced else ''
                name = 'My Wallpaper' + ('' if slot == 1 else f' {slot}')
                text = (f'Đã áp dụng vào {name}: {summary}.{note}\n{message}\n'
                        f'Trong Orca, chọn (hoặc chọn lại) theme "ASCII · {name}" để thấy ảnh mới.')
            except core.WallpaperError as error:
                text = 'Không áp dụng được: ' + str(error)
            except Exception as error:  # surface anything unexpected instead of failing silently
                text = f'Lỗi không mong muốn: {type(error).__name__}: {error}'
            self.root.after(0, lambda: self._done(text))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, text):
        self.busy = False
        self.apply_button.state(['!disabled'])
        self.status.config(text=text)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use('vista')
    except tk.TclError:
        pass
    Studio(root, sys.argv[1] if len(sys.argv) > 1 else None)
    root.mainloop()


if __name__ == '__main__':
    main()
