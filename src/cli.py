"""
CLI entry point for Easper.
Provides command-line interface for transcription and dataset generation.
"""
import argparse
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def transcribe_command(args):
    """Handle transcribe subcommand."""
    from src.core.transcriber import Wav2ElanTranscriber
    
    if not args.only_segment and not args.model:
        print("Error: --model argument is required (unless --only-segment is used)")
        return 1

    def progress_callback(current, total, message, text=None):
        if total > 0:
            print(f"\r[{current}/{total}] {message}", end="", flush=True)
        else:
            print(f"{message}")
        if text and current == total:
            print()  # newline after progress
    
    print(f"Loading models...")
    transcriber = Wav2ElanTranscriber(
        model_path=args.model if args.model else "dummy",
        secondary_model_path=args.secondary_model or "None",
        num_speakers=args.speakers,
        progress_callback=progress_callback
    )
    
    if transcriber.stopped:
        print("Error: Failed to load models")
        return 1
    
    print(f"\nProcessing: {args.input}")
    output_file = transcriber.transcribe_audio(
        args.input,
        progress_callback=progress_callback,
        min_on=args.min_on,
        min_off=args.min_off,
        only_segment=args.only_segment,
        segments_file=args.segments_from,
        start_time=args.start,
        end_time=args.end
    )
    
    if output_file:
        print(f"\nOutput: {output_file}")
        return 0
    else:
        print("\nTranscription failed or was stopped")
        return 1


def dataset_command(args):
    """Handle dataset subcommand."""
    from src.core.dataset import build_training_dataset, check_elan_files
    
    # Parse tier list from comma-separated string
    selected_tiers = [t.strip() for t in args.tiers.split(",")] if args.tiers else None
    
    # Create tier_vars structure for CLI (simple dict instead of tkinter vars)
    tier_vars = {}
    for elan_file in args.input:
        tier_vars[elan_file] = {}
        try:
            import pympi
            eaf = pympi.Elan.Eaf(elan_file)
            for tier in eaf.get_tier_names():
                # Create a simple object with get() method to mimic StringVar
                class SimpleTierVar:
                    def __init__(self, value):
                        self._value = value
                    def get(self):
                        return self._value
                
                if selected_tiers is None or tier in selected_tiers:
                    tier_vars[elan_file][tier] = SimpleTierVar(tier)
                else:
                    tier_vars[elan_file][tier] = SimpleTierVar("")
        except Exception as e:
            print(f"Error reading {elan_file}: {e}")
            return 1
    
    def progress_callback(current, total):
        print(f"\r[{current}/{total}] Processing segments...", end="", flush=True)
    
    def log_callback(message):
        print(message)
    
    print(f"Building dataset from {len(args.input)} file(s)...")
    zip_path = build_training_dataset(
        args.input,
        tier_vars,
        args.output,
        progress_callback=progress_callback,
        log_callback=log_callback
    )
    
    if zip_path:
        print(f"\nDataset created: {zip_path}")
        return 0
    else:
        print("\nDataset creation failed")
        return 1


def convert_command(args):
    """Handle convert subcommand."""
    from src.core.media_converter import convert_media_file, is_supported_media_file
    from pathlib import Path
    
    input_files = []
    for item in args.input:
        p = Path(item)
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and is_supported_media_file(str(f)):
                    input_files.append(str(f))
        elif p.is_file():
            input_files.append(str(p))
        else:
            print(f"Warning: Path not found: {item}")
    
    if not input_files:
        print("Error: No valid audio or video files found.")
        return 1

    output_dir = args.output if args.output else None
    split_channels = args.split_channels
    output_format = args.format.lower()

    print(f"Converting {len(input_files)} file(s) to 16 kHz mono {output_format.upper()}...")

    success = 0
    errors = 0
    for idx, f in enumerate(input_files, 1):
        print(f"[{idx}/{len(input_files)}] Converting {Path(f).name}...", end="", flush=True)
        try:
            generated = convert_media_file(
                f,
                output_dir=output_dir,
                split_channels=split_channels,
                output_format=output_format
            )
            print(f" -> {', '.join(Path(g).name for g in generated)}")
            success += 1
        except Exception as e:
            print(f" -> Error: {e}")
            errors += 1

    print(f"\nFinished: {success} converted, {errors} failed.")
    return 0 if errors == 0 else 1


