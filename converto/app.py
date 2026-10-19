from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio, Pango
from .core import convert, common_targets, tools_for, category, Cancelled
from .files import uri_paths

CSS = b'''
@define-color bg #10151d;
@define-color surface #18222d;
@define-color surface2 #1f2c3a;
@define-color line #2e4152;
@define-color text #eaf0f6;
@define-color muted #9badbd;
@define-color accent #72dfba;
@define-color accent_ink #0d211b;
@define-color danger #ff9a8f;

window, .view { background: @bg; color: @text; }
headerbar { background: #151c26; border: none; box-shadow: none; }
label { color: @text; }
scrolledwindow, scrolledwindow viewport { border: none; background: transparent; }

.eyebrow { color: @accent; font-size: 11px; font-weight: bold; letter-spacing: 2px; }
.title { font-size: 30px; font-weight: 800; }
.subtitle { color: @muted; font-size: 14px; }
.section { color: @muted; font-size: 11px; font-weight: bold; letter-spacing: 1.5px; }
.meta { color: @muted; font-size: 12px; }
.status-ok { color: @accent; font-size: 13px; font-weight: bold; }
.status-error { color: @danger; font-size: 13px; font-weight: bold; }
.status-idle { color: @muted; font-size: 13px; }
.error-detail { color: @danger; font-size: 12px; }

.drop { background: @surface; border: 2px dashed #3b5b5a; border-radius: 18px; transition: all 120ms ease; }
.drop.compact { border-radius: 14px; }
.drop.drag-over { background: #1b3430; border-color: @accent; }
.card { background: @surface; border-radius: 12px; }
.filerow { border-bottom: 1px solid #202c39; }
list, row { background: transparent; }
row:selected, row:hover { background: transparent; }

button { background: #253343; color: @text; border: 1px solid #334658; border-radius: 9px;
         padding: 8px 16px; box-shadow: none; text-shadow: none; background-image: none; }
button:hover { background: #31485a; }
button:disabled { color: #6b7b8b; background: #1b2530; border-color: #243140; }
button:focus { outline: 2px solid @accent; outline-offset: 2px; outline-style: solid; }
button.primary { background: @accent; color: @accent_ink; border-color: @accent; font-weight: bold; padding: 10px 22px; }
button.primary:hover { background: #8aebcb; }
button.primary:disabled { background: #25453e; color: #7aa398; border-color: #25453e; }
button.format { font-size: 14px; font-weight: bold; padding: 12px 18px; min-width: 56px; }
button.format:checked { background: @accent; color: @accent_ink; border-color: @accent; }
button.ghost { background: transparent; border-color: transparent; padding: 4px 8px; color: @muted; }
button.ghost:hover { background: #253343; color: @text; }
button.seg { padding: 8px 20px; border-radius: 0; font-weight: bold; }
button.seg:first-child { border-radius: 9px 0 0 9px; }
button.seg:last-child { border-radius: 0 9px 9px 0; }
button.seg:checked { background: #2d4a5c; border-color: @accent; color: @accent; }

.bar { background: #151c26; border-top: 1px solid #243140; padding: 12px 24px; }
progressbar trough { background: #253343; border: none; min-height: 6px; border-radius: 3px; }
progressbar progress { background: @accent; border: none; min-height: 6px; border-radius: 3px; }
'''

