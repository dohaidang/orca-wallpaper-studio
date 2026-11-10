# Wallpaper Studio

Use your own picture as an Orca wallpaper. Pick an image, crop and adjust it, and Wallpaper Studio turns it into the background of the **ASCII · My Wallpaper** themes.

- Opens JPG, PNG, WebP, BMP and GIF (animated too), up to 50 MB.
- A crop editor with aspect ratios (screen, 16:9, 16:10, 21:9, 4:3, the whole image), rotate and flip, brightness, darken and blur, and a live preview under Orca's translucent terminal.
- Three wallpaper slots, a Cancel button while it works, and a panel that follows Orca's language (Vietnamese or English).
- A desktop tool (`tools/wallpaper_studio.py`) with the same editor in a small Tk window.

## Requirements

- Orca **1.4.246 or newer**.
- **Python 3 with [Pillow](https://pypi.org/project/Pillow/)**: `pip install Pillow`. The plugin looks for Python by itself (`py -3`, `python3`, `python` and the usual per-user install folders). Set **Python with Pillow** in the plugin's settings only if it cannot find one.
- **The ASCII Themes plugin's `animated` branch** on your disk, because the My Wallpaper themes live there. Clone it (`git clone --branch animated https://github.com/dohaidang/orca-theme-plugin`), load that folder in Orca under **Settings → Plugins → Install plugin → Local folder**, then set **ASCII Themes folder** in Wallpaper Studio's settings to the same folder.

## Install

1. In Orca, open **Settings → Plugins → Install plugin → Git URL** and enter `https://github.com/dohaidang/orca-wallpaper-studio`. (From a clone you can use **Local folder** instead.)
2. Wallpaper Studio runs its own code in a separate process with your user account's access, so Orca asks you to approve it before it starts. Read what it lists and approve it if you trust it.
3. In the plugin's settings, set **ASCII Themes folder**.
4. Open the **Wallpaper Studio** panel from the right sidebar (the layers icon), choose an image, crop it and press **Apply to Orca**. Then select **ASCII · My Wallpaper** under **Settings → Appearance**.

Your pictures are kept in `%APPDATA%\orca-wallpaper-studio\library` (set `WALLPAPER_STUDIO_LIBRARY` to move it), outside the plugin, so updating or reinstalling the plugin does not lose them.

## How it works

An Orca panel cannot write files, and one panel message carries at most 64 KiB. So the panel sends the chosen image to the plugin's worker in chunks, and the worker runs `tools/wallpaper_cli.py`. That uses Pillow to crop, adjust and encode the image as a WebP that Orca accepts, writes it into the ASCII Themes folder, updates the slot's theme files and reloads the plugin.

Limits Orca puts on a theme background: 640×360 to 4096×4096, a still WebP, PNG or JPEG of at most 2 MB. Stock Orca refuses **animated** WebP backgrounds (it plays a looping video instead), so the panel has two modes under "Apply to": **Stock Orca** (the default: a still image of at most 2 MB, which any Orca accepts) and **Patched Orca** (animated allowed, up to 16 MB, only for an Orca you modified to accept it). The tool lowers quality or size until the result fits.

## Desktop tool

```sh
set ASCII_THEMES_DIR=C:\path\to\orca-theme-plugin
python -I tools\wallpaper_studio.py
```

`tools\Mo-trinh-chinh-anh.bat` starts the same tool and `tools\Doi-hinh-nen.bat` sets a wallpaper from a dragged image. Both need `ASCII_THEMES_DIR`.

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
