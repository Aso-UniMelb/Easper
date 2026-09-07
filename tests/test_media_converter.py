"""
Tests for Media Converter core and UI logic in Easper.
"""
import math
import os
import shutil
import struct
import unittest
import wave
import sys
from pathlib import Path

# Add project root to sys.path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.media_converter import (
    probe_media,
    convert_media_file,
    format_duration,
    format_size,
    is_supported_media_file,
)
from src.utils.paths import get_ffmpeg_path, get_ffprobe_path


class TestMediaConverterCore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path("temp_processing") / "test_media_conv_suite"
        cls.test_dir.mkdir(parents=True, exist_ok=True)

        # Create 1-second 44.1kHz Stereo WAV file
        cls.stereo_wav = cls.test_dir / "stereo_sample.wav"
        with wave.open(str(cls.stereo_wav), "w") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            frames = bytearray()
            for i in range(44100):
                vl = int(32767.0 * 0.4 * math.sin(2.0 * math.pi * 440.0 * i / 44100))
                vr = int(32767.0 * 0.4 * math.sin(2.0 * math.pi * 880.0 * i / 44100))
                frames.extend(struct.pack("<hh", vl, vr))
            wf.writeframes(frames)

        # Create 1-second 22.05kHz Mono WAV file
        cls.mono_wav = cls.test_dir / "mono_sample.wav"
        with wave.open(str(cls.mono_wav), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            frames = bytearray()
            for i in range(22050):
                v = int(32767.0 * 0.4 * math.sin(2.0 * math.pi * 330.0 * i / 22050))
                frames.extend(struct.pack("<h", v))
            wf.writeframes(frames)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(str(cls.test_dir), ignore_errors=True)

    def test_ffmpeg_paths_resolved(self):
        ffmpeg = get_ffmpeg_path()
        ffprobe = get_ffprobe_path()
        self.assertTrue(bool(ffmpeg), "ffmpeg path should not be empty")
        self.assertTrue(bool(ffprobe), "ffprobe path should not be empty")

    def test_extension_detection(self):
        self.assertTrue(is_supported_media_file("audio.mp3"))
        self.assertTrue(is_supported_media_file("video.mp4"))
        self.assertTrue(is_supported_media_file("video.mov"))
        self.assertTrue(is_supported_media_file("audio.WAV"))
        self.assertFalse(is_supported_media_file("document.pdf"))
        self.assertFalse(is_supported_media_file("image.png"))

    def test_probe_stereo_file(self):
        info = probe_media(str(self.stereo_wav))
        self.assertTrue(info["has_audio"])
        self.assertEqual(info["channels"], 2)
        self.assertEqual(info["sample_rate"], 44100)
        self.assertAlmostEqual(info["duration"], 1.0, delta=0.1)

    def test_probe_mono_file(self):
        info = probe_media(str(self.mono_wav))
        self.assertTrue(info["has_audio"])
        self.assertEqual(info["channels"], 1)
        self.assertEqual(info["sample_rate"], 22050)
        self.assertAlmostEqual(info["duration"], 1.0, delta=0.1)

    def test_convert_to_mono_16k(self):
        out_files = convert_media_file(str(self.stereo_wav), split_channels=False)
        self.assertEqual(len(out_files), 1)
        out_info = probe_media(out_files[0])
        self.assertEqual(out_info["channels"], 1)
        self.assertEqual(out_info["sample_rate"], 16000)

    def test_split_stereo_channels(self):
        out_files = convert_media_file(str(self.stereo_wav), split_channels=True)
        self.assertEqual(len(out_files), 2)
        ch1_path, ch2_path = out_files[0], out_files[1]
        self.assertTrue("_ch1" in ch1_path)
        self.assertTrue("_ch2" in ch2_path)

        ch1_info = probe_media(ch1_path)
        ch2_info = probe_media(ch2_path)
        self.assertEqual(ch1_info["channels"], 1)
        self.assertEqual(ch1_info["sample_rate"], 16000)
        self.assertEqual(ch2_info["channels"], 1)
        self.assertEqual(ch2_info["sample_rate"], 16000)

    def test_convert_to_mp3_sharing(self):
        out_files = convert_media_file(str(self.stereo_wav), split_channels=False, output_format="mp3")
        self.assertEqual(len(out_files), 1)
        self.assertTrue(out_files[0].endswith(".mp3"))
        info = probe_media(out_files[0])
        self.assertEqual(info["channels"], 1)
        self.assertEqual(info["sample_rate"], 16000)
        # MP3 file size should be significantly smaller than raw WAV
        wav_size = os.path.getsize(str(self.stereo_wav))
        mp3_size = os.path.getsize(out_files[0])
        self.assertLess(mp3_size, wav_size * 0.5)

    def test_split_stereo_mp3(self):
        out_files = convert_media_file(str(self.stereo_wav), split_channels=True, output_format="mp3")
        self.assertEqual(len(out_files), 2)
        self.assertTrue(out_files[0].endswith("_ch1.mp3"))
        self.assertTrue(out_files[1].endswith("_ch2.mp3"))
        info1 = probe_media(out_files[0])
        info2 = probe_media(out_files[1])
        self.assertEqual(info1["channels"], 1)
        self.assertEqual(info2["channels"], 1)
        self.assertEqual(info1["sample_rate"], 16000)
        self.assertEqual(info2["sample_rate"], 16000)

    def test_formatting_helpers(self):
        self.assertEqual(format_duration(65), "01:05")
        self.assertEqual(format_duration(3665), "01:01:05")
        self.assertEqual(format_duration(0), "--:--")
        self.assertTrue("MB" in format_size(1024 * 1024 * 5))


if __name__ == "__main__":
    unittest.main()
