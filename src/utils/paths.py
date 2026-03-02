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
