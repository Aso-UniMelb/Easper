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
    def __init__(self, model_path, secondary_model_path="None", segmentation_model="pyannote", num_speakers=1, progress_callback=None, stop_check=None, language="en", secondary_language="en"):
        
        global torch, torchaudio, Pipeline, WhisperForConditionalGeneration, WhisperTokenizer, WhisperFeatureExtractor, Resample, librosa, Wav2Vec2ForCTC, Wav2Vec2Processor

        self.stopped = False

        self.progress_callback = progress_callback
        self.stop_check = stop_check

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
                    text_with_conf = ""
                else:
                    input_features = self.feature_extractor(segment_np, sampling_rate=16000, return_tensors='pt').input_features.to(self.device)
                    if not self.model_basename.endswith('.en'): #if model is not English only:
                        generated  = self.model.generate(input_features=input_features, language=self.LANG, task='transcribe', return_dict_in_generate=True, output_scores=True)
                    else:
                        generated  = self.model.generate(input_features=input_features, return_dict_in_generate=True, output_scores=True)
                    
                    scores = generated.scores
                    sequences = generated.sequences
                    prefix_len = sequences.size(1) - len(scores)
                    log_probs = []
                    for t, score_t in enumerate(scores):
                        token_id = sequences[0, prefix_len + t]
                        logp = torch.log_softmax(score_t, dim=-1)[0, token_id].item()
                        log_probs.append(logp)
                    avg_logprob = sum(log_probs) / len(log_probs) if log_probs else 0
                    text = self.tokenizer.batch_decode(sequences, skip_special_tokens=True)[0].strip()
                    import math
                    prob = math.exp(avg_logprob)
                    confidence_score = max(0, min(9, int(round(prob * 9))))
                    text_with_conf = f"[{confidence_score}] {text}" if text else ""

            elif self.model_basename.startswith(('xls', 'mms')):
                inputs = self.processor([audio_segment], sampling_rate=16000, return_tensors="pt", padding=True, return_attention_mask=True)
                logits = self.model(inputs.input_values, attention_mask=inputs.attention_mask).logits
                predicted_ids = torch.argmax(logits, dim=-1)
                text = self.processor.batch_decode(predicted_ids)[0].strip()
                probs = torch.softmax(logits, dim=-1)
                max_probs, _ = torch.max(probs, dim=-1)
                avg_prob = torch.mean(max_probs).item()
                confidence_score = max(0, min(9, int(round(avg_prob * 9))))
                text_with_conf = f"[{confidence_score}] {text}" if text else ""
            else:
                text_with_conf = ""

            if text_with_conf and any(character.isalnum() for character in text_with_conf):
                results.append((start, end, speaker, text_with_conf))
                main_text = text_with_conf
            else:
                results.append((start, end, speaker, ""))

            if self.secondary_basename:
                if self.secondary_basename.startswith('whisper'):
                    segment_np = audio_segment.squeeze().numpy()
                    if segment_np.size == 0:
                        text2_with_conf = ""
                    else:
                        input_features = self.secondary_feature_extractor(segment_np, sampling_rate=16000, return_tensors='pt').input_features.to(self.device)
                        if not self.secondary_basename.endswith('.en'):
                            generated  = self.secondary_model.generate(input_features=input_features, language=self.LANG2, task='transcribe', return_dict_in_generate=True, output_scores=True)
                        else:
                            generated  = self.secondary_model.generate(input_features=input_features, return_dict_in_generate=True, output_scores=True)
                        scores = generated.scores
                        sequences = generated.sequences
                        prefix_len = sequences.size(1) - len(scores)
                        log_probs = []
                        for t, score_t in enumerate(scores):
                            token_id = sequences[0, prefix_len + t]
                            logp = torch.log_softmax(score_t, dim=-1)[0, token_id].item()
                            log_probs.append(logp)
                        avg_logprob2 = sum(log_probs) / len(log_probs) if log_probs else 0
                        text2 = self.secondary_tokenizer.batch_decode(sequences, skip_special_tokens=True)[0].strip()
                        import math
                        prob2 = math.exp(avg_logprob2)
                        confidence_score2 = max(0, min(9, int(round(prob2 * 9))))
                        text2_with_conf = f"[{confidence_score2}] {text2}" if text2 else ""

                elif self.secondary_basename.startswith(('xls', 'mms')):
                    inputs = self.secondary_processor([audio_segment], sampling_rate=16000, return_tensors="pt", padding=True, return_attention_mask=True)
                    logits = self.secondary_model(inputs.input_values, attention_mask=inputs.attention_mask).logits
                    predicted_ids = torch.argmax(logits, dim=-1)
                    text2 = self.secondary_processor.batch_decode(predicted_ids)[0].strip()
                    probs = torch.softmax(logits, dim=-1)
                    max_probs, _ = torch.max(probs, dim=-1)
                    avg_prob2 = torch.mean(max_probs).item()
                    confidence_score2 = max(0, min(9, int(round(avg_prob2 * 9))))
                    text2_with_conf = f"[{confidence_score2}] {text2}" if text2 else ""
                else:
                    text2_with_conf = ""

                secondary_speaker = f"{speaker}_CS"
                if text2_with_conf and any(character.isalnum() for character in text2_with_conf):
                    results.append((start, end, secondary_speaker, text2_with_conf))
                else:
                    results.append((start, end, secondary_speaker, ""))

            # Update progress
            self.current_segment = self.current_segment + 1
            if self.progress_callback:
                self.progress_callback(self.current_segment, self.total_segments, f"Segment {self.current_segment}/{self.total_segments} Transcribed", main_text)
            else:
                print(f"Segment {index+1}: {main_text}")
            
            return results

    def transcribe_audio(self, file_path, min_on=0.5, min_off=0.5, progress_callback=None, stop_check=None, only_segment=False, segments_file=None, start_time=0, end_time=None):
        self.progress_callback = progress_callback
        self.stop_check = stop_check

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
             # Skip ASR and just prepare empty transcriptions
            for start, end, speaker in utterances:
                 # item is (start, end, speaker)
                 # transcribed expects (start, end, speaker, text)
                 transcribed.append((start + start_time, end + start_time, speaker, ""))
                 if self.secondary_basename:
                     transcribed.append((start + start_time, end + start_time, f"{speaker}_CS", ""))
            
            # Mock times to avoid errors in report
            self.time_records['loading_asr'] = time.time()
            self.time_records['transcribing'] = time.time()

        else:
            self.time_records['loading_asr'] = time.time()      
            # Check if stop was requested
            if stop_check and stop_check():
                self.stopped = True
                return

            
            if self.progress_callback:
                self.progress_callback(0, 0, f"Loading ASR model(s)...")
            else:
                print(f"Loading ASR model(s)...")
            # Lazy import of heavy libraries
            import torch
            import torchaudio

            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


            # Check if stop was requested
            if stop_check and stop_check():
                self.stopped = True
                return

            if self.model_basename.startswith('whisper') or self.secondary_basename.startswith('whisper'):
                from transformers import WhisperForConditionalGeneration, WhisperTokenizer, WhisperFeatureExtractor
                from torchaudio.transforms import Resample
            if self.model_basename.startswith(('xls', 'mms')) or self.secondary_basename.startswith(('xls', 'mms')):
                import librosa
                from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

            # primary model
            if self.model_basename.startswith('whisper'):
                self.model = WhisperForConditionalGeneration.from_pretrained(self.model_path).to(self.device)
                self.tokenizer = WhisperTokenizer.from_pretrained(self.model_path, language=self.LANG, task='transcribe')
                self.feature_extractor = WhisperFeatureExtractor.from_pretrained(self.model_path, task='transcribe')
            elif self.model_basename.startswith(('xls', 'mms')):
                self.model = Wav2Vec2ForCTC.from_pretrained(self.model_path + "/model/").to(self.device)
                self.processor = Wav2Vec2Processor.from_pretrained(self.model_path + "/processor")
            # secondary model
            if self.secondary_basename.startswith('whisper'):
                self.secondary_model = WhisperForConditionalGeneration.from_pretrained(self.secondary_model_path).to(self.device)
                self.secondary_tokenizer = WhisperTokenizer.from_pretrained(self.secondary_model_path, language=self.LANG, task='transcribe')
                self.secondary_feature_extractor = WhisperFeatureExtractor.from_pretrained(self.secondary_model_path, task='transcribe')
            elif self.secondary_basename.startswith(('xls', 'mms')):
                self.secondary_model = Wav2Vec2ForCTC.from_pretrained(self.secondary_model_path + "/model/").to(self.device)
                self.secondary_processor = Wav2Vec2Processor.from_pretrained(self.secondary_model_path + "/processor")

            
            self.time_records['transcribing'] = time.time()
            if progress_callback:
                progress_callback(0, 0, f"Transcribing {len(utterances)} segments, from {len(speakers)} speaker(s)...")
            else:
                print(f"Transcribing {len(utterances)} segments, from {len(speakers)} speaker(s)...")
            
            # Check if stop was requested or if diarization returned early
            if stop_check and stop_check():
                return None
            
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
                transcribed = [(s + start_time, e + start_time, spk, txt) for s, e, spk, txt in transcribed]

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
        
        tier_names = set()
        for _, _, speaker, _ in transcribed:
            tier_names.add(speaker)
            
        for tier_name in tier_names:
            if tier_name not in eaf.get_tier_names():
                eaf.add_tier(tier_name)

        for start, end, speaker, text in transcribed:
            text = text.strip()                
            eaf.add_annotation(speaker, int(start * 1000), int(end * 1000), text)
        eaf.to_file(output_eaf)
        
        if not only_segment:
            with open(output_txt, 'w', encoding='utf-8') as f:
                for start, end, speaker, text in transcribed:
                    text = text.strip()
                    f.write(f"{convert_seconds_to_ms(start)}\t{convert_seconds_to_ms(end)}\t{speaker}\t{text}\n")

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