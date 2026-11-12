# Wallpaper Studio

Use your own picture as an Orca wallpaper. Pick an image, crop and adjust it, and Wallpaper Studio turns it into the background of a **My Wallpaper** theme that it keeps up to date for you.

- Opens JPG, PNG, WebP, BMP and GIF (animated too), up to 50 MB.
- A crop editor with aspect ratios (screen, 16:9, 16:10, 21:9, 4:3, the whole image), rotate and flip, brightness, darken and blur, and a live preview under Orca's translucent terminal.
- Three wallpaper slots (**My Wallpaper**, **My Wallpaper 2**, **My Wallpaper 3**), each with a dark-sidebar and a light-sidebar variant, plus a Cancel button while it works.
- **Video wallpapers** (Orca 1.4.254 or newer): open an MP4, MOV, WebM, MKV or AVI video, or an animated GIF/WebP, trim it to up to 60 seconds, change its speed, crop and adjust it like a picture, and Studio encodes an H.264 MP4 of at most 8 MB (20 fps, no audio) and sets it as the theme's `background.videoPath`. A still copy of the first frame stays beside it as the fallback. Orca plays it only while Background Opacity is below 1 and Reduce Visual Effects is off. Needs `ffmpeg` (see Requirements).
- A panel that follows Orca's language (Vietnamese or English).
- A desktop tool (`tools/wallpaper_studio.py`) with the same editor in a small Tk window.

It is one plugin and needs no other: the **My Wallpaper** themes are part of Wallpaper Studio itself.

## Requirements

- Orca **1.4.246 or newer**.
- **Python 3 with [Pillow](https://pypi.org/project/Pillow/)**: `pip install Pillow`. The plugin looks for Python by itself (`py -3`, `python3`, `python` and the usual per-user install folders). Set **Python with Pillow** in the plugin's settings only if it cannot find one.
- **ffmpeg with libx264, only for video wallpapers**: `pip install imageio-ffmpeg` (into the same Python; it brings its own ffmpeg), or put `ffmpeg` on your `PATH`, or set the `WALLPAPER_FFMPEG` environment variable to the executable. Pictures work without it.

## Install

1. **Get the plugin into Orca.** The simplest way is **Settings → Plugins → Install plugin → Git URL** with `https://github.com/dohaidang/orca-wallpaper-studio`. To have everything in this single plugin, clone the repository and load the clone as a development folder instead (**Settings → Plugins → Development folders**, or `orca plugin dev load <clone folder>`); see the note below.
2. Wallpaper Studio runs its own code in a separate process with your user account's access, so Orca asks you to approve it before it starts. Read what it lists and approve it if you trust it.
3. Open the **Wallpaper Studio** panel from the right sidebar (the layers icon), choose an image, crop it and press **Apply to Orca**.
4. Under **Settings → Appearance**, select the **My Wallpaper** theme. Set **Background Opacity** below 1 and turn **Reduce Visual Effects** off, so Orca paints the wallpaper behind the terminal.

**One plugin, or one extra folder.** Orca reads a theme's wallpaper only from inside the plugin that contributes the theme, and a plugin installed from the catalog or a Git URL sits in a read-only folder. Loaded as a development folder, Studio writes your picture straight into its own folder and everything is one plugin. Installed from a Git URL, it cannot, so the first time you press Apply it creates a small theme plugin named **Orca My Wallpaper** in your home folder and loads it into Orca for you (Orca shows it as "Dev · unverified", because the pictures are yours); after that it only rewrites the picture. You can choose that folder with the plugin's **My Wallpaper themes folder** setting. In that case you will see two sets of My Wallpaper themes; use the one from the extra folder.

Your original pictures and their crop settings are kept in `%APPDATA%\orca-wallpaper-studio\library` (set `WALLPAPER_STUDIO_LIBRARY` to move it), so a slot can be reopened later and updating the plugin never loses them.

## How it works

An Orca panel cannot write files, and one panel message carries at most 64 KiB. So the panel sends the chosen image to the plugin's worker in chunks, and the worker runs `tools/wallpaper_cli.py`. That uses Pillow to crop, adjust and encode the image as a WebP that Orca accepts, writes it into the My Wallpaper theme folder, updates the slot's theme files and reloads that folder in Orca.

Orca restarts a development plugin's worker (and may reload its panel) whenever a file in the plugin folder changes, and Studio changes files there when it saves your picture. So the encode does not depend on the worker: it runs as a separate process that reports its progress and result in a small job file under `%APPDATA%\orca-wallpaper-studio\jobs`, and the worker and panel read that file, including after a restart.

Limits Orca puts on a theme background: 640×360 to 4096×4096, a still WebP, PNG or JPEG of at most 2 MB. Stock Orca refuses **animated** WebP backgrounds (it plays a looping video instead), so the panel has two modes under "Apply to": **Stock Orca** (the default: a still image of at most 2 MB, which any Orca accepts) and **Patched Orca** (animated allowed, up to 16 MB, only for an Orca you modified to accept it). The tool lowers quality or size until the result fits.

## Desktop tool

```sh
python -I tools\wallpaper_studio.py
```

`tools\Mo-trinh-chinh-anh.bat` starts the same tool and `tools\Doi-hinh-nen.bat` sets a wallpaper from a dragged image. They use the same **Orca My Wallpaper** folder; set `WALLPAPER_THEMES_DIR` to use another one.

## Languages

The panel follows Orca's UI language. Vietnamese and English are provided and any other language shows English. Texts are in `panel/i18n.js`; the Python tool's messages are in `tools/wallpaper_core.py` (`_MESSAGES`). To add a language, add a table to each.

## Develop

```sh
orca plugin validate .
orca plugin dev watch .      # loads this folder into Orca and prints its logs
python -I tools/test_wallpaper.py
```

## License

[MIT](LICENSE)
