# Converto

A native Linux file converter inspired by the publicly demonstrated workflow of Tangerine. Independently implemented in Python and GTK; no Tangerine code, binaries, branding, or assets are included. No reverse-engineering tool is required.

**Version 0.1: a working first release, not feature parity with Tangerine.** Developed and tested on Zorin OS 18.1 / GNOME / X11.

## Run

```sh
./run.sh
```

Choose files or drop them into the window (drops add to the list). Review the file list, pick a format, and press the **Convert** button. Each file shows its own progress, result, or error, with a **Show** shortcut to the output folder. Outputs are saved next to each original; existing filenames receive a numeric suffix. The application never overwrites sources. Cancelling a batch preserves already completed results and removes the current job's temporary files.

### Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| Ctrl+O / Ctrl+Shift+O | Add files / add folder |
| Ctrl+Enter | Start the conversion |
| Esc | Cancel the running job |
| Ctrl+Shift+C | Copy selected file paths |
| Ctrl+Shift+Delete | Clear the list |
| Ctrl+Q | Quit |

## Right-click → Convert

In GNOME Files (Nautilus 43 or later), right-click one or more local files and choose **Convert**. Converto opens with those files selected and shows compatible output formats. It does not have to be running beforehand. Folders are supported for archive creation.

Install the action for your user account:

```sh
python3 install-context-menu.py
```

Requires `python3-nautilus` (already present on this Zorin machine). Restart Files after installing if it was running. To remove the action, run `python3 install-context-menu.py --uninstall` and restart Files.

The Shift-drag shortcut has been removed from the application. Ordinary drag-and-drop into the window still works. The right-click integration uses Nautilus's native menu provider and works independently of X11/Wayland. Remote URLs and virtual selections are omitted.

## Included

| Inputs | Outputs / tools |
| --- | --- |
| PNG, JPEG, WebP, BMP, TIFF, single-frame GIF, ICO, TGA, PPM/PGM, single-frame PSD | PNG, JPEG, WebP, TIFF, BMP, PDF, GIF, ICO, TGA, PPM; fit within 1920 px, rotate clockwise, remove metadata |
| Common audio files | MP3, WAV, FLAC, OGG, Opus, M4A, AAC, AIFF, WMA, AC3; loudness normalization to WAV |
| Common video files | MP4, WebM, MKV, GIF, MOV, AVI, WMV, MPEG, TS; audio extraction to supported audio outputs |
| DOC/DOCX, ODT, RTF, TXT, HTML | PDF, DOCX, ODT, TXT, HTML, DOC, RTF, EPUB through LibreOffice |
| XLS/XLSX, ODS, CSV, TSV | PDF, XLSX, ODS, CSV, XLS through LibreOffice; CSV ↔ TSV with quoted-cell handling |
| PPT/PPTX, ODP | PDF, PPTX, ODP, PPT through LibreOffice |
| PDF | Every page to PNG/JPEG/WebP/TIFF/BMP at 150 DPI; text extraction |
| SRT, VTT | SRT, VTT, plain text |
| Files and folders | ZIP, TAR, TAR.GZ, TAR.BZ2, TAR.XZ creation; symlinks excluded |

Batch selections show only common destinations. Each selected item produces its own output (including one archive per selected item). PDF image export makes one file per page. Conversions use local installed engines; unsupported codec or document content produces a visible error. No network calls are made by Converto.

### Current limits

- No archive extraction or archive-to-archive conversion yet.
- No HEIC/AVIF/SVG, Apple Pages, EPUB input, PDF-to-editable-Office, OCR, PDF merging, or advanced media editing yet.
- Animated and multipage image input is explicitly rejected rather than silently losing frames. GIF video export is supported.
- ICO exports fit artwork into a transparent 256 × 256 canvas and include standard icon sizes. GIF image export is single-frame; GIF video export retains animation. PPM flattens transparency onto white.
- Image conversions omit EXIF; “Remove metadata” additionally drops image profile/text metadata and exports PNG (JPEG for JPEG input). JPEG/PDF use white behind transparency.
- Removing metadata preserves palette and color-key transparency. CMYK images are converted to RGB for PNG, BMP, GIF, and TGA export; these conversions are not ICC color-managed.
- Spreadsheet CSV export follows LibreOffice's sheet/filter defaults. It does not preserve an entire multi-sheet workbook.
- Subtitle conversion retains ordinary cue text/timing; styling, cue settings, and WEBVTT regions/notes are not preserved in SRT/TXT.
- There is no background autostart, tray icon, global Wayland integration, or adjustable quality interface yet. Closing the window quits the app; closing during a job asks you to cancel first.
- Cancelling Python image decoding or a single archive member takes effect when that operation returns. External processes can be terminated promptly.
- Output folders must be writable and support hard links for atomic, collision-safe publishing. Typical Linux filesystems do; some removable filesystems may not.

## Dependencies

Uses the system Python. On Ubuntu/Zorin/Debian:

```sh
sudo apt install python3 python3-gi python3-gi-cairo python3-pil gir1.2-gtk-3.0 ffmpeg libreoffice poppler-utils
```

These dependencies were already present on the development machine. Optional converters are hidden when their executables are missing. No Python package installation is needed.

## Command line

```sh
./run.sh --to webp /absolute/path/photo.png
./run.sh --to mp3 /absolute/path/audio.wav
./run.sh --to zip /absolute/path/folder
```

## Validation

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Tests that need FFmpeg, Poppler, LibreOffice, or Nautilus skip when those optional dependencies are absent. GitHub Actions installs the converters and runs the complete suite on Ubuntu. Image regression tests cover transparent metadata removal and CMYK exports. The context-menu integration tests verify the actual Nautilus menu provider, multi-selection, remote-location filtering, and exact filename handoff. See [research and roadmap](docs/RESEARCH.md) for the original feature study.

## Structure

- `converto/core.py`: conversion routing, subprocess cancellation, collision-safe output publishing.
- `converto/app.py`: native desktop window, batch queue, status and output actions.
- `converto/files.py`: local drag-and-drop URI decoding.
- `integrations/converto-nautilus.py.in`: native Files context-menu extension.
- `install-context-menu.py`: per-user installation and removal.
- `converto/wheel.py`: historical prototype; no longer loaded by the app.
- `converto/__main__.py`: GUI/CLI entry point.

No daemon, administrator privileges, or network service is needed to run Converto.
