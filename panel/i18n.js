// Wallpaper Studio panel texts. The panel follows Orca's UI language (orca.locale): Vietnamese and English
// are provided, and any other language falls back to English. To add a language, add a table to MESSAGES
// below under its two-letter code (for example `de`) and list the same keys; nothing else needs to change.
'use strict'

const MESSAGES = {
  vi: {
    pick: 'Chọn ảnh…',
    source_hint: 'JPG, PNG, WebP, BMP hoặc GIF (kể cả ảnh động), tối đa 50 MB.',
    editor_aria: 'Khung cắt: kéo để di chuyển, cuộn chuột để phóng to hoặc thu nhỏ',
    crop_hint: 'Kéo để di chuyển khung cắt · cuộn chuột để phóng to/thu nhỏ',
    legend_crop: 'Khung cắt',
    aspect_aria: 'Tỉ lệ khung cắt',
    rotate_left: 'Xoay trái',
    rotate_right: 'Xoay phải',
    flip_h: 'Lật ngang',
    flip_v: 'Lật dọc',
    reset: 'Đặt lại',
    legend_size: 'Kích thước xuất',
    width_aria: 'Chiều ngang ảnh xuất',
    legend_adjust: 'Chỉnh ảnh',
    brightness: 'Độ sáng',
    darken: 'Làm tối (chữ dễ đọc)',
    blur: 'Làm mờ (px)',
    legend_display: 'Hiển thị trong Orca',
    opacity: 'Độ đậm hình nền',
    fit: 'Kiểu',
    anchor: 'Neo',
    legend_anim: 'Ảnh động (chỉ dùng khi ảnh là GIF/WebP động)',
    speed: 'Tốc độ (×)',
    from_frame: 'Từ khung',
    to_frame: 'đến',
    to_frame_title: '-1 là khung cuối',
    every: 'mỗi',
    keep_one: 'lấy 1',
    legend_apply: 'Áp dụng vào',
    mode_patched: 'Orca đã vá: tĩnh hoặc động, ≤ 16 MB',
    mode_stock: 'Orca chuẩn: chỉ ảnh tĩnh, ≤ 2 MB',
    preview_note: 'Xem trước dưới lớp terminal',
    preview_note_opacity: 'Xem trước dưới lớp terminal (Background Opacity {v})',
    preview_aria: 'Xem trước hình nền trong Orca',
    apply: 'Áp dụng vào Orca',
    cancel: 'Hủy',
    aspect_screen: 'Màn hình ({w}×{h})',
    aspect_full: 'Toàn bộ ảnh (không cắt)',
    width_screen: 'Màn hình ({px} px ngang)',
    size_note: 'Ảnh xuất: {w}×{h} px (Orca nhận {minw}×{minh} đến {max}×{max})',
    too_big: 'Ảnh lớn hơn {mb} MB.',
    cannot_open: 'Không đọc được ảnh này.',
    rate_limited: 'Orca đang giới hạn tốc độ gửi, chờ {s} giây rồi gửi tiếp…',
    sending: 'Đang gửi ảnh cho worker…',
    sending_n: 'Đang gửi ảnh cho worker… {i}/{n}',
    processing: 'Đang xử lý ảnh…',
    failed: 'Không áp dụng được: {e}',
    cancelled: 'Đã hủy. Hình nền hiện tại không thay đổi.',
    timeout: 'Xử lý quá 15 phút, đã dừng chờ. Hãy thử ảnh nhỏ hoặc ngắn hơn.',
    worker_restarted: 'Worker đã khởi động lại nên mất kết quả. Hãy bấm Áp dụng lần nữa.',
    waiting_worker: 'Đang chờ worker… ({e})',
    unknown_error: 'lỗi không rõ',
    adjusted: 'Đã tự điều chỉnh: {list}',
    reload_failed: 'Orca chưa nạp được thư mục theme. Hãy thêm nó trong Cài đặt → Plugins → Development folders: {folder}',
    applied: 'Đã áp dụng vào {name}: {summary}.{note}\nChọn (hoặc chọn lại) theme "{name}" trong Cài đặt → Giao diện để thấy ảnh mới.\nThư mục theme: {folder}'
  },
  en: {
    pick: 'Choose image…',
    source_hint: 'JPG, PNG, WebP, BMP or GIF (animated too), up to 50 MB.',
    editor_aria: 'Crop frame: drag to move, scroll to zoom in or out',
    crop_hint: 'Drag to move the crop frame · scroll to zoom in or out',
    legend_crop: 'Crop',
    aspect_aria: 'Crop aspect ratio',
    rotate_left: 'Rotate left',
    rotate_right: 'Rotate right',
    flip_h: 'Flip horizontally',
    flip_v: 'Flip vertically',
    reset: 'Reset',
    legend_size: 'Output size',
    width_aria: 'Output width',
    legend_adjust: 'Adjust',
    brightness: 'Brightness',
    darken: 'Darken (easier to read text)',
    blur: 'Blur (px)',
    legend_display: 'Display in Orca',
    opacity: 'Wallpaper strength',
    fit: 'Fit',
    anchor: 'Anchor',
    legend_anim: 'Animation (only for animated GIF/WebP)',
    speed: 'Speed (×)',
    from_frame: 'From frame',
    to_frame: 'to',
    to_frame_title: '-1 means the last frame',
    every: 'every',
    keep_one: 'keep 1',
    legend_apply: 'Apply to',
    mode_patched: 'Patched Orca: still or animated, ≤ 16 MB',
    mode_stock: 'Stock Orca: still images only, ≤ 2 MB',
    preview_note: 'Preview under the terminal layer',
    preview_note_opacity: 'Preview under the terminal layer (Background Opacity {v})',
    preview_aria: 'Wallpaper preview in Orca',
    apply: 'Apply to Orca',
    cancel: 'Cancel',
    aspect_screen: 'Screen ({w}×{h})',
    aspect_full: 'Whole image (no crop)',
    width_screen: 'Screen ({px} px wide)',
    size_note: 'Output: {w}×{h} px (Orca accepts {minw}×{minh} to {max}×{max})',
    too_big: 'The image is larger than {mb} MB.',
    cannot_open: "Couldn't read this image.",
    rate_limited: 'Orca is limiting the send rate; waiting {s} s before continuing…',
    sending: 'Sending the image to the worker…',
    sending_n: 'Sending the image to the worker… {i}/{n}',
    processing: 'Processing the image…',
    failed: "Couldn't apply: {e}",
    cancelled: 'Cancelled. The current wallpaper is unchanged.',
    timeout: 'Processing took over 15 minutes, so I stopped waiting. Try a smaller or shorter image.',
    worker_restarted: 'The worker restarted and the result was lost. Press Apply again.',
    waiting_worker: 'Waiting for the worker… ({e})',
    unknown_error: 'unknown error',
    adjusted: 'Adjusted automatically: {list}',
    reload_failed: 'Orca could not load the theme folder yet. Add it under Settings → Plugins → Development folders: {folder}',
    applied: 'Applied to {name}: {summary}.{note}\nSelect (or reselect) the "{name}" theme under Settings → Appearance to see the new image.\nTheme folder: {folder}'
  }
}

/** Two-letter language of Orca's UI ("vi-VN" gives "vi"); a language without a table uses English. */
function detectLanguage() {
  const tag = String(globalThis.orca?.locale || navigator.language || 'en').toLowerCase()
  const code = tag.split(/[-_]/)[0]
  return MESSAGES[code] ? code : 'en'
}

let language = detectLanguage()

/** Text for a key in the current language, with {name} placeholders filled from `params`. */
function tr(key, params = {}) {
  const text = (MESSAGES[language] ?? MESSAGES.en)[key] ?? MESSAGES.en[key] ?? key
  return text.replace(/\{(\w+)\}/g, (_, name) => (params[name] ?? `{${name}}`))
}

/** Fills the static texts of index.html: data-i18n (text), data-i18n-title and data-i18n-aria. */
function translateDocument() {
  document.documentElement.lang = language
  for (const el of document.querySelectorAll('[data-i18n]')) el.textContent = tr(el.dataset.i18n)
  for (const el of document.querySelectorAll('[data-i18n-title]')) el.title = tr(el.dataset.i18nTitle)
  for (const el of document.querySelectorAll('[data-i18n-aria]')) el.setAttribute('aria-label', tr(el.dataset.i18nAria))
}
