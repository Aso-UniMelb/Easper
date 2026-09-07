"""
Core silence trimmer and Voice Activity Detection (VAD) cutter module for Easper.
Provides functions to detect silence, trim leading/trailing dead air,
condense internal pauses, and cut audio into speech chunks with CSV timestamps.
"""
import csv
import os
import re
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Callable

from src.utils.paths import get_ffmpeg_path
from src.core.media_converter import probe_media, _get_subprocess_flags


def detect_silence_intervals(
    input_path: str,
    noise_threshold_db: float = -40.0,
    min_silence_sec: float = 0.8
) -> List[Tuple[float, float]]:
    """
    Detect all silence intervals in a media file using FFmpeg's silencedetect filter.

    Args:
        input_path: Path to audio or video file.
        noise_threshold_db: Noise floor in dB below which audio is considered silence.
        min_silence_sec: Minimum duration in seconds of silence to trigger detection.

    Returns:
        List of (silence_start, silence_end) in seconds.
    """
    input_p = Path(input_path).resolve()
    if not input_p.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Probe duration
    info = probe_media(str(input_p))
    total_duration = info.get("duration", 0.0)

    ffmpeg_path = get_ffmpeg_path()
    filter_arg = f"silencedetect=noise={noise_threshold_db}dB:d={min_silence_sec}"

    cmd = [
        ffmpeg_path,
        "-i", str(input_p),
        "-af", filter_arg,
        "-f", "null",
        "-"
    ]

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **_get_subprocess_flags()
    )

    silence_intervals = []
    current_start = None

    # Regex patterns for FFmpeg silencedetect output
    start_pattern = re.compile(r"silence_start:\s*([0-9.]+)")
    end_pattern = re.compile(r"silence_end:\s*([0-9.]+)")

    for line in proc.stderr.splitlines():
        start_match = start_pattern.search(line)
        if start_match:
            current_start = float(start_match.group(1))

        end_match = end_pattern.search(line)
        if end_match:
            end_val = float(end_match.group(1))
            start_val = current_start if current_start is not None else 0.0
            silence_intervals.append((start_val, end_val))
            current_start = None

    # If silence started and continues until end of file
    if current_start is not None and total_duration > current_start:
        silence_intervals.append((current_start, total_duration))

    return silence_intervals