KIND = {
    'image': ('Image', 'image-x-generic'), 'audio': ('Audio', 'audio-x-generic'),
    'video': ('Video', 'video-x-generic'), 'document': ('Document', 'x-office-document'),
    'spreadsheet': ('Spreadsheet', 'x-office-spreadsheet'), 'slides': ('Presentation', 'x-office-presentation'),
    'pdf': ('PDF', 'application-pdf'), 'subtitle': ('Subtitles', 'text-x-generic'),
    'folder': ('Folder', 'folder'), 'file': ('File', 'text-x-generic'),
}
ARCHIVES = {'zip', 'tar', 'tar.gz', 'tar.bz2', 'tar.xz'}
TOOLS = {'resize': 'Fit in 1920 px', 'strip': 'Remove metadata', 'rotate': 'Rotate 90°', 'normalize': 'Normalize audio'}
TOOL_HINTS = {
    'resize': 'Shrinks large images to fit within 1920 px. Smaller images are untouched.',
    'strip': 'Removes EXIF, profiles and text metadata from the copy.',
    'rotate': 'Rotates a copy 90° clockwise.',
    'normalize': 'Evens out loudness and saves a WAV copy.',
}
FORMAT_NAMES = {
    'jpg': 'JPEG image', 'png': 'PNG image', 'webp': 'WebP image', 'tiff': 'TIFF image', 'bmp': 'Bitmap image',
    'pdf': 'PDF document', 'gif': 'GIF', 'ico': 'Windows icon', 'mp3': 'MP3 audio', 'wav': 'WAV audio',
    'flac': 'FLAC lossless audio', 'opus': 'Opus audio', 'm4a': 'AAC in M4A', 'mp4': 'MP4 video',
    'webm': 'WebM video', 'mkv': 'Matroska video', 'docx': 'Word document', 'xlsx': 'Excel workbook',
    'pptx': 'PowerPoint presentation', 'txt': 'Plain text', 'zip': 'ZIP archive', 'tar.gz': 'Gzip-compressed TAR',
}


