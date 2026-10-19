#!/usr/bin/env python3
"""Install Converto's top-level Convert action for Nautilus 43+ (per user)."""
import argparse
import os
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))
    extension = data/'nautilus-python/extensions/converto.py'
    if args.uninstall:
        extension.unlink(missing_ok=True)
        print('Removed Convert action. Restart Files to unload it.')
        return
    import gi
    gi.require_version('Nautilus', '4.0')
    from gi.repository import Nautilus  # Verify python3-nautilus before installing.
    launcher = root/'run.sh'
    if not launcher.is_file(): raise SystemExit('run.sh is missing beside this installer')
    text = (root/'integrations/converto-nautilus.py.in').read_text()
    text = text.replace('__CONVERTO_LAUNCHER__', repr(str(launcher)))
    compile(text, str(extension), 'exec')
    extension.parent.mkdir(parents=True, exist_ok=True)
    if extension.exists() and not extension.read_text().startswith('# Installed by Converto'):
        raise SystemExit(f'Refusing to replace an unrelated extension: {extension}')
    staged = extension.with_suffix('.tmp')
    staged.write_text(text)
    staged.replace(extension)
    print(f'Installed: {extension}')
    print('Right-click a local file in Files and choose Convert. Restart Files if it was already running.')

if __name__ == '__main__': main()