def get_speech_intervals(
    input_path: str,
    noise_threshold_db: float = -40.0,
    min_silence_sec: float = 0.8,
    padding_sec: float = 0.25,
    min_speech_sec: float = 0.3
) -> List[Tuple[float, float]]:
    """
    Derive active speech intervals from silence detection, applying padding margins.

    Args:
        input_path: Path to audio or video file.
        noise_threshold_db: Silence threshold in dB.
        min_silence_sec: Minimum silence duration to detect.
        padding_sec: Padding added before and after speech boundaries.
        min_speech_sec: Minimum duration of a speech segment to keep.

    Returns:
        List of merged, padded (speech_start, speech_end) intervals in seconds.
    """
    info = probe_media(input_path)
    total_duration = info.get("duration", 0.0)
    if total_duration <= 0:
        return []

    silences = detect_silence_intervals(input_path, noise_threshold_db, min_silence_sec)

    # Invert silence intervals into raw speech intervals
    raw_speech = []
    prev_end = 0.0

    for s_start, s_end in silences:
        if s_start > prev_end:
            raw_speech.append((prev_end, s_start))
        prev_end = max(prev_end, s_end)

    if prev_end < total_duration:
        raw_speech.append((prev_end, total_duration))

    # If no silences found, entire file is speech
    if not silences and total_duration > 0:
        raw_speech = [(0.0, total_duration)]

    # Apply padding margins
    padded_speech = []
    for start, end in raw_speech:
        p_start = max(0.0, start - padding_sec)
        p_end = min(total_duration, end + padding_sec)
        padded_speech.append((p_start, p_end))

    # Merge overlapping or touching intervals
    if not padded_speech:
        return []

    merged = [padded_speech[0]]
    for start, end in padded_speech[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    # Filter out too short segments
    final_intervals = [(s, e) for s, e in merged if (e - s) >= min_speech_sec]
    return final_intervals


def _get_codec_args(output_format: str) -> Tuple[str, List[str]]:
    """Helper to get file extension and FFmpeg codec arguments."""
    fmt = output_format.lower().strip().lstrip(".")
    if fmt == "mp3":
        return "mp3", ["-c:a", "libmp3lame", "-b:a", "64k"]
    elif fmt == "flac":
        return "flac", ["-c:a", "flac"]
    else:
        return "wav", ["-c:a", "pcm_s16le"]


def trim_edges(
    input_path: str,
    output_dir: Optional[str] = None,
    noise_threshold_db: float = -40.0,
    min_silence_sec: float = 0.8,
    padding_sec: float = 0.25,
    output_format: str = "wav",
    progress_callback: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    """
    Trim leading and trailing silence from media file, keeping internal speech timing 100% intact.
    """
    input_p = Path(input_path).resolve()
    info = probe_media(str(input_p))
    total_dur = info.get("duration", 0.0)

    if progress_callback:
        progress_callback(f"Detecting silence in {input_p.name}...")

    speech_intervals = get_speech_intervals(
        str(input_p),
        noise_threshold_db=noise_threshold_db,
        min_silence_sec=min_silence_sec,
        padding_sec=padding_sec
    )

    if not speech_intervals:
        return {
            "status": "no_speech",
            "message": "No speech detected above the silence threshold.",
            "output_files": [],
            "duration_saved": 0.0
        }

    start_cut = speech_intervals[0][0]
    end_cut = speech_intervals[-1][1]

    target_dir = Path(output_dir).resolve() if output_dir else input_p.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    ext, codec_args = _get_codec_args(output_format)
    stem = input_p.stem
    out_file = target_dir / f"{stem}_trimmed.{ext}"

    if progress_callback:
        progress_callback(f"Trimming dead air ({start_cut:.2f}s to {end_cut:.2f}s)...")

    ffmpeg_path = get_ffmpeg_path()
    cmd = [
        ffmpeg_path,
        "-y",
        "-ss", f"{start_cut:.3f}",
        "-to", f"{end_cut:.3f}",
        "-i", str(input_p),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        *codec_args,
        str(out_file)
    ]

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **_get_subprocess_flags()
    )

    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg trim failed: {proc.stderr}")

    new_dur = end_cut - start_cut
    saved_dur = max(0.0, total_dur - new_dur)

    return {
        "status": "success",
        "output_files": [str(out_file)],
        "original_duration": total_dur,
        "trimmed_duration": new_dur,
        "duration_saved": saved_dur,
        "start_cut": start_cut,
        "end_cut": end_cut
    }


def strip_all_silence(
    input_path: str,
    output_dir: Optional[str] = None,
    noise_threshold_db: float = -40.0,
    min_silence_sec: float = 0.8,
    padding_sec: float = 0.25,
    output_format: str = "wav",
    progress_callback: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    """
    Remove or condense all silent gaps throughout the file, concatenating speech segments.
    """
    input_p = Path(input_path).resolve()
    info = probe_media(str(input_p))
    total_dur = info.get("duration", 0.0)

    if progress_callback:
        progress_callback(f"Analyzing speech intervals in {input_p.name}...")

    speech_intervals = get_speech_intervals(
        str(input_p),
        noise_threshold_db=noise_threshold_db,
        min_silence_sec=min_silence_sec,
        padding_sec=padding_sec
    )

    if not speech_intervals:
        return {
            "status": "no_speech",
            "message": "No speech detected above the silence threshold.",
            "output_files": [],
            "duration_saved": 0.0
        }

    target_dir = Path(output_dir).resolve() if output_dir else input_p.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    ext, codec_args = _get_codec_args(output_format)
    stem = input_p.stem
    out_file = target_dir / f"{stem}_condensed.{ext}"

    ffmpeg_path = get_ffmpeg_path()

    # Case 1: Only 1 segment -> simple slice
    if len(speech_intervals) == 1:
        s, e = speech_intervals[0]
        cmd = [
            ffmpeg_path, "-y",
            "-ss", f"{s:.3f}", "-to", f"{e:.3f}",
            "-i", str(input_p),
            "-vn", "-ac", "1", "-ar", "16000",
            *codec_args, str(out_file)
        ]
    # Case 2: Multiple segments -> atrim + concat filtergraph
    else:
        filter_parts = []
        concat_inputs = []
        for i, (s, e) in enumerate(speech_intervals):
            filter_parts.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]")
            concat_inputs.append(f"[a{i}]")
        
        n_inputs = len(speech_intervals)
        concat_str = f"{''.join(concat_inputs)}concat=n={n_inputs}:v=0:a=1[out]"
        full_filter = f"{';'.join(filter_parts)};{concat_str}"

        cmd = [
            ffmpeg_path, "-y",
            "-i", str(input_p),
            "-vn",
            "-filter_complex", full_filter,
            "-map", "[out]",
            "-ac", "1", "-ar", "16000",
            *codec_args, str(out_file)
        ]

    if progress_callback:
        progress_callback(f"Concatenating {len(speech_intervals)} speech segments...")

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **_get_subprocess_flags()
    )

    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg silence strip failed: {proc.stderr}")

    new_info = probe_media(str(out_file))
    new_dur = new_info.get("duration", 0.0)
    saved_dur = max(0.0, total_dur - new_dur)

    return {
        "status": "success",
        "output_files": [str(out_file)],
        "original_duration": total_dur,
        "condensed_duration": new_dur,
        "duration_saved": saved_dur,
        "segments_count": len(speech_intervals)
    }


