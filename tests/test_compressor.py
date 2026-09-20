import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

from compressor import Cancelled, CompressionError, compress, find_ffmpeg


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg and ffprobe required")
class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "한글 음성 원본.mp3"
        subprocess.run([find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "sine=frequency=440:duration=8", "-ac", "2", "-c:a", "libmp3lame",
                        "-b:a", "192k", str(self.source)], check=True)

    def probe(self, path):
        data = subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
        return json.loads(data)

    def test_real_mp3_is_smaller_48kbps_and_keeps_duration(self):
        before = hashlib.sha256(self.source.read_bytes()).hexdigest()
        result = compress(self.source, self.root / "출력 폴더")
        self.assertLess(result.compressed_bytes, result.original_bytes * 0.4)
        info = self.probe(result.output)
        self.assertEqual(int(info["streams"][0]["bit_rate"]), 48000)
        self.assertEqual(info["streams"][0]["channels"], 1)
        self.assertAlmostEqual(float(info["format"]["duration"]), 8, delta=0.15)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), before)

    def test_never_overwrites_existing_output(self):
        first = compress(self.source, self.root)
        data = first.output.read_bytes()
        second = compress(self.source, self.root)
        self.assertNotEqual(first.output, second.output)
        self.assertEqual(first.output.read_bytes(), data)

    def test_stereo(self):
        result = compress(self.source, self.root, mono=False)
        self.assertEqual(self.probe(result.output)["streams"][0]["channels"], 2)

    def test_larger_result_is_skipped(self):
        small = self.root / "small.mp3"
        subprocess.run([find_ffmpeg(), "-loglevel", "error", "-i", str(self.source), "-b:a", "8k",
                        "-ar", "8000", "-ac", "1", str(small)], check=True)
        output = self.root / "skipped"
        self.assertIsNone(compress(small, output).output)
        self.assertEqual(list(output.iterdir()), [])

    def test_invalid_file_cleans_temporary_output(self):
        bad = self.root / "broken.mp3"
        bad.write_bytes(b"not audio")
        output = self.root / "failed"
        with self.assertRaises(CompressionError):
            compress(bad, output)
        self.assertEqual(list(output.iterdir()), [])

    def test_cancel_does_not_create_output(self):
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(Cancelled):
            compress(self.source, self.root / "cancelled", cancel=cancelled)
        self.assertFalse((self.root / "cancelled").exists())

    def test_missing_file_and_unsupported_bitrate(self):
        with self.assertRaises(CompressionError):
            compress(self.root / "missing.mp3", self.root)
        with self.assertRaises(CompressionError):
            compress(self.source, self.root, bitrate=999)


if __name__ == "__main__":
    unittest.main()
