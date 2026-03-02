"""
Dataset module for Easper.
Contains logic for building ASR training datasets from ELAN files.
"""
import os
import re
from collections import Counter
import pympi
from pydub import AudioSegment
import zipfile
import shutil

def get_wav_file(elan_file_path):
    directory = os.path.dirname(elan_file_path)
    filename = os.path.basename(elan_file_path).lower()
    wav_path = filename.replace('.eaf', '.wav')
    files = [f for f in os.listdir(directory) if f.lower() == wav_path]
    if files:
        return os.path.join(directory, files[0])
    return None

def build_training_dataset(elan_files, tier_vars, output_folder, progress_callback=None, log_callback=None):
    """
    Build training dataset from ELAN files.
    
    Args:
        elan_files: List of ELAN file paths
        tier_vars: Dictionary mapping file paths to tier checkbox variables
        output_folder: Output folder path
        progress_callback: Optional callback for progress updates (current, total)
        log_callback: Optional callback for logging messages
    
    Returns:
        Path to the last created zip file
    """
    zip_path = None
    temp_folder = os.path.join(output_folder, '__temp')
    os.makedirs(temp_folder, exist_ok=True)
    tsv_path = f'{temp_folder}/metadata.tsv'
    with open(tsv_path, "w", encoding="utf-8") as wfile:    
        for elan_file_path in elan_files:
            basename = os.path.basename(elan_file_path)
            wav_path = get_wav_file(elan_file_path)
            
            if not wav_path:
                if log_callback:
                    log_callback(f"Warning: No WAV file found for {basename}")
                continue

            eaf = pympi.Elan.Eaf(elan_file_path)
            segments = []
            file_name = os.path.basename(elan_file_path).split('.')[0]
            
            for tier in eaf.get_tier_names():
                # Skip unchecked tiers
                if elan_file_path in tier_vars and tier in tier_vars[elan_file_path]:
                    if tier_vars[elan_file_path][tier].get() == "":
                        continue
                else:
                    continue
                
                annotations = []
                temp_ann = ()
                for ann in eaf.get_annotation_data_for_tier(tier):
                    if len(ann) == 3:
                        annotations.append(ann)
                    
                    if len(ann) == 4: # When the tier has a parent tier
                        if temp_ann == ():
                            temp_ann = (ann[0], ann[1], ann[2])
                        elif ann[0] == temp_ann[0] and ann[1] == temp_ann[1]:
                            temp_ann = (ann[0], ann[1], temp_ann[2] + " " + ann[2])
                        else:
                            annotations.append(temp_ann)
                            temp_ann = (ann[0], ann[1], ann[2])
                # Add the last annotation
                if temp_ann != ():
                    annotations.append(temp_ann)
                
                for annotation in annotations:
                    start, end, text = annotation[0], annotation[1], annotation[2]
                    text = text.strip()
                    if not text:
                        continue
                    if end - start > 30 * 1000:
                        if log_callback:
                            total_seconds = start // 1000
                            minutes = total_seconds // 60
                            seconds = total_seconds % 60
                            log_callback(f"Warning: Long segment found for {basename} at {minutes}:{seconds:02}")
                        continue
                    segments.append((start, end, text))

            output_dir = f'{temp_folder}/{file_name}/'
            os.makedirs(output_dir, exist_ok=True)
            # check if time offset is set for the linked wav file
            offset = 0
            linked_files = eaf.get_linked_files()
            for file_info in linked_files:
                # We check for the media URL to identify the WAV file
                media_url = file_info.get('MEDIA_URL', '')
                
                if media_url.lower().endswith('.wav'):
                    offset = int(file_info.get('TIME_ORIGIN', 0)) # in milliseconds

            audio = AudioSegment.from_wav(wav_path)
            audio = audio[offset:]
            audio = audio.set_channels(1)
            audio = audio.set_frame_rate(16000)
            audio = audio.set_sample_width(2) # Set the sample width to 2 bytes (16-bit)
        
            total_length = 0
            total_segments = len(segments)
            
            
            for i, (start, end, text) in enumerate(segments):
                segment_audio = audio[start:end]
                segment_path = os.path.join(output_dir, f"{(i + 1):04d}.wav")
                segment_audio.export(segment_path, format="wav")
                wfile.write(f"{file_name}/{(i + 1):04d}.wav\t{text}\n")
                total_length += (end-start)
                
                if progress_callback:
                    progress_callback(i + 1, total_segments)
            if log_callback:
                log_callback(f" - [Done]: | {basename}")

    # zip all files in the temp directory
    
    zip_path = f'{output_folder}/asr_training_dataset.zip'
    if os.path.exists(zip_path):
        os.remove(zip_path)
        
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(temp_folder):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, temp_folder)
                zipf.write(full_path, arcname)
    
    # delete the temp directory
    shutil.rmtree(temp_folder, ignore_errors=True)      

    
    return zip_path