def cut_into_chunks(
    input_path: str,
    output_dir: Optional[str] = None,
    noise_threshold_db: float = -40.0,
    min_silence_sec: float = 0.8,
    padding_sec: float = 0.25,
    output_format: str = "wav",
    export_csv: bool = True,
    progress_callback: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    """
    Cut media file into separate speech segment chunks, with an optional CSV timestamp table.
    """
    input_p = Path(input_path).resolve()
    info = probe_media(str(input_p))
    total_dur = info.get("duration", 0.0)

    if progress_callback:
        progress_callback(f"Detecting utterance boundaries in {input_p.name}...")

    speech_intervals = get_speech_intervals(
        str(input_p),
        noise_threshold_db=noise_threshold_db,
        min_silence_sec=min_silence_sec,
        padding_sec=padding_sec
    )

    if not speech_intervals:
        return {
            "status": "no_speech",
            "message": "No speech detected above the silence threshold.",
            "output_files": [],
            "csv_file": None
        }

    target_dir = Path(output_dir).resolve() if output_dir else (input_p.parent / f"{input_p.stem}_chunks")
    target_dir.mkdir(parents=True, exist_ok=True)

    ext, codec_args = _get_codec_args(output_format)
    stem = input_p.stem
    ffmpeg_path = get_ffmpeg_path()

    generated_files = []
    csv_rows = []

    total_chunks = len(speech_intervals)
    for idx, (s, e) in enumerate(speech_intervals, 1):
        chunk_name = f"{stem}_seg{idx:03d}.{ext}"
        chunk_path = target_dir / chunk_name

        if progress_callback:
            progress_callback(f"Exporting chunk ({idx}/{total_chunks}): {chunk_name} ({s:.2f}s - {e:.2f}s)...")

        cmd = [
            ffmpeg_path, "-y",
            "-ss", f"{s:.3f}", "-to", f"{e:.3f}",
            "-i", str(input_p),
            "-vn", "-ac", "1", "-ar", "16000",
            *codec_args, str(chunk_path)
        ]

        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **_get_subprocess_flags()
        )

        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg chunk slice failed for segment {idx}: {proc.stderr}")

        generated_files.append(str(chunk_path))
        csv_rows.append({
            "segment_id": idx,
            "start_time_sec": f"{s:.3f}",
            "end_time_sec": f"{e:.3f}",
            "duration_sec": f"{(e - s):.3f}",
            "filename": chunk_name
        })

    csv_file_path = None
    if export_csv and csv_rows:
        csv_file_path = str(target_dir / f"{stem}_segments.csv")
        with open(csv_file_path, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["segment_id", "start_time_sec", "end_time_sec", "duration_sec", "filename"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)

    return {
        "status": "success",
        "output_files": generated_files,
        "csv_file": csv_file_path,
        "total_chunks": len(generated_files),
        "target_dir": str(target_dir)
    }

