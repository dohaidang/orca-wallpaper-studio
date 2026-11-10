# Wallpaper Studio

Pick any image, crop and adjust it, and set it as the wallpaper of the **ASCII · My Wallpaper** themes in Orca. It comes in two forms that share one image pipeline:

- **An Orca plugin** (`studio-plugin/`): a panel in the right sidebar with a crop editor, live preview, adjustments, three wallpaper slots, a Cancel button, and a UI that follows Orca's language (Vietnamese or English).
- **A desktop tool** (`wallpaper_studio.py`): the same editor as a small Tk window, plus a drag-and-drop script (`set-wallpaper.py`).

An Orca panel cannot write files, so the panel sends the chosen image to the plugin's worker in chunks. The worker runs `wallpaper_cli.py`, which uses Pillow to crop, adjust and encode the image to a WebP that Orca accepts, then writes the slot's theme files into the ASCII Themes plugin.

## Requirements

- Windows, Python 3 with [Pillow](https://pypi.org/project/Pillow/) (`pip install Pillow`).
- Orca 1.4.246 or newer.
- The ASCII Themes plugin with the My Wallpaper themes (the `animated` branch of [orca-theme-plugin](https://github.com/dohaidang/orca-theme-plugin)).

## Set up the Orca plugin

1. Open **Settings → Plugins → Install plugin → Local folder** and choose `studio-plugin/`. It runs a worker with your account's access, so Orca asks you to approve it.
2. In the plugin's settings, set **Wallpaper tools folder** to this repository's folder and **Python with Pillow** to the full path of a `python.exe` that has Pillow.
3. Open the **Wallpaper Studio** panel (the layers icon), choose an image, crop it and press **Apply to Orca**. Then select **ASCII · My Wallpaper** under **Settings → Appearance**.

`PLUGIN_DIR` in `wallpaper_core.py` is the folder of the ASCII Themes plugin that holds the My Wallpaper themes; change it to match your machine. The defaults in `studio-plugin/orca-plugin.json` and `studio-plugin/src/worker.ts` are the author's own paths.

## What it does to your image

- Accepts JPG, PNG, WebP, BMP and GIF (animated GIFs too), up to 50 MB.
- Exports a WebP between 640×360 and 4096×4096. In patched Orca it may be animated and up to 16 MB; for a stock Orca it is a still image of at most 2 MB. The tool lowers quality or size until it fits.
- Your images are kept in `library/` (not part of this repository) so a slot can be reopened later.

## Language

The panel follows Orca's UI language. Vietnamese and English are provided and any other language shows English. Texts are in `studio-plugin/panel/i18n.js`; the Python tool's messages are in `wallpaper_core.py` (`_MESSAGES`). To add a language, add a table to each.

## Test

```sh
python -I test_wallpaper.py
orca plugin validate studio-plugin
```

## License

MIT