def human_size(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024


def plural(n, word):
    return f'{n} {word}' + ('' if n == 1 else 's')


def label(text, style=None, wrap=True):
    obj = Gtk.Label(label=text, xalign=0)
    if wrap: obj.set_line_wrap(True)
    if style: obj.get_style_context().add_class(style)
    return obj


def button(text, callback=None, style=None):
    obj = Gtk.Button(label=text)
    if callback: obj.connect('clicked', callback)
    if style: obj.get_style_context().add_class(style)
    return obj


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='io.converto.desktop', flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.window = None
        self.paths = []
        self.items = {}
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.cancel = threading.Event()
        self.busy = False
        self.results = []
        self.choice = None
        self.mode = 'convert'
        self.pending_paths = None
        self.chips = {}
        self.syncing = False
        self.pulse_id = None
        self.actions = {}

    # ---------- lifecycle ----------
    def do_activate(self):
        if self.window is None: self.build()
        self.window.present()

    def do_open(self, files, n_files, hint):
        self.do_activate()
        paths = [Path(f.get_path()) for f in files if f.get_path()]
        if self.busy:
            self.pending_paths = paths
            self.set_status('Files received. They will open when the current batch finishes.')
            return
        self.mode = 'convert'
        self.select(paths, replace=True)

    # ---------- construction ----------
    def build(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window = Gtk.ApplicationWindow(application=self, title='Converto')
        self.window.set_default_size(860, 780)
        self.window.set_size_request(560, 520)
        self.window.connect('delete-event', self.close)
        self.build_actions()
        self.build_header()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.window.add(root)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        root.pack_start(scroll, True, True, 0)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.set_border_width(28)
        scroll.add(box)

        # Hero: only while the list is empty, so working screens stay compact.
        self.hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.hero.pack_start(label('LOCAL BY DESIGN', 'eyebrow'), False, False, 0)
        self.hero.pack_start(label('A new format.\nWithout the detour.', 'title'), False, False, 0)
        self.hero.pack_start(label('Drop your files, choose a format, and keep moving. New copies stay beside the originals.', 'subtitle'), False, False, 0)
        box.pack_start(self.hero, False, False, 0)

        # Drop zone
        self.drop = Gtk.EventBox()
        self.drop.get_style_context().add_class('drop')
        self.drop_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.drop_inner.set_border_width(24)
        self.drop.add(self.drop_inner)
        self.drop_label = label('↓   Drop files or folders here', 'subtitle')
        self.drop_label.set_xalign(.5)
        self.drop_label.set_justify(Gtk.Justification.CENTER)
        self.drop_inner.pack_start(self.drop_label, False, False, 0)
        row = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        row.pack_start(button('Choose files', lambda _: self.choose(), 'primary'), False, False, 0)
        row.pack_start(button('Choose folder', lambda _: self.choose(True)), False, False, 0)
        self.drop_inner.pack_start(row, False, False, 0)
        box.pack_start(self.drop, False, False, 0)
        targets = [Gtk.TargetEntry.new('text/uri-list', 0, 0)]
        self.window.drag_dest_set(Gtk.DestDefaults.MOTION | Gtk.DestDefaults.DROP, targets, Gdk.DragAction.COPY)
        self.window.connect('drag-motion', self.drag_motion)
        self.window.connect('drag-leave', lambda *a: self.drop.get_style_context().remove_class('drag-over'))
        self.window.connect('drag-data-received', self.drag_received)

        # Queue
        self.queue = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        head = Gtk.Box(spacing=8)
        self.queue_title = label('', 'section', wrap=False)
        head.pack_start(self.queue_title, True, True, 0)
        self.clear_btn = button('Clear all', lambda _: self.clear(), 'ghost')
        head.pack_end(self.clear_btn, False, False, 0)
        self.queue.pack_start(head, False, False, 0)
        card = Gtk.Box()
        card.get_style_context().add_class('card')
        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.NONE)
        card.pack_start(self.list, True, True, 0)
        self.queue.pack_start(card, False, False, 0)
        box.pack_start(self.queue, False, False, 0)

        # Controls
        self.controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        modes = Gtk.Box()
        modes.get_style_context().add_class('linked')
        self.convert_tab = Gtk.ToggleButton(label='Convert')
        self.tools_tab = Gtk.ToggleButton(label='File tools')
        for tab, mode in ((self.convert_tab, 'convert'), (self.tools_tab, 'tools')):
            tab.get_style_context().add_class('seg')
            tab.connect('toggled', self.tab_toggled, mode)
            modes.pack_start(tab, False, False, 0)
        self.controls.pack_start(modes, False, False, 0)
        self.format_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.controls.pack_start(self.format_box, False, False, 0)
        self.hint = label('', 'subtitle')
        self.controls.pack_start(self.hint, False, False, 0)
        box.pack_start(self.controls, False, False, 0)

        # Empty-state tip
        self.tip = Gtk.Box(spacing=12)
        self.tip.get_style_context().add_class('card')
        self.tip.set_border_width(0)
        tip_inner = Gtk.Box(spacing=12, margin=16)
        tip_inner.pack_start(Gtk.Image.new_from_icon_name('input-mouse-symbolic', Gtk.IconSize.LARGE_TOOLBAR), False, False, 0)
        tip_inner.pack_start(label('Right-click → Convert\nSelect files in Files, right-click, then choose Convert. Install it with install-context-menu.py.', 'subtitle'), True, True, 0)
        self.tip.pack_start(tip_inner, True, True, 0)
        box.pack_start(self.tip, False, False, 0)

        # Action bar (always visible)
        bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        bar.get_style_context().add_class('bar')
        self.progress = Gtk.ProgressBar()
        bar.pack_start(self.progress, False, False, 0)
        line = Gtk.Box(spacing=12)
        self.status = label('Ready · Nothing leaves your computer', 'status-idle', wrap=False)
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        line.pack_start(self.status, True, True, 0)
        self.reveal = button('Open output folder', self.open_output)
        line.pack_start(self.reveal, False, False, 0)
        self.stop = button('Cancel', lambda _: self.cancel.set())
        line.pack_start(self.stop, False, False, 0)
        self.start = button('Choose a format', lambda _: self.run_selected(), 'primary')
        line.pack_start(self.start, False, False, 0)
        bar.pack_start(line, False, False, 0)
        root.pack_end(bar, False, False, 0)

        self.window.show_all()
        self.refresh()

    def build_actions(self):
        def add(name, callback, accels=None):
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', lambda *_: callback())
            self.add_action(action)
            self.actions[name] = action
            if accels: self.set_accels_for_action(f'app.{name}', accels)
        add('add-files', lambda: self.choose(), ['<Primary>o'])
        add('add-folder', lambda: self.choose(True), ['<Primary><Shift>o'])
        add('clear', self.clear, ['<Primary><Shift>Delete'])
        add('copy-paths', self.copy_paths, ['<Primary><Shift>c'])
        add('convert', self.run_selected, ['<Primary>Return'])
        add('cancel', lambda: self.cancel.set() if self.busy else None, ['Escape'])
        add('quit', self.close, ['<Primary>q'])

    def build_header(self):
        header = Gtk.HeaderBar(title='Converto', show_close_button=True)
        add = Gtk.Button.new_from_icon_name('list-add-symbolic', Gtk.IconSize.BUTTON)
        add.set_tooltip_text('Add files (Ctrl+O)')
        add.set_action_name('app.add-files')
        header.pack_start(add)
        menu = Gio.Menu()
        files = Gio.Menu()
        files.append('Add files…', 'app.add-files')
        files.append('Add folder…', 'app.add-folder')
        files.append('Copy file paths', 'app.copy-paths')
        files.append('Clear list', 'app.clear')
        menu.append_section(None, files)
        quit_ = Gio.Menu()
        quit_.append('Quit', 'app.quit')
        menu.append_section(None, quit_)
        menu_button = Gtk.MenuButton()
        menu_button.set_image(Gtk.Image.new_from_icon_name('open-menu-symbolic', Gtk.IconSize.BUTTON))
        menu_button.set_menu_model(menu)
        menu_button.set_tooltip_text('Menu')
        header.pack_end(menu_button)
        self.window.set_titlebar(header)

    # ---------- drag and drop ----------
    def drag_motion(self, widget, context, x, y, time):
        if not self.busy: self.drop.get_style_context().add_class('drag-over')
        return False

    def drag_received(self, widget, context, x, y, data, info, time):
        self.drop.get_style_context().remove_class('drag-over')
        if self.busy:
            self.set_status('A job is running. Drop again after it finishes.')
            return
        self.select(uri_paths(data.get_uris()))

    # ---------- selection ----------
    def choose(self, folder=False):
        if self.busy: return
        dialog = Gtk.FileChooserDialog(title='Add folders' if folder else 'Add files', parent=self.window,
            action=Gtk.FileChooserAction.SELECT_FOLDER if folder else Gtk.FileChooserAction.OPEN)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Add', Gtk.ResponseType.OK)
        dialog.set_select_multiple(True)
        if dialog.run() == Gtk.ResponseType.OK: self.select([Path(p) for p in dialog.get_filenames()])
        dialog.destroy()

    def select(self, paths, replace=False):
        if self.busy: return
        merged = list(paths) if replace else self.paths + list(paths)
        self.paths = list(dict.fromkeys(merged))
        self.items = {}
        self.results = []
        self.progress.set_fraction(0)
        self.set_status('Ready · Nothing leaves your computer', 'status-idle')
        self.build_rows()
        self.set_mode(self.mode)

    def remove(self, path):
        if self.busy: return
        self.paths = [p for p in self.paths if p != path]
        self.select([], replace=False)

    def clear(self):
        if self.busy: return
        self.paths = []
        self.select([], replace=True)

    def build_rows(self):
        for child in self.list.get_children(): self.list.remove(child)
        for path in self.paths:
            kind_name, icon = KIND[category(path)]
            row = Gtk.ListBoxRow()
            row.set_activatable(False)
            row.set_selectable(False)
            line = Gtk.Box(spacing=12, margin=12)
            line.get_style_context().add_class('filerow')
            line.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.LARGE_TOOLBAR), False, False, 0)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            name = label(path.name, wrap=False)
            name.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            name.set_tooltip_text(str(path))
            try: size = '' if path.is_dir() else ' · ' + human_size(path.stat().st_size)
            except OSError: size = ''
            text.pack_start(name, False, False, 0)
            text.pack_start(label(kind_name + size, 'meta', wrap=False), False, False, 0)
            error = label('', 'error-detail')
            error.set_no_show_all(True)
            error.set_selectable(True)
            text.pack_start(error, False, False, 0)
            line.pack_start(text, True, True, 0)
            spinner = Gtk.Spinner()
            spinner.set_no_show_all(True)
            line.pack_start(spinner, False, False, 0)
            state = label('', 'meta', wrap=False)
            state.set_xalign(1)
            state.set_ellipsize(Pango.EllipsizeMode.END)
            state.set_max_width_chars(34)
            line.pack_start(state, False, False, 0)
            show = button('Show', None, 'ghost')
            show.set_no_show_all(True)
            show.set_tooltip_text('Open the folder with the converted file')
            line.pack_start(show, False, False, 0)
            remove = Gtk.Button.new_from_icon_name('window-close-symbolic', Gtk.IconSize.BUTTON)
            remove.get_style_context().add_class('ghost')
            remove.set_tooltip_text('Remove from list')
            remove.connect('clicked', lambda _, p=path: self.remove(p))
            line.pack_start(remove, False, False, 0)
            row.add(line)
            self.list.add(row)
            self.items[path] = dict(state=state, spinner=spinner, error=error, show=show, remove=remove, status='pending')
        self.list.show_all()
        for item in self.items.values():
            item['error'].hide(); item['spinner'].hide(); item['show'].hide()

    # ---------- modes and formats ----------
    def tab_toggled(self, tab, mode):
        if self.syncing or self.busy: return
        if tab.get_active(): self.set_mode(mode)
        else: self.sync_tabs()   # keep one tab always active

    def sync_tabs(self):
        self.syncing = True
        self.convert_tab.set_active(self.mode == 'convert')
        self.tools_tab.set_active(self.mode == 'tools')
        self.syncing = False

    def set_mode(self, mode):
        if self.busy: return
        self.mode, self.choice = mode, None
        has_tools = bool(tools_for(self.paths))
        if mode == 'tools' and not has_tools and self.paths: self.mode = mode = 'convert'
        self.tools_tab.set_sensitive(has_tools)
        self.tools_tab.set_tooltip_text(None if has_tools or not self.paths else 'Tools are available for all-image or all-audio selections')
        self.sync_tabs()
        for child in self.format_box.get_children(): child.destroy()
        self.chips = {}
        options = common_targets(self.paths) if mode == 'convert' else tools_for(self.paths)
        if mode == 'convert':
            groups = [('CONVERT TO', [o for o in options if o not in ARCHIVES]), ('OR COMPRESS INTO', [o for o in options if o in ARCHIVES])]
        else:
            groups = [('TOOLS', options)]
        for title, opts in groups:
            if not opts: continue
            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            section.pack_start(label(title, 'section'), False, False, 0)
            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_min_children_per_line(2)
            flow.set_max_children_per_line(8)
            flow.set_column_spacing(8)
            flow.set_row_spacing(8)
            flow.set_homogeneous(False)
            for option in opts:
                chip = Gtk.ToggleButton(label=TOOLS.get(option, option.upper()))
                chip.get_style_context().add_class('format')
                tip = TOOL_HINTS.get(option) or FORMAT_NAMES.get(option)
                if tip: chip.set_tooltip_text(tip)
                chip.connect('toggled', self.chip_toggled, option)
                self.chips[option] = chip
                flow.add(chip)
            section.pack_start(flow, False, False, 0)
            self.format_box.pack_start(section, False, False, 0)
        self.format_box.show_all()
        if not self.paths: hint = ''
        elif not options and mode == 'convert' and len({category(p) for p in self.paths}) > 1:
            hint = 'These files don\u2019t share an output format. Remove some, or convert them in separate batches.'
        elif not options: hint = 'No compatible formats for this selection.'
        else: hint = 'Pick an output format. Originals are always preserved.' if mode == 'convert' else 'Pick a tool. It runs on a copy and never touches the original.'
        self.hint.set_text(hint)
        self.refresh()

    def chip_toggled(self, chip, option):
        if self.syncing or self.busy: return
        self.syncing = True
        if chip.get_active():
            self.choice = option
            for other, widget in self.chips.items():
                if other != option: widget.set_active(False)
        elif self.choice == option:
            chip.set_active(True)   # radio behaviour
        self.syncing = False
        self.describe_choice()
        self.refresh()

    def describe_choice(self):
        option, first = self.choice, (category(self.paths[0]) if self.paths else None)
        if option in TOOL_HINTS and self.mode == 'tools': text = TOOL_HINTS[option]
        elif option == 'pdf' and first == 'image': text = 'Creates one PDF per image, with transparency on white.'
        elif option in {'png', 'jpg'} and first == 'pdf': text = 'Exports every PDF page as a separate image at 150 DPI.'
        elif option in ARCHIVES: text = 'Creates one archive per selected item. Symbolic links are skipped.'
        else: text = 'Existing files are never overwritten. Image exports omit EXIF metadata.'
        self.hint.set_text(text)

    # ---------- state ----------
    def refresh(self):
        has = bool(self.paths)
        self.hero.set_visible(not has)
        self.tip.set_visible(not has)
        self.queue.set_visible(has)
        self.controls.set_visible(has)
        ctx = self.drop.get_style_context()
        if has: ctx.add_class('compact')
        else: ctx.remove_class('compact')
        self.drop_label.set_text('Drop more files here to add them' if has else '↓   Drop files or folders here')
        self.drop_inner.set_border_width(12 if has else 24)
        self.queue_title.set_text(f'SELECTED · {len(self.paths)}')
        for name in ('clear', 'copy-paths'): self.actions[name].set_enabled(has and not self.busy)
        self.actions['add-files'].set_enabled(not self.busy)
        self.actions['add-folder'].set_enabled(not self.busy)
        self.clear_btn.set_sensitive(has and not self.busy)
        ready = bool(self.choice) and has and not self.busy
        self.actions['convert'].set_enabled(ready)
        self.actions['cancel'].set_enabled(self.busy)
        self.start.set_sensitive(ready)
        n = len(self.paths)
        if self.choice and self.mode == 'convert': self.start.set_label(f'Convert {plural(n, "item")} to {self.choice.upper()} →')
        elif self.choice: self.start.set_label(f'Apply “{TOOLS[self.choice]}” →')
        else: self.start.set_label('Choose a format' if self.mode == 'convert' else 'Choose a tool')
        self.stop.set_visible(self.busy)
        self.reveal.set_visible(bool(self.results) and not self.busy)

    def set_status(self, text, style='status-idle'):
        ctx = self.status.get_style_context()
        for cls in ('status-idle', 'status-ok', 'status-error'): ctx.remove_class(cls)
        ctx.add_class(style)
        self.status.set_text(text)
        self.status.set_tooltip_text(text)

    def set_busy_ui(self, busy):
        self.busy = busy
        self.format_box.set_sensitive(not busy)
        self.convert_tab.set_sensitive(not busy)
        self.tools_tab.set_sensitive(not busy and bool(tools_for(self.paths)))
        for item in self.items.values(): item['remove'].set_sensitive(not busy)
        self.refresh()

    # ---------- running ----------
    def run_selected(self):
        self.submit(self.paths, self.choice, self.mode)

    def submit(self, paths, choice, mode):
        if self.busy:
            self.set_status('A job is already running. Drop again after it finishes.')
            self.window.present()
            return
        if not paths or not choice: return
        paths = list(paths)
        total = len(paths)
        self.cancel = threading.Event()
        cancel = self.cancel
        self.results = []
        for item in self.items.values():
            item['status'] = 'pending'
            item['state'].set_text('Waiting')
            for cls in ('status-ok', 'status-error'): item['state'].get_style_context().remove_class(cls)
            item['error'].hide(); item['show'].hide()
        self.set_busy_ui(True)
        self.progress.set_fraction(0)
        if total == 1: self.pulse_id = GLib.timeout_add(120, self.pulse)
        self.window.present()

        def work():
            for i, path in enumerate(paths):
                if cancel.is_set(): break
                GLib.idle_add(self.row_working, path, i, total)
                try:
                    out = convert(path, choice, cancel, 'convert' if mode == 'convert' else choice)
                    GLib.idle_add(self.row_done, path, out)
                except Cancelled:
                    break
                except Exception as exc:
                    GLib.idle_add(self.row_error, path, str(exc))
            GLib.idle_add(self.done, total)
        self.pool.submit(work)

    def pulse(self):
        if not self.busy:
            self.pulse_id = None
            return False
        self.progress.pulse()
        return True

    def row_working(self, path, i, total):
        item = self.items.get(path)
        if item:
            item['status'] = 'working'
            item['state'].set_text('Working…')
            item['spinner'].show(); item['spinner'].start()
        if total > 1: self.progress.set_fraction(i / total)
        self.set_status(f'Processing {i + 1} of {total} · {path.name}')
        return False

    def row_done(self, path, outputs):
        self.results.extend(outputs)
        item = self.items.get(path)
        if item:
            item['status'] = 'done'
            item['spinner'].stop(); item['spinner'].hide()
            text = f'✓ {outputs[0].name}' if len(outputs) == 1 else f'✓ {plural(len(outputs), "file")} saved'
            item['state'].set_text(text)
            item['state'].get_style_context().add_class('status-ok')
            item['state'].set_tooltip_text('\n'.join(p.name for p in outputs))
            folder = outputs[0].parent
            item['show'].connect('clicked', lambda _, f=folder: Gio.AppInfo.launch_default_for_uri(f.as_uri(), None))
            item['show'].show()
        return False

    def row_error(self, path, message):
        item = self.items.get(path)
        if item:
            item['status'] = 'error'
            item['spinner'].stop(); item['spinner'].hide()
            item['state'].set_text('Failed')
            item['state'].get_style_context().add_class('status-error')
            item['error'].set_text(message.strip()[:600] or 'The conversion failed.')
            item['error'].show()
        return False

    def done(self, total):
        cancelled = self.cancel.is_set()
        if self.pulse_id: self.pulse_id = None
        counts = {k: sum(1 for i in self.items.values() if i['status'] == k) for k in ('done', 'error')}
        for item in self.items.values():
            if item['status'] in {'pending', 'working'}:
                item['status'] = 'skipped'
                item['spinner'].stop(); item['spinner'].hide()
                item['state'].set_text('Cancelled' if cancelled else 'Skipped')
        self.set_busy_ui(False)
        self.progress.set_fraction(0 if cancelled else 1)
        saved = plural(len(self.results), 'file')
        if cancelled: self.set_status(f'Cancelled · {saved} saved before stopping', 'status-error')
        elif counts['error']: self.set_status(f'Finished with {plural(counts["error"], "error")} · {saved} saved', 'status-error')
        else: self.set_status(f'Done · {saved} saved next to the originals', 'status-ok')
        if not self.window.is_active() and not cancelled:
            note = Gio.Notification.new('Converto')
            note.set_body(f'{saved} saved' + (f' · {plural(counts["error"], "error")}' if counts['error'] else ''))
            self.send_notification('done', note)
        if self.pending_paths is not None:
            paths, self.pending_paths = self.pending_paths, None
            self.mode = 'convert'
            self.select(paths, replace=True)
        return False

    # ---------- misc ----------
    def open_output(self, _):
        if self.results: Gio.AppInfo.launch_default_for_uri(self.results[0].parent.as_uri(), None)

    def copy_paths(self):
        if self.paths:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text('\n'.join(str(p) for p in self.paths), -1)
            self.set_status(f'Copied {plural(len(self.paths), "path")} to the clipboard')

    def close(self, *_):
        if self.busy:
            self.set_status('Cancel the current job before closing.', 'status-error')
            return True
        self.pool.shutdown(wait=False)
        self.quit()
        return False
