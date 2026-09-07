"""
Media converter engine for Easper.
Handles probing and batch conversion of audio/video files to 16 kHz mono WAV,
with support for splitting 2-channel (stereo) files into separate mono tracks.
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any

from src.utils.paths import get_ffmpeg_path, get_ffprobe_path

# Recognized media extensions
AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma",
    ".opus", ".aiff", ".aif", ".mka", ".alac", ".pcm"
}

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv",
    ".mts", ".m2ts", ".wmv", ".3gp", ".m4v", ".ts"
}

ALL_SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


def is_supported_media_file(file_path: str) -> bool:
    """Check if a file has a supported audio or video extension."""
    return Path(file_path).suffix.lower() in ALL_SUPPORTED_EXTENSIONS


def _get_subprocess_flags():
    """Get flags to suppress console window on Windows."""
    kwargs = {}
    if os.name == "nt":
        # CREATE_NO_WINDOW = 0x08000000
        kwargs["creationflags"] = 0x08000000
    return kwargs


def probe_media(file_path: str) -> Dict[str, Any]:
    """
    Inspect media file using ffprobe to retrieve duration, channel count, and sample rate.
    Returns a dictionary with media info.
    """
    file_path = str(Path(file_path).resolve())
    ffprobe_path = get_ffprobe_path()

    info = {
        "file_path": file_path,
        "filename": Path(file_path).name,
        "has_audio": False,
        "channels": 0,
        "channel_layout": "",
        "sample_rate": 0,
        "duration": 0.0,
        "size_bytes": 0,
        "error": None
    }

    try:
        info["size_bytes"] = os.path.getsize(file_path)
    except Exception:
        pass

    try:
        cmd = [
            ffprobe_path,
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=channels,channel_layout,sample_rate,duration:format=duration",
            "-of", "json",
            file_path
        ]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            **_get_subprocess_flags()
        )

        if proc.returncode == 0 and proc.stdout:
            data = json.loads(proc.stdout)
            streams = data.get("streams", [])
            fmt = data.get("format", {})

            if streams:
                a_stream = streams[0]
                info["has_audio"] = True
                info["channels"] = int(a_stream.get("channels", 0))
                info["channel_layout"] = a_stream.get("channel_layout", "")
                info["sample_rate"] = int(a_stream.get("sample_rate", 0))

                # Duration from stream or format
                dur = a_stream.get("duration") or fmt.get("duration")
                if dur:
                    try:
                        info["duration"] = float(dur)
                    except ValueError:
                        info["duration"] = 0.0
            else:
                info["error"] = "No audio stream found"
        else:
            err_msg = proc.stderr.strip() or "ffprobe failed"
            info["error"] = err_msg

    except FileNotFoundError:
        # Fallback to soundfile / pydub if ffprobe executable is not accessible
        _probe_fallback(file_path, info)
    except Exception as e:
        info["error"] = str(e)
        _probe_fallback(file_path, info)

    return info


def _probe_fallback(file_path: str, info: Dict[str, Any]):
    """Fallback metadata inspection using soundfile or pydub."""
    try:
        import soundfile as sf
        with sf.SoundFile(file_path) as f:
            info["has_audio"] = True
            info["channels"] = f.channels
            info["sample_rate"] = f.samplerate
            info["duration"] = len(f) / float(f.samplerate)
            info["error"] = None
            return
    except Exception:
        pass

    try:
        from pydub.utils import mediainfo
        media = mediainfo(file_path)
        if media:
            info["has_audio"] = True
            info["channels"] = int(media.get("channels", 1))
            info["sample_rate"] = int(media.get("sample_rate", 0))
            info["duration"] = float(media.get("duration", 0.0))
            info["error"] = None
    except Exception as e:
        if not info.get("error"):
            info["error"] = f"Unable to probe file: {e}"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to MM:SS or HH:MM:SS string."""
    if not seconds or seconds <= 0:
        return "--:--"
    total_sec = int(round(seconds))
    hrs = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def format_size(size_bytes: int) -> str:
    """Format file size in bytes to human-readable string."""
    if not size_bytes:
        return "0 B"
    num = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def convert_media_file(
    input_path: str,
    output_dir: Optional[str] = None,
    split_channels: bool = False,
    output_format: str = "wav",
    progress_callback: Optional[Callable[[str], None]] = None
) -> List[str]:
    """
    Convert a single media file to 16 kHz mono audio in WAV, MP3, or FLAC format.
    
    If split_channels is True and the file has 2 channels (stereo),
    it generates two separate mono tracks:
        - <basename>_ch1.<ext> (Channel 1 / Left)
        - <basename>_ch2.<ext> (Channel 2 / Right)
    
    Otherwise, downmixes to a single 16 kHz mono track.
    To protect original archival recordings, if the input already has the same
    extension in the destination directory, the output is named <basename>_16k_mono.<ext>.

    Args:
        input_path: Path to input audio or video file.
        output_dir: Destination folder (defaults to same folder as input file).
        split_channels: If True, splits stereo into separate files.
        output_format: "wav" (16-bit PCM), "mp3" (compact sharing), or "flac" (lossless).
        progress_callback: Optional callback for status messages.

    Returns:
        List of generated output file paths.
    """
    input_p = Path(input_path).resolve()
    if not input_p.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    # Normalize format
    fmt = output_format.lower().strip().lstrip(".")
    if fmt not in {"wav", "mp3", "flac"}:
        fmt = "wav"

    if fmt == "mp3":
        codec_args = ["-c:a", "libmp3lame", "-b:a", "64k"]
    elif fmt == "flac":
        codec_args = ["-c:a", "flac"]
    else:
        codec_args = ["-c:a", "pcm_s16le"]

    # Determine target directory
    if output_dir:
        target_dir = Path(output_dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = input_p.parent

    # Probe file to check channels
    media_info = probe_media(str(input_p))
    channels = media_info.get("channels", 0)

    ffmpeg_path = get_ffmpeg_path()
    stem = input_p.stem
    generated_files = []

    # Case A: Split stereo channels
    if split_channels and channels == 2:
        out_ch1 = target_dir / f"{stem}_ch1.{fmt}"
        out_ch2 = target_dir / f"{stem}_ch2.{fmt}"

        if progress_callback:
            progress_callback(f"Splitting stereo channels into {out_ch1.name} and {out_ch2.name}...")

        cmd = [
            ffmpeg_path,
            "-y",
            "-i", str(input_p),
            "-vn",
            "-filter_complex", "[0:a]channelsplit=channel_layout=stereo[left][right]",
            "-map", "[left]", "-ar", "16000", "-ac", "1", *codec_args, str(out_ch1),
            "-map", "[right]", "-ar", "16000", "-ac", "1", *codec_args, str(out_ch2)
        ]

        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **_get_subprocess_flags()
        )

        if proc.returncode != 0:
            # Fallback if channel_layout was not standard stereo (e.g. 2 channels without layout name)
            cmd_fallback = [
                ffmpeg_path,
                "-y",
                "-i", str(input_p),
                "-vn",
                "-filter_complex", "[0:a]pan=mono|c0=c0[a0];[0:a]pan=mono|c0=c1[a1]",
                "-map", "[a0]", "-ar", "16000", "-ac", "1", *codec_args, str(out_ch1),
                "-map", "[a1]", "-ar", "16000", "-ac", "1", *codec_args, str(out_ch2)
            ]
            proc2 = subprocess.run(
                cmd_fallback,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                **_get_subprocess_flags()
            )
            if proc2.returncode != 0:
                raise RuntimeError(f"FFmpeg channel split failed: {proc2.stderr or proc.stderr}")

        generated_files.extend([str(out_ch1), str(out_ch2)])

    # Case B: Standard mono downmix to 16 kHz
    else:
        # Check if output would overwrite the input file
        same_dir = target_dir.samefile(input_p.parent) if target_dir.exists() and input_p.parent.exists() else False
        is_same_file = same_dir and (input_p.suffix.lower() == f".{fmt}")

        if is_same_file:
            out_filename = f"{stem}_16k_mono.{fmt}"
        else:
            out_filename = f"{stem}.{fmt}"

        out_path = target_dir / out_filename

        if progress_callback:
            progress_callback(f"Converting to 16 kHz mono {fmt.upper()}: {out_filename}...")

        cmd = [
            ffmpeg_path,
            "-y",
            "-i", str(input_p),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            *codec_args,
            str(out_path)
        ]

        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **_get_subprocess_flags()
        )

        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg conversion failed: {proc.stderr}")

        generated_files.append(str(out_path))

    return generated_files