def trim_command(args):
    """Handle trim subcommand."""
    from src.core.silence_cutter import trim_edges, strip_all_silence
    from src.core.media_converter import is_supported_media_file
    from pathlib import Path

    input_files = []
    for item in args.input:
        p = Path(item)
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and is_supported_media_file(str(f)):
                    input_files.append(str(f))
        elif p.is_file():
            input_files.append(str(p))
        else:
            print(f"Warning: Path not found: {item}")

    if not input_files:
        print("Error: No valid audio or video files found.")
        return 1

    mode = args.mode
    output_dir = args.output if args.output else None
    noise_db = args.noise_db
    min_silence = args.min_silence
    padding_sec = args.padding
    fmt = args.format.lower()

    print(f"Running silence processing (mode: {mode}) on {len(input_files)} file(s)...")

    success = 0
    errors = 0
    for idx, f in enumerate(input_files, 1):
        print(f"[{idx}/{len(input_files)}] Processing {Path(f).name}...", end="", flush=True)
        try:
            if mode == "edges":
                res = trim_edges(
                    f, output_dir=output_dir, noise_threshold_db=noise_db,
                    min_silence_sec=min_silence, padding_sec=padding_sec, output_format=fmt
                )
            else:  # strip
                res = strip_all_silence(
                    f, output_dir=output_dir, noise_threshold_db=noise_db,
                    min_silence_sec=min_silence, padding_sec=padding_sec, output_format=fmt
                )

            if res.get("status") == "no_speech":
                print(" -> No speech detected above threshold.")
            elif res.get("output_files"):
                outs = res["output_files"]
                if len(outs) <= 2:
                    print(f" -> {', '.join(Path(o).name for o in outs)}")
                else:
                    print(f" -> Generated {len(outs)} chunk(s) in {Path(outs[0]).parent.name}")
                if res.get("csv_file"):
                    print(f"    Timestamp CSV: {Path(res['csv_file']).name}")
                success += 1
            else:
                print(" -> Failed.")
                errors += 1
        except Exception as e:
            print(f" -> Error: {e}")
            errors += 1

    print(f"\nFinished: {success} successful, {errors} failed.")
    return 0 if errors == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        prog="Easper",
        description="Easper - Audio transcription and dataset generation"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Transcribe subcommand
    transcribe_parser = subparsers.add_parser(
        "transcribe",
        help="Transcribe audio file to ELAN format"
    )
    transcribe_parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input audio file (WAV or MP4)"
    )
    transcribe_parser.add_argument(
        "--model", "-m",
        required=False,
        help="Path to ASR model (whisper, mms, or xls). Required unless --only-segment is used."
    )
    transcribe_parser.add_argument(
        "--secondary-model",
        help="Path to secondary ASR model for fallback"
    )
    transcribe_parser.add_argument(
        "--speakers", "-s",
        type=int,
        default=1,
        help="Number of speakers (default: 1)"
    )
    transcribe_parser.add_argument(
        "--min-on",
        type=float,
        default=0.5,
        help="Minimum segment duration in seconds (default: 0.5)"
    )
    transcribe_parser.add_argument(
        "--min-off",
        type=float,
        default=0.5,
        help="Minimum duration between segments in seconds (default: 0.5)"
    )
    transcribe_parser.add_argument(
        "--only-segment",
        action="store_true",
        help="Only perform segmentation (diarization), skip transcription"
    )
    transcribe_parser.add_argument(
        "--segments-from",
        help="Path to ELAN file to read segments from (skips diarization)"
    )
    transcribe_parser.add_argument(
        "--start",
        type=float,
        default=0,
        help="Start time in seconds (default: 0)"
    )
    transcribe_parser.add_argument(
        "--end",
        type=float,
        help="End time in seconds (default: End of file)"
    )

    # Dataset subcommand
    dataset_parser = subparsers.add_parser(
        "dataset",
        help="Build ASR training dataset from ELAN files"
    )
    dataset_parser.add_argument(
        "--input", "-i",
        nargs="+",
        required=True,
        help="Input ELAN (.eaf) file(s)"
    )
    dataset_parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output folder for dataset"
    )
    dataset_parser.add_argument(
        "--tiers", "-t",
        help="Comma-separated list of tier names to include (default: all)"
    )
    
    # Convert subcommand
    convert_parser = subparsers.add_parser(
        "convert",
        help="Batch convert audio/video files to 16 kHz mono WAV"
    )
    convert_parser.add_argument(
        "--input", "-i",
        nargs="+",
        required=True,
        help="Input audio/video file(s) or folder(s)"
    )
    convert_parser.add_argument(
        "--output", "-o",
        help="Output folder (default: same folder as input file)"
    )
    convert_parser.add_argument(
        "--split-channels", "-s",
        action="store_true",
        help="Split 2-channel (stereo) files into separate mono tracks (_ch1 & _ch2)"
    )
    convert_parser.add_argument(
        "--format", "-f",
        choices=["wav", "mp3", "flac"],
        default="wav",
        help="Output audio format: wav (16-bit PCM), mp3 (compact sharing), flac (lossless). Default: wav"
    )

    # Trim subcommand
    trim_parser = subparsers.add_parser(
        "trim",
        help="Silence trimmer and VAD utterance cutter"
    )
    trim_parser.add_argument(
        "--input", "-i",
        nargs="+",
        required=True,
        help="Input audio/video file(s) or folder(s)"
    )
    trim_parser.add_argument(
        "--mode", "-m",
        choices=["edges", "strip"],
        default="edges",
        help="Mode: 'edges' (trim start/end dead air) or 'strip' (condense all pauses). Default: edges"
    )
    trim_parser.add_argument(
        "--output", "-o",
        help="Output directory"
    )
    trim_parser.add_argument(
        "--noise-db",
        type=float,
        default=-40.0,
        help="Silence threshold in dB (default: -40.0)"
    )
    trim_parser.add_argument(
        "--min-silence",
        type=float,
        default=0.8,
        help="Minimum silence duration in seconds to detect (default: 0.8)"
    )
    trim_parser.add_argument(
        "--padding",
        type=float,
        default=0.25,
        help="Speech boundary padding margin in seconds (default: 0.25)"
    )
    trim_parser.add_argument(
        "--format", "-f",
        choices=["wav", "mp3", "flac"],
        default="wav",
        help="Output audio format: wav, mp3, or flac. Default: wav"
    )

    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 0
    
    if args.command == "transcribe":
        return transcribe_command(args)
    elif args.command == "dataset":
        return dataset_command(args)
    elif args.command == "convert":
        return convert_command(args)
    elif args.command == "trim":
        return trim_command(args)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
