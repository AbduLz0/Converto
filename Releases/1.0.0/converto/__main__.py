import argparse
import sys
from . import __version__

def main():
    parser = argparse.ArgumentParser(description='Converto — offline file conversion for Linux')
    parser.add_argument('files', nargs='*')
    parser.add_argument('--to', help='Convert without opening the desktop window')
    parser.add_argument('--version', action='version', version=__version__)
    args = parser.parse_args()
    if args.to:
        if not args.files: parser.error('--to requires at least one file')
        from .core import convert
        failed = False
        for source in args.files:
            try:
                for result in convert(source, args.to.lower()): print(result)
            except Exception as exc:
                print(f'{source}: {exc}', file=sys.stderr)
                failed = True
        return int(failed)
    from .app import App
    return App().run([sys.argv[0], '--'] + args.files)

if __name__ == '__main__':
    raise SystemExit(main())
