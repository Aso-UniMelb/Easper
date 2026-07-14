"""
Transcriber module for Easper.
Contains the Wav2ElanTranscriber class for audio transcription.
"""
import os
import shutil
from pathlib import Path
from collections import Counter
import concurrent.futures
import time
import math

import warnings
warnings.filterwarnings("ignore")

# Heavy imports are done lazily in the class to improve startup time

from src.utils.paths import get_temp_dir
# from src.core.diarize_funasr import funasr_diarize
from src.core.diarize_pyannote import diarize_pyannote
from src.core.diarize_speechbrain import diarize_speechbrain
from src.core.segment_cleanup import segments_cleanup

temp_dir = str(get_temp_dir())


class Wav2ElanTranscriber:
    def __init__(self, model_path, secondary_model_path="None", segmentation_model="pyannote", num_speakers=1, progress_callback=None, language="en", secondary_language="en", word_set=None, output_confidence=True):
        
        global torch, torchaudio, Pipeline, WhisperForConditionalGeneration, WhisperTokenizer, WhisperFeatureExtractor, Resample, librosa, Wav2Vec2ForCTC, Wav2Vec2Processor


        self.progress_callback = progress_callback

        self.total_segments = 0
        self.current_segment = 0

        self.time_records = {}
        self.time_records['start'] = time.time()

        self.num_speakers = num_speakers
        self.segmentation_model = segmentation_model
        self.model_path = model_path
        self.secondary_model_path = secondary_model_path
        # Get basename for model type detection (paths may be full absolute paths)
        self.model_basename = os.path.basename(self.model_path)
        self.secondary_basename = os.path.basename(self.secondary_model_path) if self.secondary_model_path != "None" else ""
        self.LANG = language
        self.LANG2 = secondary_language
        self.word_set = word_set          # set of known words for OOV detection; None = disabled
        self.output_confidence = output_confidence  # whether to write _words and _conf tiers
  

    def convert_to_mono_16k(self, input_path, start_time=0, end_time=None):
        from pydub import AudioSegment
        output_path = f"{temp_dir}/{Path(input_path).name}"
        audio = AudioSegment.from_file(input_path)
        
        start_ms = start_time * 1000
        if end_time is not None:
             end_ms = end_time * 1000
             audio = audio[start_ms:end_ms]
        else:
             audio = audio[start_ms:]

        audio = audio.set_channels(1)
        audio = audio.set_frame_rate(16000)
        audio.export(output_path, format="wav")
        return output_path

    def transcribe_segment(self, segment):
        index, start, end, speaker, audio_segment = segment
        import torch
        with torch.no_grad():
            results = []
            main_text = ""

            if self.model_basename.startswith('whisper'):
                # Convert to 1D array
                segment_np = audio_segment.squeeze().numpy()
                # Handle short segments or errors
                if segment_np.size == 0:
                    seg_text = ""
                    words_data = []
                else:
                    input_features = self.feature_extractor(segment_np, sampling_rate=16000, return_tensors='pt').input_features.to(self.device)
                    if not self.model_basename.endswith('.en'):  # if model is not English only
                        generated = self.model.generate(input_features=input_features, language=self.LANG, task='transcribe', return_dict_in_generate=True, output_scores=True, return_timestamps=True)
                    else:
                        generated = self.model.generate(input_features=input_features, return_dict_in_generate=True, output_scores=True, return_timestamps=True)

                    # generated can be a dict (e.g. on macOS/newer transformers) or a ModelOutput object
                    if isinstance(generated, dict):
                        scores = generated.get("scores")
                        sequences = generated.get("sequences")
                    else:
                        scores = getattr(generated, "scores", None)
                        sequences = getattr(generated, "sequences", None)

                    text = self.tokenizer.batch_decode(sequences, skip_special_tokens=True)[0].strip()
                    seg_text = text  # clean text → main speaker tier (no embedded scores)

                    # On macOS / newer transformers, scores may be None when return_timestamps=True
                    # even if output_scores=True was requested. Fall back gracefully.
                    if scores is None:
                        token_ids = sequences[0].tolist()
                        all_raw = self.tokenizer.convert_ids_to_tokens(token_ids)
                        log_probs = [float('-inf')] * len(token_ids)
                    else:
                        prefix_len = sequences.size(1) - len(scores)

                        # Collect per-token IDs and log-probs
                        token_ids = sequences[0, prefix_len:].tolist()
                        all_raw = self.tokenizer.convert_ids_to_tokens(token_ids)
                        log_probs = []
                        for t, score_t in enumerate(scores):
                            token_id = sequences[0, prefix_len + t]
                            logp = torch.log_softmax(score_t, dim=-1)[0, token_id].item()
                            log_probs.append(logp)

                    # Overall segment confidence (exclude timestamp / special tokens)
                    text_logprobs = [lp for tok, lp in zip(all_raw, log_probs)
                                     if tok and not (tok.startswith('<') and tok.endswith('>'))]
                    avg_logprob = sum(text_logprobs) / len(text_logprobs) if text_logprobs else 0
                    confidence_score = max(0, min(9, int(round(math.exp(avg_logprob) * 9))))

                    # Group tokens into words and compute per-word confidence.
                    # IMPORTANT: decode each word's token IDs *together* — decoding one
                    # token at a time breaks multi-byte Unicode (e.g. Arabic, Kurdish)
                    # because a single character may span several byte-level BPE tokens.
                    # Use convert_ids_to_tokens() only to detect word boundaries (Ġ / ▁),
                    # never to produce the displayed text.
                    words_with_scores = []
                    cur_word_ids = []
                    cur_logprobs = []
                    for tid, tok, logp in zip(token_ids, all_raw, log_probs):
                        if tok is None or (tok.startswith('<') and tok.endswith('>')):
                            continue  # skip special / timestamp tokens
                        is_boundary = tok.startswith('\u0120') or tok.startswith('\u2581')  # Ġ or ▁
                        if is_boundary and cur_word_ids:
                            word_text = self.tokenizer.decode(cur_word_ids, skip_special_tokens=True).strip()
                            if word_text:
                                word_score = max(0, min(9, int(round(math.exp(sum(cur_logprobs) / len(cur_logprobs)) * 9))))
                                words_with_scores.append((word_text, word_score))
                            cur_word_ids, cur_logprobs = [tid], [logp]
                        else:
                            cur_word_ids.append(tid)
                            cur_logprobs.append(logp)
                    if cur_word_ids:
                        word_text = self.tokenizer.decode(cur_word_ids, skip_special_tokens=True).strip()
                        if word_text:
                            word_score = max(0, min(9, int(round(math.exp(sum(cur_logprobs) / len(cur_logprobs)) * 9))))
                            words_with_scores.append((word_text, word_score))

                    # Extract word-level timestamps from Whisper's <|t.tt|> timestamp tokens.
                    # tokenizer.decode(..., output_offsets=True) parses them and returns time
                    # offsets relative to this segment's local start (0 = segment start).
                    words_data = []
                    try:
                        offset_result = self.tokenizer.decode(sequences[0].tolist(), output_offsets=True)
                        ts_chunks = offset_result.get('offsets', [])
                    except Exception:
                        ts_chunks = []

                    if ts_chunks and words_with_scores:
                        seg_dur = end - start
                        word_idx = 0
                        for chunk in ts_chunks:
                            c_text = chunk.get('text', '').strip()
                            ts = chunk.get('timestamp', (None, None))
                            c_local_start = ts[0] if ts[0] is not None else 0.0
                            c_local_end = ts[1] if ts[1] is not None else seg_dur
                            c_local_end = min(c_local_end, seg_dur)
                            cw = [w for w in c_text.split() if w]
                            n = len(cw)
                            if n == 0 or word_idx >= len(words_with_scores):
                                continue
                            # Collect the n words that map to this chunk
                            chunk_words = [words_with_scores[word_idx + i]
                                           for i in range(n)
                                           if word_idx + i < len(words_with_scores)]
                            # Distribute chunk duration proportionally by character length
                            total_chars = sum(len(wt) for wt, _ in chunk_words) or 1
                            chunk_dur = c_local_end - c_local_start
                            t = c_local_start
                            for wt, ws in chunk_words:
                                prop_dur = chunk_dur * (len(wt) / total_chars)
                                words_data.append((wt, ws, start + t, start + t + prop_dur))
                                t += prop_dur
                                word_idx += 1

                    # Fallback: distribute proportionally by character length across the segment
                    if not words_data and words_with_scores:
                        total_chars = sum(len(wt) for wt, _ in words_with_scores) or 1
                        seg_dur = end - start
                        t = 0.0
                        for wt, ws in words_with_scores:
                            prop_dur = seg_dur * (len(wt) / total_chars)
                            words_data.append((wt, ws, start + t, start + t + prop_dur))
                            t += prop_dur

            elif self.model_basename.startswith(('xls', 'mms')):
                inputs = self.processor([audio_segment], sampling_rate=16000, return_tensors="pt", padding=True, return_attention_mask=True)
                logits = self.model(inputs.input_values, attention_mask=inputs.attention_mask).logits
                predicted_ids = torch.argmax(logits, dim=-1)
                text = self.processor.batch_decode(predicted_ids)[0].strip()
                probs = torch.softmax(logits, dim=-1)
                max_probs, _ = torch.max(probs, dim=-1)
                avg_prob = torch.mean(max_probs).item()
                confidence_score = max(0, min(9, int(round(avg_prob * 9))))
                seg_text = f"[{confidence_score}] {text}" if text else ""
                words_data = None  # no word-level tier for xls/mms
            else:
                seg_text = ""
                words_data = None

            if seg_text and any(c.isalnum() for c in seg_text):
                results.append((start, end, speaker, seg_text, words_data))
                main_text = seg_text
            else:
                results.append((start, end, speaker, "", None))

            if self.secondary_basename:
                if self.secondary_basename.startswith('whisper'):
                    segment_np = audio_segment.squeeze().numpy()
                    if segment_np.size == 0:
                        seg_text2 = ""
                        words_data2 = []
                    else:
                        input_features = self.secondary_feature_extractor(segment_np, sampling_rate=16000, return_tensors='pt').input_features.to(self.device)
                        if not self.secondary_basename.endswith('.en'):
                            generated = self.secondary_model.generate(input_features=input_features, language=self.LANG2, task='transcribe', return_dict_in_generate=True, output_scores=True, return_timestamps=True)
                        else:
                            generated = self.secondary_model.generate(input_features=input_features, return_dict_in_generate=True, output_scores=True, return_timestamps=True)

                        if isinstance(generated, dict):
                            scores = generated.get("scores")
                            sequences = generated.get("sequences")
                        else:
                            scores = getattr(generated, "scores", None)
                            sequences = getattr(generated, "sequences", None)

                        text2 = self.secondary_tokenizer.batch_decode(sequences, skip_special_tokens=True)[0].strip()
                        seg_text2 = text2  # clean text → main tier

                        # On macOS / newer transformers, scores may be None when return_timestamps=True
                        # even if output_scores=True was requested. Fall back gracefully.
                        if scores is None:
                            token_ids2 = sequences[0].tolist()
                            all_raw2 = self.secondary_tokenizer.convert_ids_to_tokens(token_ids2)
                            log_probs2 = [float('-inf')] * len(token_ids2)
                        else:
                            prefix_len = sequences.size(1) - len(scores)

                            token_ids2 = sequences[0, prefix_len:].tolist()
                            all_raw2 = self.secondary_tokenizer.convert_ids_to_tokens(token_ids2)
                            log_probs2 = []
                            for t, score_t in enumerate(scores):
                                token_id = sequences[0, prefix_len + t]
                                logp = torch.log_softmax(score_t, dim=-1)[0, token_id].item()
                                log_probs2.append(logp)

                        # Overall segment confidence (exclude timestamp / special tokens)
                        text_logprobs2 = [lp for tok, lp in zip(all_raw2, log_probs2)
                                          if tok and not (tok.startswith('<') and tok.endswith('>'))]
                        avg_logprob2 = sum(text_logprobs2) / len(text_logprobs2) if text_logprobs2 else 0
                        confidence_score2 = max(0, min(9, int(round(math.exp(avg_logprob2) * 9))))

                        # Group tokens into words and compute per-word confidence
                        words_with_scores2 = []
                        cur_word_ids2 = []
                        cur_logprobs2 = []
                        for tid, tok, logp in zip(token_ids2, all_raw2, log_probs2):
                            if tok is None or (tok.startswith('<') and tok.endswith('>')):
                                continue
                            is_boundary = tok.startswith('\u0120') or tok.startswith('\u2581')
                            if is_boundary and cur_word_ids2:
                                word_text2 = self.secondary_tokenizer.decode(cur_word_ids2, skip_special_tokens=True).strip()
                                if word_text2:
                                    word_score2 = max(0, min(9, int(round(math.exp(sum(cur_logprobs2) / len(cur_logprobs2)) * 9))))
                                    words_with_scores2.append((word_text2, word_score2))
                                cur_word_ids2, cur_logprobs2 = [tid], [logp]
                            else:
                                cur_word_ids2.append(tid)
                                cur_logprobs2.append(logp)
                        if cur_word_ids2:
                            word_text2 = self.secondary_tokenizer.decode(cur_word_ids2, skip_special_tokens=True).strip()
                            if word_text2:
                                word_score2 = max(0, min(9, int(round(math.exp(sum(cur_logprobs2) / len(cur_logprobs2)) * 9))))
                                words_with_scores2.append((word_text2, word_score2))

                        # Extract word-level timestamps
                        words_data2 = []
                        try:
                            offset_result2 = self.secondary_tokenizer.decode(sequences[0].tolist(), output_offsets=True)
                            ts_chunks2 = offset_result2.get('offsets', [])
                        except Exception:
                            ts_chunks2 = []

                        if ts_chunks2 and words_with_scores2:
                            seg_dur = end - start
                            word_idx2 = 0
                            for chunk in ts_chunks2:
                                c_text = chunk.get('text', '').strip()
                                ts = chunk.get('timestamp', (None, None))
                                c_local_start = ts[0] if ts[0] is not None else 0.0
                                c_local_end = ts[1] if ts[1] is not None else seg_dur
                                c_local_end = min(c_local_end, seg_dur)
                                cw = [w for w in c_text.split() if w]
                                n = len(cw)
                                if n == 0 or word_idx2 >= len(words_with_scores2):
                                    continue
                                chunk_words2 = [words_with_scores2[word_idx2 + i]
                                                for i in range(n)
                                                if word_idx2 + i < len(words_with_scores2)]
                                total_chars2 = sum(len(wt) for wt, _ in chunk_words2) or 1
                                chunk_dur = c_local_end - c_local_start
                                t = c_local_start
                                for wt, ws in chunk_words2:
                                    prop_dur = chunk_dur * (len(wt) / total_chars2)
                                    words_data2.append((wt, ws, start + t, start + t + prop_dur))
                                    t += prop_dur
                                    word_idx2 += 1

                        if not words_data2 and words_with_scores2:
                            total_chars2 = sum(len(wt) for wt, _ in words_with_scores2) or 1
                            seg_dur = end - start
                            t = 0.0
                            for wt, ws in words_with_scores2:
                                prop_dur = seg_dur * (len(wt) / total_chars2)
                                words_data2.append((wt, ws, start + t, start + t + prop_dur))
                                t += prop_dur

                elif self.secondary_basename.startswith(('xls', 'mms')):
                    inputs = self.secondary_processor([audio_segment], sampling_rate=16000, return_tensors="pt", padding=True, return_attention_mask=True)
                    logits = self.secondary_model(inputs.input_values, attention_mask=inputs.attention_mask).logits
                    predicted_ids = torch.argmax(logits, dim=-1)
                    text2 = self.secondary_processor.batch_decode(predicted_ids)[0].strip()
                    probs = torch.softmax(logits, dim=-1)
                    max_probs, _ = torch.max(probs, dim=-1)
                    avg_prob2 = torch.mean(max_probs).item()
                    confidence_score2 = max(0, min(9, int(round(avg_prob2 * 9))))
                    seg_text2 = f"[{confidence_score2}] {text2}" if text2 else ""
                    words_data2 = None
                else:
                    seg_text2 = ""
                    words_data2 = None

                secondary_speaker = f"{speaker}_CS"
                if seg_text2 and any(c.isalnum() for c in seg_text2):
                    results.append((start, end, secondary_speaker, seg_text2, words_data2))
                else:
                    results.append((start, end, secondary_speaker, "", None))

            # Update progress
            self.current_segment = self.current_segment + 1
            if self.progress_callback:
                self.progress_callback(self.current_segment, self.total_segments, f"Segment {self.current_segment}/{self.total_segments} Transcribed", main_text)
            else:
                print(f"Segment {index+1}: {main_text}")
            
            return results

    def transcribe_audio(self, file_path, min_on=0.5, min_off=0.5, progress_callback=None, only_segment=False, segments_file=None, start_time=0, end_time=None):
        self.progress_callback = progress_callback

        if progress_callback:
            progress_callback(0, 0, "...", "...")
        os.makedirs(temp_dir, exist_ok=True)
        temp_file_path = self.convert_to_mono_16k(file_path, start_time, end_time)
        
        self.time_records['segmenting'] = time.time()
        
        utterances = []
        speakers = []

        if segments_file:
            if progress_callback:
                progress_callback(0, 0, f"Loading segments from {segments_file}...")
            else:
                print(f"Loading segments from {segments_file}...")
            
            import pympi
            eaf = pympi.Elan.Eaf(segments_file)
            for tier in eaf.get_tier_names():
                speakers.append(tier)
                for start_ms, end_ms, value in eaf.get_annotation_data_for_tier(tier):
                    s = start_ms / 1000.0
                    e = end_ms / 1000.0
                    
                    if end_time is not None and s >= end_time:
                        continue
                    if e <= start_time:
                        continue
                        
                    s = max(0, s - start_time)
                    e = e - start_time
                    if end_time is not None:
                         e = min(end_time - start_time, e)
                    
                    utterances.append((s, e, tier))
            # Sort by start time
            utterances.sort(key=lambda x: x[0])
            self.num_speakers = len(speakers)
        else:
            if progress_callback:
                progress_callback(0, 0, f"Segmenting...")
            else:
                print(f"Segmenting...")
            
            if self.segmentation_model == "pyannote":
                init_segments = diarize_pyannote(temp_file_path, num_speakers=self.num_speakers)
            elif self.segmentation_model == "speechbrain":
                init_segments = diarize_speechbrain(temp_file_path, num_speakers=self.num_speakers)

            utterances = segments_cleanup(init_segments, min_segment=min_on, min_silence=min_off)
            speakers = [f"Speaker_{int(i)}" for i in range(self.num_speakers)]

        #=============
        
        transcribed = []

        if only_segment:
            self.output_confidence = False
            # Skip ASR and just prepare empty transcriptions
            for start, end, speaker in utterances:
                 # item is (start, end, speaker)
                 # transcribed expects (start, end, speaker, text)
                 transcribed.append((start + start_time, end + start_time, speaker, "", None))
                 if self.secondary_basename:
                     transcribed.append((start + start_time, end + start_time, f"{speaker}_CS", "", None))
            
            # Mock times to avoid errors in report
            self.time_records['loading_asr'] = time.time()
            self.time_records['transcribing'] = time.time()

        else:
            self.time_records['loading_asr'] = time.time()
            
            if self.progress_callback:
                self.progress_callback(0, 0, f"Loading ASR model(s)...")
            else:
                print(f"Loading ASR model(s)...")
            # Lazy import of heavy libraries
            import torch
            import torchaudio

            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

            if self.model_basename.startswith('whisper') or self.secondary_basename.startswith('whisper'):
                from transformers import WhisperForConditionalGeneration, WhisperTokenizer, WhisperFeatureExtractor
                from torchaudio.transforms import Resample
                
                def load_whisper_extras(model_obj, path, basename, lang):
                    try:
                        t = WhisperTokenizer.from_pretrained(path, language=lang, task='transcribe')
                        f = WhisperFeatureExtractor.from_pretrained(path, task='transcribe')
                        return t, f
                    except Exception:
                        base = getattr(model_obj.config, "_name_or_path", "")
                        if not base or not base.startswith("openai/"):
                            bn = basename.lower()
                            if "large-v3" in bn: base = "openai/whisper-large-v3"
                            elif "large" in bn: base = "openai/whisper-large-v2"
                            elif "medium" in bn: base = "openai/whisper-medium"
                            elif "small" in bn: base = "openai/whisper-small"
                            elif "base" in bn: base = "openai/whisper-base"
                            elif "tiny" in bn: base = "openai/whisper-tiny"
                            else: base = "openai/whisper-small"
                            if bn.endswith(".en") and not base.endswith(".en"):
                                base += ".en"
                        t = WhisperTokenizer.from_pretrained(base, language=lang, task='transcribe')
                        f = WhisperFeatureExtractor.from_pretrained(base, task='transcribe')
                        return t, f

            if self.model_basename.startswith(('xls', 'mms')) or self.secondary_basename.startswith(('xls', 'mms')):
                import librosa
                from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

            # primary model
            if self.model_basename.startswith('whisper'):
                self.model = WhisperForConditionalGeneration.from_pretrained(self.model_path).to(self.device)
                self.tokenizer, self.feature_extractor = load_whisper_extras(self.model, self.model_path, self.model_basename, self.LANG)
            elif self.model_basename.startswith(('xls', 'mms')):
                self.model = Wav2Vec2ForCTC.from_pretrained(self.model_path + "/model/").to(self.device)
                self.processor = Wav2Vec2Processor.from_pretrained(self.model_path + "/processor")
            
            # secondary model
            if self.secondary_basename:
                if self.secondary_basename.startswith('whisper'):
                    self.secondary_model = WhisperForConditionalGeneration.from_pretrained(self.secondary_model_path).to(self.device)
                    self.secondary_tokenizer, self.secondary_feature_extractor = load_whisper_extras(self.secondary_model, self.secondary_model_path, self.secondary_basename, self.LANG2)
                elif self.secondary_basename.startswith(('xls', 'mms')):
                    self.secondary_model = Wav2Vec2ForCTC.from_pretrained(self.secondary_model_path + "/model/").to(self.device)
                    self.secondary_processor = Wav2Vec2Processor.from_pretrained(self.secondary_model_path + "/processor")

            
            self.time_records['transcribing'] = time.time()
            if progress_callback:
                progress_callback(0, 0, f"Transcribing {len(utterances)} segments, from {len(speakers)} speaker(s)...")
            else:
                print(f"Transcribing {len(utterances)} segments, from {len(speakers)} speaker(s)...")
            
            # --- Transcribe Audio ---
            
            if self.model_basename.startswith('whisper'):
                    waveform, sample_rate = torchaudio.load(temp_file_path)
            if self.model_basename.startswith(('xls', 'mms')):
                    waveform, sample_rate = librosa.load(temp_file_path, sr=16000)
            self.model.eval()
            

            # a list of waveform segments
            segments = []
            for i, (start, end, speaker) in enumerate(utterances):
                start_sample = int(start * sample_rate)
                end_sample = int(end * sample_rate)
                if self.model_basename.startswith('whisper'):
                    segments.append((i, start, end, speaker, waveform[:, start_sample:end_sample]))
                elif self.model_basename.startswith(('xls', 'mms')):
                    segments.append((i, start, end, speaker, waveform[start_sample:end_sample]))
            self.total_segments = len(segments)
            # transcribed = Parallel(n_jobs=-1)(delayed(self.transcribe_segment)(segment) for segment in segments)
            with concurrent.futures.ThreadPoolExecutor() as executor:
                transcribed_nested = list(executor.map(self.transcribe_segment, segments))
                transcribed = []
                for sublist in transcribed_nested:
                    if isinstance(sublist, list):
                        transcribed.extend(sublist)
                    else:
                        transcribed.append(sublist)

            # Shift timestamps back to original timebase
            if start_time > 0:
                shifted = []
                for item in transcribed:
                    s, e, spk, txt, wd = item
                    if wd:
                        wd = [(wt, ws, wts + start_time, wte + start_time)
                              for wt, ws, wts, wte in wd]
                    shifted.append((s + start_time, e + start_time, spk, txt, wd))
                transcribed = shifted

        # --- Create ELAN (.eaf) and Text (.txt) Files ---                
        self.time_records['storing'] = time.time()
        import pympi
        import re
        output_eaf = re.sub(r'\.(wav|mp4)', '.eaf', file_path)
        output_txt = re.sub(r'\.(wav|mp4)', '.txt', file_path)
        if os.path.exists(output_eaf):
            from datetime import datetime
            output_eaf = re.sub(r'\.eaf', '@' + datetime.now().strftime("%H-%M") + '.eaf', output_eaf)
            output_txt = re.sub(r'\.txt', '@' + datetime.now().strftime("%H-%M") + '.txt', output_txt)

        eaf = pympi.Elan.Eaf()
        eaf.add_linked_file(file_path)
        
        # Create main speaker tiers (always); word and confidence tiers only if requested
        tier_names = set()
        has_words = set()
        for item in transcribed:
            spk = item[2]
            tier_names.add(spk)
            if item[4]:  # has word annotations
                has_words.add(spk)
                
        for tier_name in sorted(tier_names):
            if tier_name not in eaf.get_tier_names():
                eaf.add_tier(tier_name)
            if self.output_confidence and tier_name in has_words:
                word_tier = f"{tier_name}_words"
                conf_tier = f"{tier_name}_conf"
                if word_tier not in eaf.get_tier_names():
                    eaf.add_tier(word_tier)
                if conf_tier not in eaf.get_tier_names():
                    eaf.add_tier(conf_tier)

        for item in transcribed:
            s, e, spk, txt, wd = item
            txt = txt.strip()
            if txt or only_segment:
                eaf.add_annotation(spk, int(s * 1000), int(e * 1000), txt)
            if self.output_confidence and wd:
                word_tier = f"{spk}_words"
                conf_tier = f"{spk}_conf"
                for wt, ws, w_start, w_end in wd:
                    if w_end > w_start:  # guard against zero-duration annotations
                        oov = "*" if self.word_set is not None and wt not in self.word_set else ""
                        t_start = int(w_start * 1000)
                        t_end   = int(w_end   * 1000)
                        eaf.add_annotation(word_tier, t_start, t_end, wt)
                        eaf.add_annotation(conf_tier, t_start, t_end, f"{ws}{oov}")
        eaf.to_file(output_eaf)
        
        if not only_segment:
            with open(output_txt, 'w', encoding='utf-8') as f:
                for item in transcribed:
                    s, e, spk, txt = item[0], item[1], item[2], item[3]
                    txt = txt.strip()
                    f.write(f"{convert_seconds_to_ms(s)}\t{convert_seconds_to_ms(e)}\t{spk}\t{txt}\n")

        self.time_records['end'] = time.time()
        time_report = '=====Time Report (min:sec)=====\n'
        time_report += 'Segmenting: ' + convert_seconds_to_hms(self.time_records['loading_asr'] - self.time_records['segmenting']) + '\n'
        time_report += 'Loading models: ' + convert_seconds_to_hms(self.time_records['transcribing'] - self.time_records['loading_asr']) + '\n'
        time_report += 'Transcribing: ' + convert_seconds_to_hms(self.time_records['storing'] - self.time_records['transcribing']) + '\n'
        time_report += 'Total: ' + convert_seconds_to_hms(self.time_records['end'] - self.time_records['start']) + '\n'
        if progress_callback:
            progress_callback(1, 1, f"Created {output_eaf} with {len(transcribed)} segments.", time_report)
        else:
            print(f"Created {output_eaf} with {len(transcribed)} segments.")
        return output_eaf

def convert_seconds_to_ms(time):
    hours = int(time // 3600)
    minutes = int((time % 3600) // 60) + (hours * 60)
    seconds = int(time % 60)
    milliseconds = int((time - int(time)) * 1000)
    return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

def convert_seconds_to_hms(time):
    hours = int(time // 3600)
    minutes = int((time % 3600) // 60) + (hours * 60)
    seconds = int(time % 60)
    return f"{minutes:02d}:{seconds:02d}"