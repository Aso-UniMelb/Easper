"""
Pyannote speaker diarization.
"""

def diarize_pyannote(audio_path, num_speakers=1):
    """
    Diarize audio using Pyannote speaker diarization pipeline.
    
    Args:
        audio_path: Path to the audio file
        num_speakers: Number of speakers
    
    Returns:
        list of (start_time, end_time, speaker_id) tuples
    """

    print("Loading Pyannote speaker diarization model...")
    import torch

    # Fix PyTorch 2.6+ weights_only default breaking pyannote / pytorch-lightning checkpoint loading
    _real_torch_load = getattr(torch, "_easper_orig_load", None)
    if _real_torch_load is None:
        _real_torch_load = torch.load
        torch._easper_orig_load = _real_torch_load

    def _safe_torch_load(*args, **kwargs):
        kwargs["weights_only"] = False
        try:
            return _real_torch_load(*args, **kwargs)
        except TypeError:
            kwargs.pop("weights_only", None)
            return _real_torch_load(*args, **kwargs)

    torch.load = _safe_torch_load

    if hasattr(torch.serialization, "add_safe_globals"):
        try:
            import torch.torch_version
            torch.serialization.add_safe_globals([torch.torch_version.TorchVersion])
        except Exception:
            pass
        try:
            import pyannote.audio.core.task
            torch.serialization.add_safe_globals([pyannote.audio.core.task.Specifications])
        except Exception:
            pass

    import torchaudio
    from pyannote.audio import Pipeline
    from pyannote.audio.pipelines.utils.hook import ProgressHook
    
    # HuggingFace token (should be moved to config/env in production)
    HF_TOKEN = 'hf_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX'
    
    print("Speaker diarization...")
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=HF_TOKEN)
    
    # Segmentation parameters
    # min_duration_off (in seconds) controls intra-speaker pauses. 
    # Setting it to 2, for example, would mean only pauses of 2 seconds or more by the same speaker would start a new segment.
    # pipeline.segmentation.min_duration_off = 1.0
    
    # Run segmentation/diarization
    waveform, sr = torchaudio.load(audio_path)
    with ProgressHook() as hook:
        output_diarization = pipeline({"waveform": waveform, "sample_rate": sr}, num_speakers=num_speakers+1, hook=hook)
    
    utterances = []
    for turn, _, speaker in output_diarization.itertracks(yield_label=True):
        speaker = speaker.replace("SPEAKER_0", "")
        utterances.append((turn.start, turn.end, f"Speaker_{int(speaker) + 1}"))
    print("Speaker diarization completed.")
    return utterances
