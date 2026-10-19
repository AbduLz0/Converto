from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio
from .core import convert, common_targets, tools_for, category, Cancelled
from .files import uri_paths

CSS = b'''
window { background: #10151d; color: #eaf0f6; }
headerbar { background: #151c26; border: none; box-shadow: none; }
label { color: #eaf0f6; }
.title { font-size: 30px; font-weight: 800; }
.subtitle { color: #97a6b6; font-size: 14px; }
.eyebrow { color: #72dfba; font-size: 11px; font-weight: bold; letter-spacing: 2px; }
.drop { background: #18232d; border: 2px dashed #3b5b5a; border-radius: 18px; padding: 30px; }
.card { background: #19222e; border-radius: 12px; padding: 16px; }
button { background: #253343; color: #eaf0f6; border: 1px solid #334658; border-radius: 9px; padding: 10px 18px; box-shadow: none; text-shadow: none; }
button:hover { background: #354c5b; }
button:disabled { color: #687787; background: #1b2530; }
button.primary { background: #72dfba; color: #10231e; border-color: #72dfba; font-weight: bold; }
button.format { font-size: 14px; font-weight: bold; padding: 16px; }
button.active { background: #72dfba; color: #10231e; }
progressbar trough { background: #253343; border: none; }
progressbar progress { background: #72dfba; border: none; }
scrolledwindow { border: none; }
'''

def label(text, style=None):
    obj = Gtk.Label(label=text, xalign=0)
    obj.set_line_wrap(True)
    if style: obj.get_style_context().add_class(style)
    return obj

def button(text, callback, style=None):
    obj = Gtk.Button(label=text)
    obj.connect('clicked', callback)
    if style: obj.get_style_context().add_class(style)
    return obj

