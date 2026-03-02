"""
Transcriber UI module for Easper.
Contains the TranscribeToElanApp class for the transcription GUI.
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import shutil
import threading
from pydub import AudioSegment
import re

from src.core.transcriber import Wav2ElanTranscriber
from src.utils.paths import get_temp_dir, list_asr_models
from src.utils.languages import WHISPER_LANGUAGES

temp_dir = str(get_temp_dir())


class TranscribeToElanApp(ctk.CTkFrame):
    def __init__(self, parent, back_callback=None):
        super().__init__(parent)
        
        self.parent = parent
        self.back_callback = back_callback

        # configure grid layout
        self.grid_columnconfigure(0, weight=1)
        
        self.audio_file = ""
        self.input_eaf_path = None
        self.stop_requested = False
        self.output_elan_path = ""        

        # === Back Button (if callback provided)
        if back_callback:
            self.back_button = ctk.CTkButton(self, text="← Back to Menu", command=back_callback, width=120, fg_color="gray")
            self.back_button.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")

        # === Browse Button for Audio file
        self.browse_input_file_button = ctk.CTkButton(self, text="Select an untranscribed file\n(either an audio or a segmented ELAN file)...", command=self.browse_input_file)
        self.browse_input_file_button.grid(row=1, column=0, padx=10, pady=(20, 0), sticky="")
        # label showing file path
        self.file_path_label = ctk.CTkLabel(self, text="")
        self.file_path_label.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="")

        # === 
        self.segmentation_options_frame = ctk.CTkFrame(self)
        self.segmentation_options_frame.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        self.segmentation_options_frame.grid_columnconfigure(1, weight=1)

        # slider for number of speakers
        self.num_speakers_label = ctk.CTkLabel(self.segmentation_options_frame, text="Number of Speakers:")
        self.num_speakers_label.grid(row=0, column=0, padx=10, pady=5, sticky="e")
        
        self.num_speakers_frame = ctk.CTkFrame(self.segmentation_options_frame, fg_color="transparent")
        self.num_speakers_frame.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        self.num_speakers_frame.grid_columnconfigure(0, weight=1)
        
        self.num_speakers_slider = ctk.CTkSlider(self.num_speakers_frame, from_=1, to=5, number_of_steps=4, command=self.update_speakers_label)
        self.num_speakers_slider.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.num_speakers_slider.set(1)
        
        self.num_speakers_value_label = ctk.CTkLabel(self.num_speakers_frame, text="1", width=30)
        self.num_speakers_value_label.grid(row=0, column=1, sticky="w")

        # entry for minimum duration betwwen segments (in seconds)
        self.min_duration_between_segments_label = ctk.CTkLabel(self.segmentation_options_frame, text="Minimum Gap between Segments (in seconds):")
        self.min_duration_between_segments_label.grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.min_duration_between_segments_entry = ctk.CTkEntry(self.segmentation_options_frame, width=40)
        self.min_duration_between_segments_entry.grid(row=1, column=1, padx=10, pady=5, sticky="w")
        self.min_duration_between_segments_entry.insert(0, "0.4")

        # entry for minimum annotation length (in seconds)
        self.min_annotation_length_label = ctk.CTkLabel(self.segmentation_options_frame, text="Minimum Segment Length (in seconds):")
        self.min_annotation_length_label.grid(row=2, column=0, padx=10, pady=5, sticky="e")
        self.min_annotation_length_entry = ctk.CTkEntry(self.segmentation_options_frame, width=40)
        self.min_annotation_length_entry.grid(row=2, column=1, padx=10, pady=5, sticky="w")
        self.min_annotation_length_entry.insert(0, "0.5")

        # Start Time
        self.start_time_label = ctk.CTkLabel(self.segmentation_options_frame, text="Start Time (HH:MM:SS):")
        self.start_time_label.grid(row=3, column=0, padx=10, pady=5, sticky="e")
        self.start_time_entry = ctk.CTkEntry(self.segmentation_options_frame, width=100)
        self.start_time_entry.grid(row=3, column=1, padx=10, pady=5, sticky="w")
        self.start_time_entry.insert(0, "00:00:00")

        # End Time
        self.end_time_label = ctk.CTkLabel(self.segmentation_options_frame, text="End Time (HH:MM:SS):")
        self.end_time_label.grid(row=4, column=0, padx=10, pady=5, sticky="e")
        self.end_time_entry = ctk.CTkEntry(self.segmentation_options_frame, width=100, placeholder_text="HH:MM:SS")
        self.end_time_entry.grid(row=4, column=1, padx=10, pady=5, sticky="w")

        # Segmentation model
        self.segmentation_model_label = ctk.CTkLabel(self.segmentation_options_frame, text="Segmentation/Diarization Model:")
        self.segmentation_model_label.grid(row=5, column=0, padx=10, pady=5, sticky="e")
        self.segmentation_model_combobox = ctk.CTkComboBox(self.segmentation_options_frame, values=['speechbrain', 'pyannote'])
        self.segmentation_model_combobox.grid(row=5, column=1, padx=10, pady=5, sticky="ew")

        
        # === Transcription Options ===
        self.only_segment_switch = ctk.CTkSwitch(self.segmentation_options_frame, text="Only Segmentation (No Transcription)", command=self.on_only_segment_change)
        self.only_segment_switch.grid(row=6, column=0, padx=10, pady=5, sticky="ew", columnspan=2)

        self.segmentation_options_frame.grid_remove()


        # === Automatic Transcription Options
        self.transcription_options_frame = ctk.CTkFrame(self)
        self.transcription_options_frame.grid(row=4, column=0, padx=10, pady=5, sticky="ew")
        self.transcription_options_frame.grid_columnconfigure(1, weight=1)

        # combobox for ASR model
        self.asr_model_label = ctk.CTkLabel(self.transcription_options_frame, text="ASR Model:")
        self.asr_model_label.grid(row=0, column=0, padx=10, pady=5, sticky="e")
        self.asr_model_combobox = ctk.CTkComboBox(self.transcription_options_frame, values=[])
        self.asr_model_combobox.grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        # combobox for Language
        self.language_label = ctk.CTkLabel(self.transcription_options_frame, text="Tokenizer Language:")
        self.language_label.grid(row=1, column=0, padx=10, pady=5, sticky="e")
        
        # Sort languages by name
        sorted_languages = sorted(WHISPER_LANGUAGES.values())
        self.language_combobox = ctk.CTkComboBox(self.transcription_options_frame, values=sorted_languages)
        self.language_combobox.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        self.language_combobox.set("english")
      
        # combobox for Secondary ASR model
        self.secondary_model_label = ctk.CTkLabel(self.transcription_options_frame, text="ASR Model for Second Language:")
        self.secondary_model_label.grid(row=2, column=0, padx=10, pady=5, sticky="e")
        self.secondary_model_combobox = ctk.CTkComboBox(self.transcription_options_frame, values=[])
        self.secondary_model_combobox.grid(row=2, column=1, padx=10, pady=5, sticky="ew")

        # combobox for Language
        self.secondary_language_label = ctk.CTkLabel(self.transcription_options_frame, text="Tokenizer for Second Language:")
        self.secondary_language_label.grid(row=3, column=0, padx=10, pady=5, sticky="e")
        
        # Sort languages by name
        self.secondary_language_combobox = ctk.CTkComboBox(self.transcription_options_frame, values=sorted_languages)
        self.secondary_language_combobox.grid(row=3, column=1, padx=10, pady=5, sticky="ew")
        self.secondary_language_combobox.set("english")


        self.transcription_options_frame.grid_remove()

        # ===================
        self.process_frame = ctk.CTkFrame(self)
        self.process_frame.grid(row=5, column=0, padx=10, pady=5, sticky="ew")
        self.process_frame.grid_columnconfigure(1, weight=1)

        # output Elan path
        self.output_elan_path_label = ctk.CTkLabel(self.process_frame, text="Output ELAN Path:")
        self.output_elan_path_label.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        self.output_elan_path_entry = ctk.CTkEntry(self.process_frame, width=200)
        self.output_elan_path_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")


        # Button to Start Transcription
        self.transcription_button = ctk.CTkButton(self.process_frame, text="Transcribe!", font=ctk.CTkFont(weight="bold"), fg_color="green", command=self.start_transcription)
        self.transcription_button.grid(row=1, column=0, padx=10, pady=20, sticky="", columnspan=2)
        # Stop button (initially hidden)
        self.stop_button = ctk.CTkButton(self.process_frame, text="Stop", font=ctk.CTkFont(weight="bold"), fg_color="red", hover_color="darkred", command=self.stop_transcription)
        self.stop_button.grid(row=1, column=1, padx=10, pady=5, sticky="e")
        self.stop_button.grid_remove()
        # Progress label
        self.progress_label = ctk.CTkLabel(self.process_frame, text="")
        self.progress_label.grid(row=2, column=0, padx=10, pady=5, sticky="", columnspan=2)
        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(self.process_frame)
        self.progress_bar.grid(row=3, column=0, padx=10, pady=5, sticky="ew", columnspan=2)
        self.progress_bar.set(0)
        # last transcription (wordwrap)
        self.last_transcribed_label = ctk.CTkLabel(self.process_frame, text="", wraplength=400)
        self.last_transcribed_label.grid(row=4, column=0, padx=10, pady=5, sticky="", columnspan=2)
        
        self.process_frame.grid_remove()

        self.populate_models()

    def on_only_segment_change(self):
        if self.only_segment_switch.get():
            self.transcription_options_frame.grid_remove()
            self.transcription_button.configure(text="Segmentise!")
        else:
            self.transcription_options_frame.grid()
            self.transcription_button.configure(text="Transcribe!")

    def populate_models(self):
        models = list_asr_models()
        
        # Also check current directory for backward compatibility
        current_dir = os.getcwd()
        subdirs = [d for d in os.listdir(current_dir) if os.path.isdir(os.path.join(current_dir, d))]
        for d in subdirs:
            if (d.startswith('whisper') or d.startswith('xls') or d.startswith('mms')):
                full_path = os.path.join(current_dir, d)
                if full_path not in models:
                    models.append(full_path)
        
        if models:
            self.asr_model_combobox.configure(values=models)
            self.asr_model_combobox.set(models[0])
            self.secondary_model_combobox.configure(values=["None"] + models)
            self.secondary_model_combobox.set("None")
        else:
            messagebox.showerror("Error", "No ASR models found.")

    def ms_to_min_sec(self, milliseconds):
        ''' convert milliseconds to MM:SS format string (for display label) '''
        total_seconds = milliseconds // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}m {seconds}s"

    def format_seconds_to_hms(self, seconds):
        """Convert seconds to HH:MM:SS string."""
        if seconds is None:
            return ""
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

    def parse_time_string(self, time_str):
        """Convert HH:MM:SS, MM:SS, or SS string to seconds."""
        if not time_str or not time_str.strip():
            return None
        
        parts = time_str.strip().split(':')
        try:
            if len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + float(s)
            elif len(parts) == 2:
                m, s = parts
                return int(m) * 60 + float(s)
            elif len(parts) == 1:
                return float(parts[0])
            else:
                raise ValueError("Invalid time format")
        except ValueError:
            return None

    def browse_input_file(self):
        filetypes = (('WAV files', '*.wav'), ('MP4 files', '*.mp4'), ('ELAN files', '*.eaf'), ('All files', '*.*'))
        filename = filedialog.askopenfilename(title="Select File", filetypes=filetypes)
        
        if filename:
            self.process_frame.grid()
            self.input_eaf_path = None # Reset
            
            if filename.lower().endswith('.eaf'):                
                self.input_eaf_path = filename
                self.segmentation_options_frame.grid_remove()
                # Handle ELAN file
                # find .wav or .mp4   in the same directory as the .eaf file
                directory = os.path.dirname(filename)
                fname = os.path.basename(filename).lower()
                fname = re.sub(r'@.*\.eaf$', '.eaf', fname)
                files = [f for f in os.listdir(directory) if f.lower() == fname.replace('.eaf', '.wav') or f.lower() == fname.replace('.eaf', '.mp4')]
                if files:
                    self.audio_file = os.path.join(directory, files[0])
                else:
                    messagebox.showerror("Error", "Please put the audio file for this Elan file in the same directory with the same name.")
                # UI Logic for EAF
                self.only_segment_switch.grid_remove() # Hide only segment                
                self.file_path_label.configure(text=f"EAF: {os.path.basename(filename)}\nAudio: {os.path.basename(self.audio_file)}")
            else:
                # Handle Audio file
                self.segmentation_options_frame.grid()
                self.audio_file = filename
                self.input_eaf_path = None
                
                self.only_segment_switch.grid() # Show "Only Segment"
                
                self.file_path_label.configure(text=f"{self.audio_file}")
            
            # Common setup
            try:
                audio = AudioSegment.from_file(self.audio_file)
                self.file_path_label.configure(text=self.file_path_label.cget("text") + f" [Len:{self.ms_to_min_sec(len(audio))}]")
            except:
                pass # safely ignore if pydub fails to load for display
                
            self.transcription_options_frame.grid()
            self.output_elan_path = os.path.dirname(self.audio_file)
            self.output_elan_path_entry.delete(0, 'end')
            self.output_elan_path_entry.insert(0, self.output_elan_path)

            # Auto-populate start and end times
            try:
                audio_len_sec = len(AudioSegment.from_file(self.audio_file)) / 1000.0
                self.start_time_entry.delete(0, 'end')
                self.start_time_entry.insert(0, "00:00:00")
                self.end_time_entry.delete(0, 'end')
                self.end_time_entry.insert(0, self.format_seconds_to_hms(audio_len_sec))
            except:
                pass # safely ignore if pydub fails

        else:
            self.process_frame.grid_remove()
            self.transcription_options_frame.grid_remove()
            self.segmentation_options_frame.grid_remove()

    def update_speakers_label(self, value):
        """Update the label showing the current number of speakers."""
        self.num_speakers_value_label.configure(text=str(int(value)))
    
    def start_transcription(self):
        if not self.audio_file:
            messagebox.showerror("Error", "Please select a file.")
            return
        if not os.path.exists(self.output_elan_path):
            messagebox.showerror("Error", "Output folder path does not exist.")
            return

        # Collect values from UI
        model_name = self.asr_model_combobox.get()
        secondary_model_name = self.secondary_model_combobox.get()
        min_on = float(self.min_annotation_length_entry.get())
        min_off = float(self.min_duration_between_segments_entry.get())
        audio_file = self.audio_file
        
        # Get language code
        selected_language = self.language_combobox.get()
        selected_secondary_language = self.secondary_language_combobox.get()
        language_code = "en"
        secondary_language_code = "en"
        for code, name in WHISPER_LANGUAGES.items():
            if name == selected_language:
                language_code = code
                break
            if name == selected_secondary_language:
                secondary_language_code = code
                break

        # Get start and end times
        start_time = self.parse_time_string(self.start_time_entry.get())
        if start_time is None:
             start_time = 0
            
        end_time_str = self.end_time_entry.get()
        if end_time_str.strip():
            end_time = self.parse_time_string(end_time_str)
        else:
            end_time = None

        
        # Logic for segment source
        if self.input_eaf_path:
            # Started with EAF
            only_segment = False
            from_elan = self.input_eaf_path
            segmentation_model = "None" # Won't be used
        else:
            # Started with Audio
            segmentation_model = self.segmentation_model_combobox.get()
            only_segment = bool(self.only_segment_switch.get())
            from_elan = None

        # Disable UI and show stop button
        self.stop_requested = False
        self.transcription_button.configure(state="disabled")
        self.stop_button.grid()
        self.progress_bar.set(0)
        self.progress_label.configure(text="Initializing...")
        
        # Start the thread with arguments
        threading.Thread(target=self.run_process, args=(model_name, secondary_model_name, segmentation_model, audio_file, min_on, min_off, only_segment, from_elan, start_time, end_time, language_code, secondary_language_code), daemon=True).start()

    def run_process(self, model_name, secondary_model_name, segmentation_model, audio_file_path, min_on, min_off, only_segment, from_elan, start_time, end_time, language_code, secondary_language_code):
        # Initialize Transcriber with stop check
        num_speakers = int(self.num_speakers_slider.get())
        transcriber = Wav2ElanTranscriber(
            model_name, 
            secondary_model_name, 
            segmentation_model,
            num_speakers=num_speakers, 
            progress_callback=self.update_progress,
            stop_check=lambda: self.stop_requested,
            language=language_code,
            secondary_language=secondary_language_code
        )
        
        # Check if stopped during initialization
        if self.stop_requested or transcriber.stopped:
            self.finish_stopped()
            return
        
        # Run transcription with stop check
        output_file = transcriber.transcribe_audio(
            audio_file_path, 
            progress_callback=self.update_progress,
            min_on=min_on,
            min_off=min_off,
            stop_check=lambda: self.stop_requested,
            only_segment=only_segment,
            segments_file=from_elan,
            start_time=start_time,
            end_time=end_time
        )
        
        if self.stop_requested:
            self.finish_stopped()
        else:
            self.finish_success(output_file)

    def update_progress(self, current, total, message, transcribed=None):
        # Create a thread-safe wrapper
        def _update():
            if total > 0:
                percent = (current / total) * 100
                self.progress_bar.set(percent / 100)
                self.progress_label.configure(text=f'{message} ({int(percent)}%)')
            else:
                self.progress_label.configure(text=message)
            if transcribed:
                self.last_transcribed_label.configure(text=transcribed)
        self.after(0, _update)

    def stop_transcription(self):
        """Request the transcription process to stop."""
        self.stop_requested = True
        self.stop_button.configure(state="disabled")
        self.progress_label.configure(text="Stopping...")

    def finish_success(self, output_file):
        def _finish():
            shutil.rmtree(temp_dir, ignore_errors=True)
            self.stop_button.grid_remove()
            self.stop_button.configure(state="normal")
            self.progress_bar.set(1)
            self.progress_label.configure(text="Transcription completed successfully.")
            self.transcription_button.configure(state="normal")
            messagebox.showinfo("Success", f"Transcription completed successfully.\nOutput file: {output_file}")
        self.after(0, _finish)
    
    def finish_stopped(self):
        """Handle transcription stopped by user."""
        def _finish():
            shutil.rmtree(temp_dir, ignore_errors=True)
            self.stop_button.grid_remove()
            self.stop_button.configure(state="normal")
            self.progress_bar.set(0)
            self.progress_label.configure(text="Transcription stopped by user.")
            self.transcription_button.configure(state="normal")
        self.after(0, _finish)

    def finish_error(self, error_msg):
        def _finish():
            shutil.rmtree(temp_dir, ignore_errors=True)
            self.stop_button.grid_remove()
            self.stop_button.configure(state="normal")
            self.progress_bar.set(0)
            self.progress_label.configure(text="Transcription failed.")
            self.transcription_button.configure(state="normal")
            messagebox.showerror("Error", error_msg)
        self.after(0, _finish)
