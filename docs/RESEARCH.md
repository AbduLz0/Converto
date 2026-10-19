# Tangerine study and Converto scope

Research date: 19 October 2026. Sources are public descriptions, not observations of the installed Mac application. We have neither a Mac nor the application bundle; no claim about Tangerine's internal implementation is made.

## Interaction update — 19 October 2026

Following user testing, the Shift-drag shortcut was replaced by a native Nautilus right-click **Convert** action. It hands local selections to Converto in a separate process and resets the app to conversion mode. The old wheel is no longer loaded; its code and synthetic smoke test remain historical prototypes. The wheel descriptions and verification below document the initial design, not the current user workflow.

## Product behavior

The [official website](https://tangerineformac.com/) advertises 275 conversion paths, 26 tools, and six file actions. It lists image, audio, video, PDF, document, slide, spreadsheet, ebook, subtitle, and archive categories. Its browser interaction is explicitly a simulation, not a working converter. The website describes tapping Shift during a drag for conversions, Command for tools, and Control for file actions. The wheel stays open after releasing the modifier. Some advertised formats are input-only.

The [press kit](https://tangerineformac.com/press) describes a contextual radial menu at the pointer, locally processed jobs, and new copies saved beside originals. File actions include AirDrop, Float, Copy, Move, Copy Path, and Terminal, and can act on mixed selections and folders. This supports three product requirements for our independent implementation: fast access from a file drag, choices constrained by input types, and preservation of originals.

The [App Store listing](https://apps.apple.com/us/app/tangerine-file-converter/id6813034065?mt=12) describes batch handling, job progress, revealing outputs, and a menu-bar presence. Its tool list includes compression, image editing, media trimming and normalization, metadata editing, PDF manipulation, and QR reading. It describes Option+Shift for tools, whereas the current website uses Command. Format lists also differ. Treat these as version-dependent claims; a Linux app should not claim all combinations are supported without conversion tests.

## Independent Linux design

Converto uses GTK 3 for real desktop drag-and-drop, Pillow for basic raster processing, FFmpeg for media, LibreOffice for office documents, Poppler for PDF rendering/text extraction, and Python's standard library for archives/tabular text/subtitles. These choices are ours, not findings about Tangerine.

Sources for integration behavior: [GTK drag destinations](https://docs.gtk.org/gtk3/method.Widget.drag_dest_set.html), [Xlib pointer APIs](https://xorg.freedesktop.org/archive/current/doc/libX11/libX11/libX11.html), and [FFmpeg CLI](https://ffmpeg.org/ffmpeg.html).

The X11 wheel polls pointer/modifier state and accepts file URIs via GTK's Xdnd support. It does not inspect other processes, scrape file-manager selections, or record typing. Wayland needs compositor-specific integration for an equivalent global gesture; the ordinary drop window is the supported fallback for now.

## Roadmap

| Capability | Version 0.1 | Follow-up work |
| --- | --- | --- |
| Contextual conversions | Common targets across batch selection | Per-format quality/preset controls |
| Drag wheel | X11 implementation; GTK-source end-to-end test passed | Nautilus/Nemo/Thunar and multi-monitor validation; keyboard navigation |
| Wayland | Drop into app window | GNOME Shell integration or supported desktop APIs |
| Images | Basic conversion, rotate, resize, strip metadata | HEIC/AVIF/SVG, animation, cropping, previews |
| Audio/video | Conversion/extraction; audio normalization | Trim, compression target, joining, waveform/video previews |
| PDF | Page images and text extraction | Merge/split/reorder, OCR; editable export needs separate quality assessment |
| Office | LibreOffice-backed subset | Richer format-specific export controls and fixture coverage |
| Subtitles | Basic timing/text conversion | Styling and richer cue metadata |
| Archives | Create ZIP and TAR.GZ | Safe extraction and repacking with resource limits |
| File actions | Copy paths, open output folder | Copy/move, terminal, desktop sharing integration |
| Background lifecycle | Window can be minimized | Tray, optional autostart, job notifications |

## Verification record

Twelve engine tests passed on the target machine: transparency/JPEG, unchanged originals and collisions, early cancellation, damaged-input cleanup, animation rejection, CSV quoting, subtitle roundtrip, symlink-safe ZIP creation, mixed-selection formats, resize/rotate, real FFmpeg audio/video, two-page PDF rendering, and LibreOffice conversion (some assertions share a test case).

The X11 desktop smoke test passed the complete synthetic drag-to-conversion flow. Native window layout was visually inspected. Real Tangerine fidelity, exhaustive format combinations, Wayland, and every file manager remain unverified.