class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='io.converto.desktop', flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.window = None
        self.paths = []
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.cancel = threading.Event()
        self.busy = False
        self.results = []
        self.choice = None
        self.mode = 'convert'
        self.pending_paths = None

    def do_activate(self):
        if self.window is None: self.build()
        self.window.present()

    def do_open(self, files, n_files, hint):
        self.do_activate()
        paths = [Path(f.get_path()) for f in files if f.get_path()]
        if self.busy:
            self.pending_paths = paths
            self.status.set_text('Files received. They will open when the current batch finishes.')
            return
        self.mode = 'convert'
        self.select(paths)

    def build(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window = Gtk.ApplicationWindow(application=self, title='Converto')
        self.window.set_default_size(820, 760)
        self.window.connect('delete-event', self.close)
        header = Gtk.HeaderBar(title='Converto', show_close_button=True)
        header.set_subtitle('Your files. Your device.')
        self.window.set_titlebar(header)
        scroll = Gtk.ScrolledWindow()
        self.window.add(scroll)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.set_border_width(32)
        scroll.add(box)
        box.pack_start(label('LOCAL BY DESIGN', 'eyebrow'), False, False, 0)
        box.pack_start(label('A new format.\nWithout the detour.', 'title'), False, False, 0)
        box.pack_start(label('Drop your files, choose a format, and keep moving.\nNew copies stay beside the originals.', 'subtitle'), False, False, 0)
        drop = Gtk.EventBox()
        drop.get_style_context().add_class('drop')
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        inner.set_border_width(24)
        drop.add(inner)
        self.selection = label('↓   Drop files or folders here', 'subtitle')
        inner.pack_start(self.selection, False, False, 0)
        row = Gtk.Box(spacing=12)
        row.pack_start(button('Choose files', self.choose, 'primary'), False, False, 0)
        row.pack_start(button('Choose folder', lambda _: self.choose(None, True)), False, False, 0)
        inner.pack_start(row, False, False, 0)
        drop.drag_dest_set(Gtk.DestDefaults.ALL, [Gtk.TargetEntry.new('text/uri-list',0,0)], Gdk.DragAction.COPY)
        drop.connect('drag-data-received', lambda w,c,x,y,data,info,t: self.select(uri_paths(data.get_uris())))
        box.pack_start(drop, False, False, 0)
        tabs = Gtk.Box(spacing=10)
        tabs.pack_start(button('Convert', lambda _: self.set_mode('convert')), False, False, 0)
        tabs.pack_start(button('File tools', lambda _: self.set_mode('tools')), False, False, 0)
        tabs.pack_end(button('Copy paths', self.copy_paths), False, False, 0)
        box.pack_start(tabs, False, False, 0)
        self.formats = Gtk.FlowBox()
        self.formats.set_selection_mode(Gtk.SelectionMode.NONE)
        self.formats.set_min_children_per_line(3)
        self.formats.set_max_children_per_line(5)
        self.formats.set_column_spacing(8)
        self.formats.set_row_spacing(8)
        box.pack_start(self.formats, False, False, 0)
        self.hint = label('Choose files to see compatible formats.', 'subtitle')
        box.pack_start(self.hint, False, False, 0)
        actions = Gtk.Box(spacing=12)
        self.start = button('Convert files →', lambda _: self.submit(self.paths, self.choice, self.mode), 'primary')
        self.start.set_sensitive(False)
        actions.pack_start(self.start, True, True, 0)
        self.stop = button('Cancel', lambda _: self.cancel.set())
        self.stop.set_sensitive(False)
        actions.pack_start(self.stop, False, False, 0)
        box.pack_start(actions, False, False, 0)
        self.progress = Gtk.ProgressBar()
        box.pack_start(self.progress, False, False, 0)
        self.status = label('Ready · Nothing leaves your computer', 'subtitle')
        box.pack_start(self.status, False, False, 0)
        self.reveal = button('Open output folder', self.open_output)
        self.reveal.set_sensitive(False)
        box.pack_start(self.reveal, False, False, 0)
        integration = Gtk.Box(spacing=12)
        integration.get_style_context().add_class('card')
        integration.pack_start(label('Right-click → Convert\nSelect files in Files, right-click, then choose Convert.', 'subtitle'), True, True, 0)
        box.pack_start(integration, False, False, 0)
        box.pack_start(label('Converto opens with your selection. Choose a format to continue.', 'subtitle'), False, False, 0)
        self.window.show_all()

    def choose(self, _, folder=False):
        dialog = Gtk.FileChooserDialog(title='Choose a folder' if folder else 'Choose files', parent=self.window,
            action=Gtk.FileChooserAction.SELECT_FOLDER if folder else Gtk.FileChooserAction.OPEN)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Choose', Gtk.ResponseType.OK)
        dialog.set_select_multiple(True)
        if dialog.run() == Gtk.ResponseType.OK: self.select([Path(p) for p in dialog.get_filenames()])
        dialog.destroy()

    def select(self, paths):
        if self.busy: return
        self.paths = list(dict.fromkeys(paths))
        names = ', '.join(p.name for p in self.paths[:3])
        if len(self.paths)>3: names += f' + {len(self.paths)-3} more'
        self.selection.set_text(f'{len(self.paths)} selected · {names}' if self.paths else '↓   Drop files or folders here')
        self.selection.set_tooltip_text('\n'.join(str(p) for p in self.paths))
        self.set_mode(self.mode)

    def set_mode(self, mode):
        if self.busy: return
        self.mode, self.choice = mode, None
        for child in self.formats.get_children(): self.formats.remove(child)
        options = common_targets(self.paths) if mode == 'convert' else tools_for(self.paths)
        friendly = {'resize':'Fit in 1920 px', 'strip':'Remove metadata', 'rotate':'Rotate 90°', 'normalize':'Normalize audio'}
        for option in options:
            b = button(friendly.get(option, option.upper()), lambda b,o=option: self.pick(o,b), 'format')
            self.formats.add(b)
        self.formats.show_all()
        self.start.set_sensitive(False)
        self.start.set_label('Convert files →' if mode == 'convert' else 'Apply tool →')
        self.hint.set_text('Select an output format. Originals are preserved.' if options else
                           ('No compatible tools for this selection.' if self.paths else 'Choose files to see compatible formats.'))

    def pick(self, option, selected):
        if self.busy: return
        self.choice = option
        for child in self.formats.get_children(): child.get_child().get_style_context().remove_class('active')
        selected.get_style_context().add_class('active')
        self.start.set_sensitive(True)
        if option == 'pdf' and self.paths and category(self.paths[0]) == 'image': self.hint.set_text('Creates one PDF per image, with transparency on white.')
        elif option in {'png','jpg'} and self.paths and category(self.paths[0]) == 'pdf': self.hint.set_text('Exports every PDF page as a separate image at 150 DPI.')
        else: self.hint.set_text('Existing files are never overwritten. Image exports omit EXIF metadata.')

    def submit(self, paths, choice, mode):
        if self.busy:
            self.status.set_text('A job is already running. Drop again after it finishes.')
            self.window.present()
            return
        if not paths or not choice: return
        paths = list(paths)
        self.busy = True
        self.cancel = threading.Event()
        self.results = []
        self.start.set_sensitive(False)
        self.stop.set_sensitive(True)
        self.reveal.set_sensitive(False)
        self.formats.set_sensitive(False)
        self.window.present()
        def work():
            errors = []
            for i, path in enumerate(paths):
                if self.cancel.is_set(): break
                GLib.idle_add(self.update, i/len(paths), f'Processing {i+1}/{len(paths)} · {path.name}')
                try:
                    self.results.extend(convert(path, choice, self.cancel, 'convert' if mode == 'convert' else choice))
                except Cancelled: break
                except Exception as exc: errors.append(f'{path.name}: {exc}')
            GLib.idle_add(self.done, errors)
        self.pool.submit(work)

    def update(self, fraction, text):
        self.progress.set_fraction(fraction)
        self.status.set_text(text)
        return False

    def done(self, errors):
        self.busy = False
        self.formats.set_sensitive(True)
        self.start.set_sensitive(bool(self.choice))
        self.stop.set_sensitive(False)
        self.reveal.set_sensitive(bool(self.results))
        state = 'Cancelled' if self.cancel.is_set() else ('Finished with errors' if errors else 'Done')
        self.progress.set_fraction(0 if self.cancel.is_set() else 1)
        self.status.set_text(f'{state} · {len(self.results)} output file(s) saved' + ('\n' + '\n'.join(errors)[:1800] if errors else ''))
        if self.pending_paths is not None:
            paths, self.pending_paths = self.pending_paths, None
            self.mode = 'convert'
            self.select(paths)
        return False

    def open_output(self, _):
        if self.results: Gio.AppInfo.launch_default_for_uri(self.results[0].parent.as_uri(), None)

    def copy_paths(self, _):
        if self.paths:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text('\n'.join(str(p) for p in self.paths), -1)
            self.status.set_text('File paths copied')

    def close(self, *_):
        if self.busy:
            self.status.set_text('Cancel the current job before closing.')
            return True
        self.pool.shutdown(wait=False)
        self.quit()
        return False
