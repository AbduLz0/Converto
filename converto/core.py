"""Conversion engine. No shell evaluation, uploads, or source modifications."""
from pathlib import Path
import csv
import os
import re
import shutil
import subprocess
import tempfile
import threading
import zipfile
import tarfile
from PIL import Image, ImageOps

IMAGE = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'tif', 'tiff', 'gif', 'ico', 'tga', 'ppm', 'pgm', 'psd'}
AUDIO = {'mp3', 'm4a', 'wav', 'flac', 'ogg', 'opus', 'aiff', 'wma', 'aac', 'ac3', 'aif'}
VIDEO = {'mp4', 'mov', 'mkv', 'webm', 'avi', 'wmv', 'mpeg', 'mpg', 'ts', 'm4v'}
DOC = {'doc', 'docx', 'odt', 'rtf', 'txt', 'html'}
SHEET = {'xls', 'xlsx', 'ods', 'csv', 'tsv'}
SLIDE = {'ppt', 'pptx', 'odp'}

class ConversionError(Exception):
    pass

class Cancelled(ConversionError):
    pass

def category(path):
    p = Path(path)
    if p.is_dir(): return 'folder'
    ext = p.suffix.lower()[1:]
    for name, group in [('image', IMAGE), ('audio', AUDIO), ('video', VIDEO),
                        ('document', DOC), ('spreadsheet', SHEET), ('slides', SLIDE)]:
        if ext in group: return name
    if ext == 'pdf': return 'pdf'
    if ext in {'srt', 'vtt'}: return 'subtitle'
    return 'file'

def targets(path):
    kind = category(path)
    options = []
    if kind == 'image': options = ['png', 'jpg', 'webp', 'tiff', 'bmp', 'pdf', 'gif', 'ico', 'tga', 'ppm']
    if kind in {'audio', 'video'} and shutil.which('ffmpeg'):
        options = ['mp3', 'wav', 'flac', 'ogg', 'opus', 'm4a', 'aac', 'aiff', 'wma', 'ac3']
        if kind == 'video': options = ['mp4', 'webm', 'mkv', 'gif', 'mov', 'avi', 'wmv', 'mpeg', 'ts'] + options
    if kind in {'document', 'spreadsheet', 'slides'} and shutil.which('libreoffice'):
        options = {'document': ['pdf', 'docx', 'odt', 'txt', 'html', 'rtf', 'doc', 'epub'],
                   'spreadsheet': ['pdf', 'xlsx', 'ods', 'csv', 'xls'],
                   'slides': ['pdf', 'pptx', 'odp', 'ppt']}[kind]
    if Path(path).suffix.lower() in {'.csv', '.tsv'}: options += ['csv', 'tsv']
    if kind == 'pdf':
        if shutil.which('pdftoppm'): options += ['png', 'jpg', 'webp', 'tiff', 'bmp']
        if shutil.which('pdftotext'): options += ['txt']
    if kind == 'subtitle': options = ['srt', 'vtt', 'txt']
    options += ['zip', 'tar.gz', 'tar', 'tar.bz2', 'tar.xz']
    return list(dict.fromkeys(x for x in options if x != Path(path).suffix.lower()[1:]))

def common_targets(paths):
    if not paths: return []
    return [x for x in targets(paths[0]) if all(x in targets(p) for p in paths[1:])]

def tools_for(paths):
    if not paths: return []
    kinds = {category(p) for p in paths}
    if kinds == {'image'}: return ['resize', 'strip', 'rotate']
    if kinds == {'audio'} and shutil.which('ffmpeg'): return ['normalize']
    return []

