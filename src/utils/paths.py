"""
Centralized path management for Easper.
"""
import sys
from pathlib import Path

def get_base_path():
    """
    Get the base path for the application.
    """
    return Path(__file__).parent.parent.parent

def get_user_models_path():
    """
    Get the user models folder for ASR models (Whisper, MMS, XLS-R).
    Users place their fine-tuned models in this folder.
    """
    user_models = get_base_path() / "user_models"
    user_models.mkdir(parents=True, exist_ok=True)
    return user_models

def get_cache_dir():
    """
    Get the cache directory for other models (Silero VAD, SpeechBrain).
    """
    return get_base_path() / "cached"

def get_temp_dir():
    """Get a temporary directory for audio processing."""
    temp = get_base_path() / "temp_processing"
    temp.mkdir(parents=True, exist_ok=True)
    return temp

def list_asr_models():
    """
    List all ASR models (Whisper, MMS, XLS-R) from the user_models folder.
    """
    models = []
    user_models_path = get_user_models_path()
    if user_models_path.exists():
        for item in user_models_path.iterdir():
            if item.is_dir():
                models.append(str(item))
    return models


def get_ffmpeg_path():
    """
    Get the path to the ffmpeg executable.
    Checks system PATH, installed application directory, and bundled installer directory.
    """
    import os
    import shutil
    
    # 1. System PATH
    found = shutil.which("ffmpeg")
    if found:
        return found
    
    # 2. Installed layout: {base_path}/ffmpeg/bin/ffmpeg.exe
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    installed_ffmpeg = get_base_path() / "ffmpeg" / "bin" / exe_name
    if installed_ffmpeg.exists():
        return str(installed_ffmpeg)

    # 3. Development / build layout: {base_path}/windows_installer/ffmpeg-7.1.1-full_build/bin/ffmpeg.exe
    dev_ffmpeg = get_base_path() / "windows_installer" / "ffmpeg-7.1.1-full_build" / "bin" / exe_name
    if dev_ffmpeg.exists():
        return str(dev_ffmpeg)

    return "ffmpeg"


def get_ffprobe_path():
    """
    Get the path to the ffprobe executable.
    Checks system PATH, installed application directory, and bundled installer directory.
    """
    import os
    import shutil

    # 1. System PATH
    found = shutil.which("ffprobe")
    if found:
        return found
    
    # 2. Installed layout
    exe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    installed_ffprobe = get_base_path() / "ffmpeg" / "bin" / exe_name
    if installed_ffprobe.exists():
        return str(installed_ffprobe)

    # 3. Development layout
    dev_ffprobe = get_base_path() / "windows_installer" / "ffmpeg-7.1.1-full_build" / "bin" / exe_name
    if dev_ffprobe.exists():
        return str(dev_ffprobe)

    return "ffprobe"

