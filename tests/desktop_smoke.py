"""Opt-in integration check on X11, using only a temporary test source window.

Run: python3 tests/desktop_smoke.py
Moves the pointer to drag a generated PNG into Converto's real Xdnd wheel.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import threading
import time
import subprocess
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, Gdk, GLib
from PIL import Image
from converto.wheel import Wheel
from converto.core import convert

temp = tempfile.TemporaryDirectory()
source = Path(temp.name)/'drag-test.png'
Image.new('RGB',(48,48),'red').save(source)
state = {'ok':False}
def submit(paths, target, mode):
    try:
        assert paths == [source], paths
        assert target == 'jpg', target
        result = convert(paths[0],target)
        with Image.open(result[0]) as img: assert img.format == 'JPEG'
        state['ok'] = True
        print('PASS: X11 Shift trigger → URI handoff → JPG sector drop → actual conversion',flush=True)
    except Exception as exc: print('FAIL:',repr(exc),flush=True)
    GLib.timeout_add(200, Gtk.main_quit)

window = Gtk.Window(title='Converto drag integration test')
window.set_default_size(250,150)
window.move(30,50)
source_widget = Gtk.EventBox()
source_widget.add(Gtk.Label(label='Converto test file'))
window.add(source_widget)
source_widget.drag_source_set(Gdk.ModifierType.BUTTON1_MASK,[Gtk.TargetEntry.new('text/uri-list',0,0)],Gdk.DragAction.COPY)
source_widget.connect('drag-data-get',lambda w,c,data,info,t: data.set_uris([source.as_uri()]))
window.show_all()
wheel = Wheel(submit)

def drive():
    time.sleep(.8)
    x,y = window.get_position()
    # This window belongs to the test; coordinates are relative to its known position.
    def mouse(*args): subprocess.run(['xdotool',*map(str,args)],check=True)
    try:
        mouse('mousemove',x+100,y+80)
        mouse('mousedown',1)
        mouse('mousemove',x+120,y+85)
        time.sleep(.3)
        mouse('mousemove',x+360,y+200)
        mouse('keydown','Shift_L')
        time.sleep(.4)
        mouse('keyup','Shift_L')
        mouse('mousemove',x+362,y+201)
        time.sleep(.4)
        # JPG is the first of seven options for a PNG input; first sector is upper-right.
        wx,wy = wheel.get_position()
        mouse('mousemove',wx+250,wy+80)
        time.sleep(.4)
        mouse('mouseup',1)
    finally:
        mouse('keyup','Shift_L')
        mouse('mouseup',1)

threading.Thread(target=drive,daemon=True).start()
GLib.timeout_add_seconds(8,Gtk.main_quit)
Gtk.main()
wheel.destroy(); window.destroy(); temp.cleanup()
if not state['ok']:
    print('FAIL: no successful drop received',flush=True)
    sys.exit(1)
