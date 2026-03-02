"""
Silero VAD + SpeechBrain speaker diarization.
https://github.com/cvqluu/simple_diarizer

https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb
Speaker Verification with ECAPA-TDNN embeddings on Voxceleb

"""

from src.utils.paths import get_cache_dir


def diarize_speechbrain(audio_path, num_speakers=1):
    """
    Diarize audio using Silero VAD and SpeechBrain speaker embeddings.
    
    Args:
        audio_path: Path to the audio file
        num_speakers: Number of speakers
    
    Returns:
        list of (start_time, end_time, speaker_id) tuples
    """
    print("Loading Voice Activity Detection model...")
    import torch
    import torchaudio
    import numpy as np
    from tqdm.autonotebook import tqdm
    from sklearn.metrics import pairwise_distances
    from speechbrain.inference.speaker import EncoderClassifier
    from sklearn.cluster import AgglomerativeClustering
    
    cache_dir = get_cache_dir()
    
    # Load Silero VAD from cached folder
    vad_path = cache_dir / "silero_vad"
    if vad_path.exists():
        vad_model, utils = torch.hub.load(str(vad_path), 'silero_vad', source='local')
    else:
        vad_model, utils = torch.hub.load('snakers4/silero-vad', 'silero_vad')
    
    get_ts, _, read_audio, _, _ = utils

    
    print("Running VAD...")
    signal, fs = torchaudio.load(audio_path)
    speech_ts = get_ts(signal, vad_model)
    
    init_segments = []
    if num_speakers == 1:
        for seg in speech_ts:
            init_segments.append((seg['start']/fs, seg['end']/fs, 0))
    
    elif num_speakers > 1:
        print("Loading speaker diarization model...")
        # Load speaker model from cached folder
        embed_path = cache_dir / "spkrec-ecapa-voxceleb"
        if embed_path.exists():
            embed_model = EncoderClassifier.from_hparams(source=str(embed_path), savedir=str(embed_path))
        else:
            embed_model = EncoderClassifier.from_hparams("speechbrain/spkrec-ecapa-voxceleb")
        # --- Split segments into small windows before embeddings ---
        # with some changes, the code is from https://github.com/cvqluu/simple_diarizer/blob/main/simple_diarizer/diarizer.py

        print("Extracting speaker embeddings...")
        all_embeds = []
        all_segments = []
        window = 1.0
        period = 0.5
        for utt in tqdm(speech_ts, desc="Utterances", position=0):
            start = utt["start"]
            end = utt["end"]

            utt_signal = signal[:, start:end]

            # windowed_embeds
            len_window = int(window * fs)
            len_period = int(period * fs)
            len_signal = utt_signal.shape[1]
            # Get the windowed segments
            utt_segments = []
            utt_start = 0
            while utt_start + len_window < len_signal:
                utt_segments.append([utt_start, utt_start + len_window])
                utt_start += len_period
            utt_segments.append([utt_start, len_signal - 1])
            utt_embeds = []
            with torch.no_grad():
                for i, j in utt_segments:
                    signal_seg = utt_signal[:, i:j]
                    seg_embed = embed_model.encode_batch(signal_seg)
                    utt_embeds.append(seg_embed.squeeze(0).squeeze(0).cpu().numpy())
            utt_embeds = np.array(utt_embeds) 
            utt_segments = np.array(utt_segments)
            
            all_embeds.append(utt_embeds)
            all_segments.append(utt_segments + start)
        
        embeds, segments = np.concatenate(all_embeds, axis=0), np.concatenate(all_segments, axis=0)
        
        print("Clustering...")
        S = pairwise_distances(embeds, metric="cosine")
        cluster_labels = AgglomerativeClustering(n_clusters=num_speakers, linkage="average").fit_predict(S)

        for i in range(len(cluster_labels)):
            init_segments.append((segments[i][0] / fs, segments[i][1] / fs, int(cluster_labels[i])))
    print("Segmentation Finished!")
    return init_segments