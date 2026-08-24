"""
Model downloader utility for Easper.
Handles downloading pre-trained Whisper models from Hugging Face into user_models/.
"""
import os
import shutil
from pathlib import Path
from src.utils.paths import get_user_models_path, list_asr_models


def get_available_models():
    """
    Get list of available ASR model display names and full paths.
    """
    models = list_asr_models()
    
    # Also check current working directory for backward compatibility
    current_dir = os.getcwd()
    try:
        subdirs = [d for d in os.listdir(current_dir) if os.path.isdir(os.path.join(current_dir, d))]
        for d in subdirs:
            if d.startswith(('whisper', 'xls', 'mms')):
                full_path = os.path.join(current_dir, d)
                if full_path not in models:
                    models.append(full_path)
    except Exception:
        pass

    return models


def download_whisper_small_model(progress_callback=None):
    """
    Download openai/whisper-small from Hugging Face and save into user_models/whisper-small.
    
    Args:
        progress_callback: Optional fn(status_str)
        
    Returns:
        str: Path to downloaded model directory.
    """
    from transformers import WhisperProcessor, WhisperForConditionalGeneration
    
    model_id = "openai/whisper-small"
    save_dir = get_user_models_path() / "whisper-small"
    save_dir.mkdir(parents=True, exist_ok=True)
    
    if progress_callback:
        progress_callback("Downloading Whisper tokenizer & processor...")
        
    processor = WhisperProcessor.from_pretrained(model_id)
    processor.save_pretrained(str(save_dir))
    
    if progress_callback:
        progress_callback("Downloading Whisper-small model weights (~960 MB)...")
        
    model = WhisperForConditionalGeneration.from_pretrained(model_id)
    model.save_pretrained(str(save_dir))
    
    if progress_callback:
        progress_callback("Whisper-small downloaded and ready!")
        
    return str(save_dir)
