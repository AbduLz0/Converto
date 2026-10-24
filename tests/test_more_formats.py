import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from PIL import Image
from converto.core import convert

class MoreFormatsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()

    def test_new_images_and_readback(self):
        src = self.root/'picture.png'
        Image.new('RGBA',(80,40),(200,30,50,180)).save(src)
        for fmt in ['gif','ico','tga','ppm']:
            with self.subTest(format=fmt):
                out = convert(src,fmt)[0]
                with Image.open(out) as img:
                    img.load()
                    self.assertEqual(img.format,fmt.upper())
                with Image.open(convert(out,'png')[0]) as img: img.load()

    def test_new_archive_contents(self):
        src = self.root/'note.txt'; src.write_text('archive payload')
        for fmt in ['tar','tar.bz2','tar.xz']:
            with self.subTest(format=fmt):
                with tarfile.open(convert(src,fmt)[0]) as archive:
                    self.assertEqual(archive.extractfile('note.txt').read(),b'archive payload')

    @unittest.skipUnless(shutil.which('pdftoppm'), 'Poppler not installed')
    def test_new_pdf_images(self):
        src = self.root/'pages.pdf'
        Image.new('RGB',(32,32),'blue').save(src,save_all=True,append_images=[Image.new('RGB',(32,32),'red')])
        for fmt in ['webp','tiff','bmp']:
            with self.subTest(format=fmt):
                outputs = convert(src,fmt)
                self.assertEqual(len(outputs),2)
                for out in outputs:
                    with Image.open(out) as img:
                        img.load()
                        self.assertEqual(img.format,fmt.upper())

    def probe(self,path,kind):
        result = subprocess.run(['ffprobe','-v','error','-show_streams','-of','json',str(path)],capture_output=True,check=True)
        self.assertIn(kind, [s['codec_type'] for s in json.loads(result.stdout)['streams']])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg/ffprobe not installed')
    def test_new_audio(self):
        src = self.root/'tone.wav'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=0.3',str(src)],check=True)
        for fmt in ['aac','aiff','wma','ac3']:
            with self.subTest(format=fmt): self.probe(convert(src,fmt)[0],'audio')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg/ffprobe not installed')
    def test_new_video_with_audio(self):
        src = self.root/'clip.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=s=64x48:d=0.4',
                        '-f','lavfi','-i','sine=duration=0.4','-c:v','libx264','-c:a','aac','-shortest',str(src)],check=True)
        for fmt in ['mov','avi','wmv','mpeg','ts']:
            with self.subTest(format=fmt):
                out = convert(src,fmt)[0]
                self.probe(out,'video'); self.probe(out,'audio')

    @unittest.skipUnless(shutil.which('libreoffice'), 'LibreOffice not installed')
    def test_new_office_exports(self):
        src = self.root/'note.txt'; src.write_text('Converto document export')
        for fmt in ['doc','rtf','epub']:
            with self.subTest(format=fmt):
                output = convert(src,fmt)[0]
                data = output.read_bytes()
                if fmt == 'rtf': self.assertTrue(data.startswith(b'{\\rtf'))
                if fmt == 'doc': self.assertTrue(data.startswith(bytes.fromhex('d0cf11e0')))
                if fmt == 'epub':
                    with zipfile.ZipFile(output) as z: self.assertEqual(z.read('mimetype'),b'application/epub+zip')
        csv = self.root/'sheet.csv'; csv.write_text('name,amount\none,42\n')
        self.assertTrue(convert(csv,'xls')[0].read_bytes().startswith(bytes.fromhex('d0cf11e0')))

    @unittest.skipUnless(shutil.which('libreoffice'), 'LibreOffice not installed')
    def test_presentation_export(self):
        source = self.root/'slides.odp'
        with zipfile.ZipFile(source,'w') as z:
            z.writestr('mimetype','application/vnd.oasis.opendocument.presentation')
            z.writestr('content.xml','''<?xml version="1.0"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" office:version="1.2"><office:body><office:presentation><draw:page draw:name="Slide 1"/></office:presentation></office:body></office:document-content>''')
            z.writestr('META-INF/manifest.xml','''<?xml version="1.0"?><manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2"><manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.presentation"/><manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/></manifest:manifest>''')
        self.assertTrue(convert(source,'ppt')[0].read_bytes().startswith(bytes.fromhex('d0cf11e0')))

if __name__ == '__main__': unittest.main()
