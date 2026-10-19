"""X11 pointer-triggered drop wheel. Ordinary drop UI works on Wayland too."""
import ctypes as C
import math
import os
import time
from pathlib import Path
from urllib.parse import urlparse, unquote
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
from .core import common_targets, tools_for

def uri_paths(uris):
    paths = []
    for uri in uris or []:
        parsed = urlparse(uri)
        if parsed.scheme == 'file' and parsed.netloc in {'', 'localhost'}:
            path = Path(unquote(parsed.path))
            if path.exists(): paths.append(path)
    return paths

class Pointer:
    def __init__(self):
        if os.environ.get('XDG_SESSION_TYPE') == 'wayland': raise RuntimeError('X11 required')
        self.lib = C.CDLL('libX11.so.6')
        self.lib.XOpenDisplay.argtypes = [C.c_char_p]
        self.lib.XOpenDisplay.restype = C.c_void_p
        self.lib.XDefaultRootWindow.argtypes = [C.c_void_p]
        self.lib.XDefaultRootWindow.restype = C.c_ulong
        self.lib.XQueryPointer.argtypes = [C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),
            C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_uint)]
        self.display = self.lib.XOpenDisplay(None)
        if not self.display: raise RuntimeError('No X11 display')
        self.root = self.lib.XDefaultRootWindow(self.display)
    def read(self):
        root, child = C.c_ulong(), C.c_ulong()
        x, y, wx, wy, mask = C.c_int(), C.c_int(), C.c_int(), C.c_int(), C.c_uint()
        self.lib.XQueryPointer(self.display, self.root, C.byref(root), C.byref(child), C.byref(x),
                              C.byref(y), C.byref(wx), C.byref(wy), C.byref(mask))
        return x.value, y.value, mask.value

class Wheel(Gtk.Window):
    SIZE = 400
    def __init__(self, submit):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.submit = submit
        self.set_title('Converto wheel')
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_resizable(False)
        self.set_default_size(self.SIZE, self.SIZE)
        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual: self.set_visual(visual)
        self.area = Gtk.DrawingArea()
        self.add(self.area)
        self.area.connect('draw', self.draw)
        self.drag_dest_set(Gtk.DestDefaults(0), [Gtk.TargetEntry.new('text/uri-list', 0, 0)], Gdk.DragAction.COPY)
        self.connect('drag-motion', self.motion)
        self.connect('drag-drop', self.drop)
        self.connect('drag-data-received', self.receive)
        self.paths, self.options = [], []
        self.selected = -1
        self.pending_drop = False
        self.requested = False
        self.mode = 'convert'
        self.enabled = True
        self.was_chord = False
        self.last_held = 0
        try: self.pointer = Pointer()
        except (OSError, RuntimeError): self.pointer = None
        if self.pointer: GLib.timeout_add(50, self.poll)

    def poll(self):
        x, y, mask = self.pointer.read()
        held = bool(mask & 256)
        chord = held and bool(mask & 1)
        if held: self.last_held = time.monotonic()
        if self.enabled and chord and not self.was_chord and not self.get_visible():
            self.paths, self.options, self.selected = [], [], -1
            self.pending_drop = self.requested = False
            self.mode = 'tools' if mask & 8 else 'convert'
            monitor = self.get_display().get_monitor_at_point(x, y).get_workarea()
            self.move(max(monitor.x, min(x-200, monitor.x+monitor.width-400)),
                      max(monitor.y, min(y-200, monitor.y+monitor.height-400)))
            self.show_all()
        if self.get_visible() and not held and time.monotonic()-self.last_held > .6 and not self.pending_drop:
            self.hide()
        self.was_chord = chord
        return True

    def index_at(self, x, y):
        if not self.options or not 75 <= math.hypot(x-200, y-200) <= 192: return -1
        angle = (math.atan2(y-200, x-200) + math.pi/2) % math.tau
        return int(angle / math.tau * len(self.options))

    def motion(self, widget, context, x, y, timestamp):
        self.selected = self.index_at(x, y)
        Gdk.drag_status(context, Gdk.DragAction.COPY, timestamp)
        if not self.requested:
            self.requested = True
            self.drag_get_data(context, Gdk.Atom.intern('text/uri-list', False), timestamp)
        self.area.queue_draw()
        return True

    def receive(self, widget, context, x, y, data, info, timestamp):
        self.paths = uri_paths(data.get_uris())
        self.options = (tools_for(self.paths) if self.mode == 'tools' else common_targets(self.paths))[:10]
        self.selected = self.index_at(x, y)
        if self.pending_drop:
            self.finish(context, timestamp)
        self.area.queue_draw()

    def drop(self, widget, context, x, y, timestamp):
        self.selected = self.index_at(x, y)
        if self.paths: self.finish(context, timestamp)
        else:
            self.pending_drop = True
            self.drag_get_data(context, Gdk.Atom.intern('text/uri-list', False), timestamp)
            GLib.timeout_add(2000, self.drop_timeout)
        return True

    def drop_timeout(self):
        if self.pending_drop:
            self.pending_drop = False
            self.hide()
        return False

    def finish(self, context, timestamp):
        success = 0 <= self.selected < len(self.options)
        Gtk.drag_finish(context, success, False, timestamp)
        self.pending_drop = False
        if success:
            choice = self.options[self.selected]
            self.submit(list(self.paths), choice, self.mode)
        self.hide()

    def draw(self, widget, cr):
        import cairo
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source_rgba(.055, .075, .11, .98)
        cr.arc(200,200,194,0,math.tau)
        cr.fill()
        n = len(self.options)
        for i, option in enumerate(self.options):
            start, end = -math.pi/2 + i*math.tau/n, -math.pi/2 + (i+1)*math.tau/n
            cr.arc(200,200,187,start+.02,end-.02)
            cr.arc_negative(200,200,81,end-.02,start+.02)
            cr.close_path()
            cr.set_source_rgb(*((.39,.87,.71) if i == self.selected else (.12,.15,.2)))
            cr.fill()
            angle = (start+end)/2
            cr.set_source_rgb(*((.04,.1,.09) if i == self.selected else (.86,.9,.94)))
            self.text(cr, option.upper(), 200+134*math.cos(angle), 200+134*math.sin(angle), 13)
        cr.set_source_rgb(.39,.87,.71)
        self.text(cr, 'CONVERTO', 200,185,14)
        cr.set_source_rgb(.66,.71,.77)
        self.text(cr, f'{len(self.paths)} files' if self.paths else 'Move file here',200,207,12)
        self.text(cr, 'Drop on a format' if n else 'Waiting for file…',200,226,10)
        return False

    @staticmethod
    def text(cr, value, x, y, size):
        cr.select_font_face('Sans')
        cr.set_font_size(size)
        ext = cr.text_extents(value)
        cr.move_to(x-ext.width/2-ext.x_bearing,y)
        cr.show_text(value)
