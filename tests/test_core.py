import csv
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
import zipfile
from PIL import Image, PngImagePlugin
from converto.core import convert, targets, common_targets, Cancelled, ConversionError

class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def image(self, name='sample.png'):
        p = self.root / name
        Image.new('RGBA', (31, 25), (255, 0, 0, 100)).save(p)
        return p
    def test_alpha_original_and_collision(self):
        p = self.image('a;$(touch nope).png')
        before = hashlib.sha256(p.read_bytes()).digest()
        first = convert(p, 'jpg')[0]
        data = first.read_bytes()
        second = convert(p, 'jpg')[0]
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), data)
        self.assertEqual(hashlib.sha256(p.read_bytes()).digest(), before)
        with Image.open(first) as img:
            self.assertEqual(img.size, (31,25))
            self.assertEqual(img.mode, 'RGB')
    def test_cancel_no_output(self):
        p = self.image()
        stop = threading.Event(); stop.set()
        with self.assertRaises(Cancelled): convert(p, 'jpg', stop)
        self.assertEqual(list(self.root.iterdir()), [p])
    def test_bad_input_cleans_staging(self):
        p = self.root/'broken.png'; p.write_text('not an image')
        with self.assertRaises(Exception): convert(p, 'jpg')
        self.assertEqual(list(self.root.iterdir()), [p])
    def test_animation_rejected(self):
        p = self.root/'animated.gif'
        Image.new('RGB',(2,2),'red').save(p,save_all=True,append_images=[Image.new('RGB',(2,2),'blue')])
        with self.assertRaises(ConversionError): convert(p, 'png')
    def test_cmyk_exports_and_orientation(self):
        source = self.root / 'print.jpg'
        exif = Image.Exif()
        exif[274] = 6
        exif[315] = 'Private author'
        Image.new('CMYK', (12, 8), (0, 150, 180, 20)).save(source, exif=exif)
        before = source.read_bytes()
        for target in ('png', 'bmp', 'gif', 'tga'):
            with self.subTest(target=target):
                with Image.open(convert(source, target)[0]) as output:
                    output.load()
                    self.assertEqual(output.size, (8, 12))
                    self.assertNotEqual(output.mode, 'CMYK')
                    self.assertNotIn(315, output.getexif())
        self.assertEqual(source.read_bytes(), before)
    def test_strip_preserves_palette_and_color_key_transparency(self):
        for mode, transparent in [('P', 0), ('RGB', (255, 0, 0))]:
            with self.subTest(mode=mode):
                source = self.root / f'transparent-{mode}.png'
                img = Image.new(mode, (2, 1), 0 if mode == 'P' else 'red')
                if mode == 'P': img.putpalette([255, 0, 0, 0, 0, 255] + [0] * 762)
                img.putpixel((1, 0), 1 if mode == 'P' else (0, 0, 255))
                metadata = PngImagePlugin.PngInfo()
                metadata.add_text('Author', 'Private author')
                img.save(source, transparency=transparent, pnginfo=metadata)
                before = source.read_bytes()
                with Image.open(source) as original:
                    expected = original.convert('RGBA').tobytes()
                with Image.open(convert(source, 'png', operation='strip')[0]) as output:
                    self.assertEqual(output.convert('RGBA').tobytes(), expected)
                    self.assertNotIn('Author', output.info)
                self.assertEqual(source.read_bytes(), before)
    def test_csv_quoted_cells(self):
        p = self.root/'table.csv'; p.write_text('name,value\n"a,b","two\nlines"\n')
        out = convert(p,'tsv')[0]
        with out.open(newline='') as f: rows = list(csv.reader(f,delimiter='\t'))
        self.assertEqual(rows[1], ['a,b','two\nlines'])
    def test_subtitle_roundtrip(self):
        p = self.root/'sub.srt'; p.write_text('1\n00:00:01,200 --> 00:00:02,300\nHello\n')
        vtt = convert(p, 'vtt')[0]
        self.assertIn('00:00:01.200', vtt.read_text())
        srt = convert(vtt, 'srt')[0]
        self.assertIn('00:00:01,200',srt.read_text())
        self.assertEqual(convert(vtt, 'txt')[0].read_text(),'Hello\n')
    def test_folder_zip_skips_symlink(self):
        folder = self.root/'folder'; folder.mkdir()
        (folder/'hello.txt').write_text('hello')
        (folder/'link').symlink_to('/etc/passwd')
        out = convert(folder, 'zip')[0]
        with zipfile.ZipFile(out) as z:
            self.assertEqual(z.read('folder/hello.txt'), b'hello')
            self.assertNotIn('folder/link', z.namelist())
    def test_common_formats(self):
        self.assertEqual(common_targets([self.image(), self.root/'unknown.xyz']), ['zip','tar.gz','tar','tar.bz2','tar.xz'])
    def test_rotate_and_resize(self):
        p = self.image()
        with Image.open(convert(p,'png',operation='rotate')[0]) as img: self.assertEqual(img.size,(25,31))
        p = self.root/'large.png'; Image.new('RGB',(2500,1250)).save(p)
        with Image.open(convert(p,'png',operation='resize')[0]) as img: self.assertEqual(img.size,(1920,960))
    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg not installed')
    def test_real_audio_video(self):
        wav = self.root/'tone.wav'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=0.2',str(wav)],check=True)
        mp3 = convert(wav,'mp3')[0]
        self.assertGreater(mp3.stat().st_size,100)
        video = self.root/'video.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=red:s=32x32:d=0.2',str(video)],check=True)
        self.assertGreater(convert(video,'webm')[0].stat().st_size,100)
    @unittest.skipUnless(shutil.which('pdftoppm'), 'Poppler not installed')
    def test_pdf_all_pages(self):
        p = self.root/'pages.pdf'
        Image.new('RGB',(20,20),'red').save(p,save_all=True,append_images=[Image.new('RGB',(20,20),'blue')])
        out = convert(p,'png')
        self.assertEqual(len(out),2)
        for page in out:
            with Image.open(page) as img: self.assertGreater(img.width,20)
    @unittest.skipUnless(shutil.which('libreoffice'), 'LibreOffice not installed')
    def test_office_to_pdf(self):
        p = self.root/'note.txt'; p.write_text('Converto test document')
        output = convert(p,'pdf')[0]
        self.assertTrue(output.read_bytes().startswith(b'%PDF'))

if __name__ == '__main__': unittest.main()