def run(args, cancel):
    if cancel.is_set(): raise Cancelled('Cancelled')
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen([str(a) for a in args], stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        while proc.poll() is None:
            if cancel.wait(.1):
                import signal
                try: os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                try: proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try: os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    proc.wait()
                raise Cancelled('Cancelled; original unchanged')
        if proc.returncode:
            log.seek(0, 2)
            log.seek(max(0, log.tell() - 2000))
            raise ConversionError(log.read().decode(errors='replace').strip())

def publish(staged, directory, name):
    """Hard-link completed outputs atomically without replacing existing names."""
    base = Path(name)
    for i in range(10000):
        candidate = directory / (name if i == 0 else f'{base.stem} ({i}){base.suffix}')
        try:
            os.link(staged, candidate)
            return candidate
        except FileExistsError: continue
    raise ConversionError('Too many files with the same output name')

def subtitle(text, target):
    text = text.lstrip('\ufeff').replace('\r\n', '\n').strip()
    blocks = re.split(r'\n\s*\n', text)
    cues = []
    stamp = re.compile(r'(?:(\d{2,}):)?(\d{2}):(\d{2})[,.](\d{3})')
    def timestamp(match):
        return f'{match[1] or "00"}:{match[2]}:{match[3]}{"," if target == "srt" else "."}{match[4]}'
    for block in blocks:
        lines = block.splitlines()
        if not lines or lines[0].startswith(('WEBVTT', 'NOTE', 'STYLE', 'REGION')): continue
        pos = next((i for i, s in enumerate(lines) if '-->' in s), None)
        if pos is None: continue
        timing = stamp.sub(timestamp, lines[pos])
        if target == 'srt':
            timing = ' --> '.join(part.strip().split()[0] for part in timing.split('-->'))
        body = '\n'.join(lines[pos + 1:])
        if target == 'txt': cues.append(re.sub(r'<[^>]+>', '', body))
        else: cues.append((f'{len(cues)+1}\n' if target == 'srt' else '') + timing + '\n' + body)
    if not cues: raise ConversionError('No subtitle cues found')
    return ('WEBVTT\n\n' if target == 'vtt' else '') + '\n\n'.join(cues) + '\n'

def convert(source, target, cancel=None, operation='convert'):
    cancel = cancel or threading.Event()
    source = Path(source).expanduser().absolute()
    if not source.exists(): raise ConversionError(f'File not found: {source}')
    if source.is_symlink(): raise ConversionError('Choose the original file rather than a symbolic link')
    if cancel.is_set(): raise Cancelled('Cancelled')
    kind = category(source)
    if operation == 'convert' and target not in targets(source):
        raise ConversionError(f'{target.upper()} is not available for {source.name}')
    if operation != 'convert' and operation not in tools_for([source]):
        raise ConversionError('This tool is not available for this file')
    # Stage beside the original so atomic publishing uses the same filesystem.
    with tempfile.TemporaryDirectory(prefix='.converto-', dir=source.parent) as temp:
        work = Path(temp)
        stem = source.stem + ('-' + operation if operation != 'convert' else '')
        if operation in {'resize', 'strip', 'rotate'}:
            target = 'jpg' if source.suffix.lower() in {'.jpg', '.jpeg'} else 'png'
        elif operation == 'normalize': target = 'wav'
        output = work / f'{stem}.{target}'
        outputs = [output]
        if target in {'zip', 'tar.gz', 'tar', 'tar.bz2', 'tar.xz'}:
            # Do not recurse through symlinks or include our staging directory.
            files = [source] if source.is_file() else sorted(source.rglob('*'))
            files = [p for p in files if not p.is_symlink() and not any(x.startswith('.converto-') for x in p.parts)]
            if target == 'zip':
                with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                    if source.is_dir(): archive.write(source, source.name)
                    for p in files:
                        if cancel.is_set(): raise Cancelled('Cancelled')
                        archive.write(p, p.relative_to(source.parent))
            else:
                with tarfile.open(output, {'tar':'w', 'tar.gz':'w:gz', 'tar.bz2':'w:bz2', 'tar.xz':'w:xz'}[target]) as archive:
                    if source.is_dir(): archive.add(source, arcname=source.name, recursive=False)
                    for p in files:
                        if cancel.is_set(): raise Cancelled('Cancelled')
                        archive.add(p, arcname=str(p.relative_to(source.parent)), recursive=False)
        elif kind == 'image':
            with Image.open(source) as original:
                if getattr(original, 'n_frames', 1) > 1:
                    raise ConversionError('Animated/multipage images need an explicit frame choice; not supported yet')
                img = ImageOps.exif_transpose(original)
                if operation == 'resize': img.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
                if operation == 'rotate': img = img.transpose(Image.Transpose.ROTATE_270)
                if img.mode == 'CMYK' and target in {'png', 'bmp', 'gif', 'tga'}:
                    img = img.convert('RGB')
                    # A CMYK profile must not be attached to RGB pixel data.
                    img.info.pop('icc_profile', None)
                if target in {'jpg', 'pdf', 'ppm'}:
                    if 'A' in img.getbands() or 'transparency' in img.info:
                        rgba = img.convert('RGBA')
                        background = Image.new('RGB', img.size, 'white')
                        background.paste(rgba, mask=rgba.getchannel('A'))
                        img = background
                    else: img = img.convert('RGB')
                # All image exports omit EXIF; strip also clears embedded profile/text.
                img.info.pop('exif', None)
                if operation == 'strip':
                    # Palette/color-key transparency describes pixels, not metadata.
                    # Preserve it as an alpha channel before clearing image info.
                    if 'transparency' in img.info: img = img.convert('RGBA')
                    img.info.clear()
                if target == 'ico':
                    img = ImageOps.contain(img.convert('RGBA'), (256, 256))
                    canvas = Image.new('RGBA', (256, 256))
                    canvas.paste(img, ((256-img.width)//2, (256-img.height)//2))
                    img = canvas
                img.save(output, format={'jpg':'JPEG', 'tiff':'TIFF'}.get(target, target.upper()), quality=90)
        elif kind in {'audio', 'video'}:
            args = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-i', source]
            if operation == 'normalize': args += ['-vn', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11']
            elif target in AUDIO:
                args += ['-vn']
                args += {'mp3':['-c:a','libmp3lame','-q:a','2'], 'm4a':['-c:a','aac','-b:a','192k'],
                         'ogg':['-c:a','libvorbis','-q:a','5'], 'opus':['-c:a','libopus','-b:a','128k'],
                         'aac':['-c:a','aac','-b:a','192k'], 'aiff':['-c:a','pcm_s16be'],
                         'wma':['-c:a','wmav2','-b:a','192k'], 'ac3':['-c:a','ac3','-b:a','192k']}.get(target, [])
            elif target in {'mp4', 'mkv', 'mov', 'ts'}:
                args += ['-c:v','libx264','-crf','23','-pix_fmt','yuv420p', '-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-c:a','aac']
                if target == 'mp4': args += ['-movflags', '+faststart']
            elif target in {'avi', 'wmv', 'mpeg'}:
                args += ['-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2', '-pix_fmt','yuv420p']
                args += {'avi':['-c:v','mpeg4','-q:v','4','-c:a','libmp3lame'],
                         'wmv':['-c:v','wmv2','-b:v','2M','-c:a','wmav2'],
                         'mpeg':['-c:v','mpeg2video','-q:v','4','-r','25','-c:a','mp2','-ar','48000']}[target]
            elif target == 'webm': args += ['-c:v','libvpx-vp9','-crf','32','-b:v','0','-c:a','libopus']
            elif target == 'gif': args += ['-vf', 'fps=12,scale=640:-1:flags=lanczos', '-an']
            run(args + [output], cancel)
        elif source.suffix.lower() in {'.csv', '.tsv'} and target in {'csv', 'tsv'}:
            with source.open(newline='', encoding='utf-8-sig') as src, output.open('w', newline='', encoding='utf-8') as dst:
                reader = csv.reader(src, delimiter='\t' if source.suffix.lower() == '.tsv' else ',')
                writer = csv.writer(dst, delimiter='\t' if target == 'tsv' else ',')
                for row in reader:
                    if cancel.is_set(): raise Cancelled('Cancelled')
                    writer.writerow(row)
        elif kind in {'document', 'spreadsheet', 'slides'}:
            profile = (work / 'office-profile').as_uri()
            export_filter = {'rtf':'rtf:Rich Text Format', 'doc':'doc:MS Word 97',
                             'epub':'epub:EPUB', 'xls':'xls:MS Excel 97',
                             'ppt':'ppt:MS PowerPoint 97'}.get(target, target)
            run(['libreoffice', f'-env:UserInstallation={profile}', '--headless', '--convert-to', export_filter,
                 '--outdir', work, source], cancel)
        elif kind == 'pdf':
            if target == 'txt': run(['pdftotext', '-layout', source, output], cancel)
            else:
                run(['pdftoppm', '-r', '150', '-jpeg' if target == 'jpg' else '-png', source, work / stem], cancel)
                if target in {'webp', 'tiff', 'bmp'}:
                    outputs = []
                    for page in sorted(work.glob('*.png')):
                        destination = page.with_suffix('.' + target)
                        with Image.open(page) as img:
                            img.save(destination, format=target.upper(), quality=90)
                        outputs.append(destination)
                else:
                    outputs = sorted(work.glob(f'*.{target}'))
                if not outputs: raise ConversionError('PDF rendering produced no pages')
        elif kind == 'subtitle':
            output.write_text(subtitle(source.read_text(encoding='utf-8-sig'), target), encoding='utf-8')
        if cancel.is_set(): raise Cancelled('Cancelled; original unchanged')
        for p in outputs:
            if not p.is_file() or p.stat().st_size == 0:
                raise ConversionError('The converter produced no output. The source may be unsupported or damaged.')
        committed = []
        try:
            for p in outputs: committed.append(publish(p, source.parent, p.name))
        except Exception:
            for p in committed: p.unlink(missing_ok=True)
            raise
        return committed
