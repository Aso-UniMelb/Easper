"""
Unit tests for Silence Trimmer and VAD Cutter in Easper.
"""
import csv
import math
import os
import shutil
import struct
import sys
import unittest
import wave
from pathlib import Path

# Add project root to sys.path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.silence_cutter import (
    detect_silence_intervals,
    get_speech_intervals,
    trim_edges,
    strip_all_silence,
    cut_into_chunks,
)
from src.core.media_converter import probe_media


class TestSilenceCutter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path("temp_processing") / "test_silence_suite"
        cls.test_dir.mkdir(parents=True, exist_ok=True)

        # Create 7-second audio:
        # 0s - 1s: Silence
        # 1s - 3s: Tone 1 (Speech)
        # 3s - 4.5s: Silence
        # 4.5s - 6s: Tone 2 (Speech)
        # 6s - 7s: Silence
        cls.sample_wav = cls.test_dir / "sample_speech.wav"
        sr = 16000
        cls.sample_rate = sr
        with wave.open(str(cls.sample_wav), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            frames = bytearray()
            # 1s silence
            frames.extend(b"\x00\x00" * sr)
            # 2s tone 1 (440 Hz)
            for i in range(sr * 2):
                v = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * 440.0 * i / sr))
                frames.extend(struct.pack("<h", v))
            # 1.5s silence
            frames.extend(b"\x00\x00" * int(sr * 1.5))
            # 1.5s tone 2 (880 Hz)
            for i in range(int(sr * 1.5)):
                v = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * 880.0 * i / sr))
                frames.extend(struct.pack("<h", v))
            # 1s silence
            frames.extend(b"\x00\x00" * sr)
            wf.writeframes(frames)

        # Create pure silence audio
        cls.pure_silence_wav = cls.test_dir / "pure_silence.wav"
        with wave.open(str(cls.pure_silence_wav), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(b"\x00\x00" * (sr * 3))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(str(cls.test_dir), ignore_errors=True)

    def test_silence_detection(self):
        silences = detect_silence_intervals(str(self.sample_wav), noise_threshold_db=-35.0, min_silence_sec=0.8)
        self.assertGreaterEqual(len(silences), 2)
        # Leading silence should be around [0, 1.0]
        self.assertAlmostEqual(silences[0][0], 0.0, delta=0.2)
        self.assertAlmostEqual(silences[0][1], 1.0, delta=0.2)

    def test_speech_intervals_derivation(self):
        speech = get_speech_intervals(
            str(self.sample_wav),
            noise_threshold_db=-35.0,
            min_silence_sec=0.8,
            padding_sec=0.1
        )
        self.assertEqual(len(speech), 2)
        # Segment 1 should be around 1.0s to 3.0s
        self.assertAlmostEqual(speech[0][0], 0.9, delta=0.2)
        self.assertAlmostEqual(speech[0][1], 3.1, delta=0.2)

    def test_trim_edges_wav(self):
        res = trim_edges(
            str(self.sample_wav),
            output_dir=str(self.test_dir),
            noise_threshold_db=-35.0,
            min_silence_sec=0.8,
            padding_sec=0.1,
            output_format="wav"
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(len(res["output_files"]), 1)
        out_p = res["output_files"][0]
        self.assertTrue(os.path.exists(out_p))

        # Check that duration was reduced by cutting edges
        info = probe_media(out_p)
        orig_info = probe_media(str(self.sample_wav))
        self.assertLess(info["duration"], orig_info["duration"])
        self.assertGreater(res["duration_saved"], 1.0)

    def test_trim_edges_mp3(self):
        res = trim_edges(
            str(self.sample_wav),
            output_dir=str(self.test_dir),
            noise_threshold_db=-35.0,
            min_silence_sec=0.8,
            padding_sec=0.1,
            output_format="mp3"
        )
        self.assertEqual(res["status"], "success")
        out_p = res["output_files"][0]
        self.assertTrue(out_p.endswith(".mp3"))
        info = probe_media(out_p)
        self.assertEqual(info["channels"], 1)
        self.assertEqual(info["sample_rate"], 16000)

    def test_strip_all_silence(self):
        res = strip_all_silence(
            str(self.sample_wav),
            output_dir=str(self.test_dir),
            noise_threshold_db=-35.0,
            min_silence_sec=0.8,
            padding_sec=0.1,
            output_format="wav"
        )
        self.assertEqual(res["status"], "success")
        out_p = res["output_files"][0]
        info = probe_media(out_p)
        # 2s tone + 1.5s tone + padding ~ 3.5s to 4.0s
        self.assertLess(info["duration"], 5.0)
        self.assertGreater(info["duration"], 3.0)

    def test_cut_into_chunks_with_csv(self):
        out_dir = self.test_dir / "chunks_test"
        res = cut_into_chunks(
            str(self.sample_wav),
            output_dir=str(out_dir),
            noise_threshold_db=-35.0,
            min_silence_sec=0.8,
            padding_sec=0.1,
            output_format="wav",
            export_csv=True
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["total_chunks"], 2)
        self.assertEqual(len(res["output_files"]), 2)
        self.assertTrue(res["csv_file"] is not None)
        self.assertTrue(os.path.exists(res["csv_file"]))

        # Verify CSV contents
        with open(res["csv_file"], "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            self.assertEqual(len(reader), 2)
            self.assertEqual(reader[0]["segment_id"], "1")
            self.assertEqual(reader[1]["segment_id"], "2")
            self.assertTrue(float(reader[0]["duration_sec"]) > 0)

    def test_pure_silence_handling(self):
        res = trim_edges(
            str(self.pure_silence_wav),
            output_dir=str(self.test_dir),
            noise_threshold_db=-35.0,
            min_silence_sec=0.5
        )
        self.assertEqual(res["status"], "no_speech")
        self.assertEqual(len(res["output_files"]), 0)

    def test_ui_defaults_and_options(self):
        import customtkinter as ctk
        from src.ui.silence_cutter_ui import SilenceTrimmerApp

        root = ctk.CTk()
        root.withdraw()
        try:
            app = SilenceTrimmerApp(root)
            # Verify "Cut into Speech Chunks" is removed
            self.assertEqual(app.mode_btn.cget("values"), ["Trim Edges Only", "Remove All Silences"])
            self.assertNotIn("Cut into Speech Chunks", app.mode_btn.cget("values"))
            self.assertEqual(app.mode_btn.get(), "Trim Edges Only")

            # Verify output format default is selected & highlighted
            self.assertEqual(app.fmt_btn.cget("values"), ["WAV (16 kHz Mono)", "MP3 (Compact Sharing)", "FLAC (Lossless)"])
            self.assertEqual(app.fmt_btn.get(), "WAV (16 kHz Mono)")
            self.assertEqual(app.format_var.get(), "WAV (16 kHz Mono)")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()

