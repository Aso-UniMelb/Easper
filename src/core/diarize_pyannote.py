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
        output_diarization = pipeline({"waveform": waveform, "sample_rate": sr}, num_speakers=num_speakers, hook=hook)
    
    utterances = []
    for turn, _, speaker in output_diarization.itertracks(yield_label=True):
        speaker = speaker.replace("SPEAKER_0", "")
        utterances.append((turn.start, turn.end, int(speaker)))
    print("Speaker diarization completed.")
    return utterances
