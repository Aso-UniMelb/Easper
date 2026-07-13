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
        self.grid_columnconfigure(0, weight=1)

        self.audio_file = ""
        self.input_eaf_path = None
        self.output_elan_path = ""

        # ── Back button ──────────────────────────────────────────────
        if back_callback:
            self.back_button = ctk.CTkButton(
                self, text="← Back", command=back_callback,
                width=90, fg_color="gray", hover_color="#555"
            )
            self.back_button.grid(row=0, column=0, padx=12, pady=(5, 0), sticky="w")

        # ── File picker ──────────────────────────────────────────────
        self.browse_input_file_button = ctk.CTkButton(
            self, text="📂  Open Audio or ELAN File…",
            command=self.browse_input_file,
            height=44, font=ctk.CTkFont(size=14, weight="bold")
        )
        self.browse_input_file_button.grid(row=1, column=0, padx=12, pady=(5, 4), sticky="ew")

        self.file_path_label = ctk.CTkLabel(
            self, text="Select an audio file (.wav or .mp4) or a segmented but untranscribed ELAN file.",
            text_color="gray", font=ctk.CTkFont(size=12)
        )
        self.file_path_label.grid(row=2, column=0, padx=12, pady=(0, 5))

        # ── Segmentation frame ───────────────────────────────────────
        self.segmentation_options_frame = ctk.CTkFrame(self)
        self.segmentation_options_frame.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        self.segmentation_options_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.segmentation_options_frame, text="Segmentation",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, columnspan=2, padx=12, pady=(5, 4), sticky="w")

        # Time range – From / To side by side
        _tf = ctk.CTkFrame(self.segmentation_options_frame, fg_color="transparent")
        _tf.grid(row=1, column=0, columnspan=2, padx=12, pady=4, sticky="ew")
        ctk.CTkLabel(_tf, text="From Time (HH:MM:SS):").grid(row=0, column=0, padx=(0, 4), sticky="e")
        self.start_time_entry = ctk.CTkEntry(_tf, width=90, placeholder_text="00:00:00")
        self.start_time_entry.grid(row=0, column=1, padx=(0, 16), sticky="w")
        self.start_time_entry.insert(0, "00:00:00")
        ctk.CTkLabel(_tf, text="To Time (HH:MM:SS):").grid(row=0, column=2, padx=(0, 4), sticky="e")
        self.end_time_entry = ctk.CTkEntry(_tf, width=90, placeholder_text="HH:MM:SS")
        self.end_time_entry.grid(row=0, column=3, sticky="w")

        # Min gap / Min length – side by side
        _df = ctk.CTkFrame(self.segmentation_options_frame, fg_color="transparent")
        _df.grid(row=2, column=0, columnspan=2, padx=12, pady=4, sticky="ew")
        ctk.CTkLabel(_df, text="Merge segments if gap is shorter than (in seconds):").grid(row=0, column=0, padx=(0, 4), sticky="e")
        self.min_duration_between_segments_entry = ctk.CTkEntry(_df, width=60)
        self.min_duration_between_segments_entry.grid(row=0, column=1, padx=(0, 20), sticky="w")
        self.min_duration_between_segments_entry.insert(0, "0.4")
        ctk.CTkLabel(_df, text="Discard segments shorter than (in seconds):").grid(row=0, column=2, padx=(0, 4), sticky="e")
        self.min_annotation_length_entry = ctk.CTkEntry(_df, width=60)
        self.min_annotation_length_entry.grid(row=0, column=3, sticky="w")
        self.min_annotation_length_entry.insert(0, "0.5")

        # Speakers and Diarization Model - side by side
        _sf = ctk.CTkFrame(self.segmentation_options_frame, fg_color="transparent")
        _sf.grid(row=3, column=0, columnspan=2, padx=12, pady=4, sticky="ew")
        
        ctk.CTkLabel(_sf, text="Number of Speakers:").grid(row=0, column=0, padx=(0, 4), sticky="e")
        self.num_speakers_frame = ctk.CTkFrame(_sf, fg_color="transparent")
        self.num_speakers_frame.grid(row=0, column=1, padx=(0, 20), sticky="w")
        self.num_speakers_slider = ctk.CTkSlider(
            self.num_speakers_frame, from_=1, to=5, number_of_steps=4,
            command=self.update_speakers_label, width=100
        )
        self.num_speakers_slider.grid(row=0, column=0, padx=(0, 4), sticky="ew")
        self.num_speakers_slider.set(1)
        self.num_speakers_value_label = ctk.CTkLabel(self.num_speakers_frame, text="1", width=20)
        self.num_speakers_value_label.grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(_sf, text="Segmentation/Diarization Model:").grid(row=0, column=2, padx=(0, 4), sticky="e")
        self.segmentation_model_combobox = ctk.CTkComboBox(
            _sf, values=["speechbrain", "pyannote"], width=120
        )
        self.segmentation_model_combobox.grid(row=0, column=3, sticky="w")

        # Only-segment toggle
        self.only_segment_switch = ctk.CTkSwitch(
            self.segmentation_options_frame,
            text="Segmentation only  (skip transcription)",
            command=self.on_only_segment_change
        )
        self.only_segment_switch.grid(
            row=4, column=0, columnspan=2, padx=12, pady=(4, 5), sticky="w"
        )

        self.segmentation_options_frame.grid_remove()

        # ── Transcription frame ──────────────────────────────────────
        self.transcription_options_frame = ctk.CTkFrame(self)
        self.transcription_options_frame.grid(row=4, column=0, padx=10, pady=5, sticky="ew")
        self.transcription_options_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.transcription_options_frame, text="Transcription",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, columnspan=2, padx=12, pady=(5, 4), sticky="w")

        sorted_languages = sorted(WHISPER_LANGUAGES.values())

        # Primary model + language - side by side
        _pmf = ctk.CTkFrame(self.transcription_options_frame, fg_color="transparent")
        _pmf.grid(row=1, column=0, columnspan=2, padx=12, pady=4, sticky="ew")
        
        ctk.CTkLabel(_pmf, text="Main ASR Model:").grid(row=0, column=0, padx=(0, 4), sticky="e")
        self.asr_model_combobox = ctk.CTkComboBox(_pmf, values=[], width=180)
        self.asr_model_combobox.grid(row=0, column=1, padx=(0, 20), sticky="w")

        ctk.CTkLabel(_pmf, text="Tokenizer Language:").grid(row=0, column=2, padx=(0, 4), sticky="e")
        self.language_combobox = ctk.CTkComboBox(
            _pmf, values=sorted_languages, width=120
        )
        self.language_combobox.grid(row=0, column=3, sticky="w")
        self.language_combobox.set("english")

        # Quality sub-section
        ctk.CTkLabel(
            self.transcription_options_frame, text="Quality & Out-of-Vocabulary Checks",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="gray"
        ).grid(row=2, column=0, columnspan=2, padx=12, pady=(5, 2), sticky="w")

        # Output confidence and word list OOV - side by side
        _qf = ctk.CTkFrame(self.transcription_options_frame, fg_color="transparent")
        _qf.grid(row=3, column=0, columnspan=2, padx=12, pady=4, sticky="ew")

        self.output_confidence_checkbox = ctk.CTkCheckBox(
            _qf, text="Output Confidence Scores"
        )
        self.output_confidence_checkbox.grid(row=0, column=0, padx=(0, 20), sticky="w")
        self.output_confidence_checkbox.select()

        ctk.CTkLabel(_qf, text="Word List (Valid Vocabulary):").grid(row=0, column=1, padx=(0, 4), sticky="e")
        self.wordlist_combobox = ctk.CTkComboBox(
            _qf, values=["None"], width=180
        )
        self.wordlist_combobox.grid(row=0, column=2, sticky="w")
        self.wordlist_combobox.set("None")

        # Second language sub-section
        ctk.CTkLabel(
            self.transcription_options_frame, text="Second Language Transcription (optional)",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="gray"
        ).grid(row=4, column=0, columnspan=2, padx=12, pady=(5, 2), sticky="w")

        # Second ASR model and language - side by side
        _smf = ctk.CTkFrame(self.transcription_options_frame, fg_color="transparent")
        _smf.grid(row=5, column=0, columnspan=2, padx=12, pady=(4, 5), sticky="ew")

        ctk.CTkLabel(_smf, text="Secondary ASR Model:").grid(row=0, column=0, padx=(0, 4), sticky="e")
        self.secondary_model_combobox = ctk.CTkComboBox(
            _smf, values=[], width=180
        )
        self.secondary_model_combobox.grid(row=0, column=1, padx=(0, 20), sticky="w")

        ctk.CTkLabel(_smf, text="Tokenizer Language:").grid(row=0, column=2, padx=(0, 4), sticky="e")
        self.secondary_language_combobox = ctk.CTkComboBox(
            _smf, values=sorted_languages, width=120
        )
        self.secondary_language_combobox.grid(row=0, column=3, sticky="w")
        self.secondary_language_combobox.set("english")

        self.transcription_options_frame.grid_remove()

        # ── Output / Process frame ───────────────────────────────────
        self.process_frame = ctk.CTkFrame(self)
        self.process_frame.grid(row=5, column=0, padx=10, pady=5, sticky="ew")
        self.process_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.process_frame, text="Output",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, columnspan=2, padx=12, pady=(5, 4), sticky="w")

        # Output path
        _op = ctk.CTkFrame(self.process_frame, fg_color="transparent")
        _op.grid(row=1, column=0, columnspan=2, padx=12, pady=4, sticky="ew")
        _op.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_op, text="Save to:").grid(row=0, column=0, padx=(0, 8), sticky="e")
        self.output_elan_path_entry = ctk.CTkEntry(_op)
        self.output_elan_path_entry.grid(row=0, column=1, sticky="ew")

        # Action buttons
        _ab = ctk.CTkFrame(self.process_frame, fg_color="transparent")
        _ab.grid(row=2, column=0, columnspan=2, padx=12, pady=(5, 8), sticky="ew")
        _ab.grid_columnconfigure(0, weight=1)

        self.transcription_button = ctk.CTkButton(
            _ab, text="▶  Transcribe!",
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#2a7d2a", hover_color="#1e5c1e",
            height=42, command=self.start_transcription
        )
        self.transcription_button.grid(row=0, column=0, sticky="ew")

        self.terminate_button = ctk.CTkButton(
            _ab, text="✕  Cancel",
            font=ctk.CTkFont(weight="bold"),
            fg_color="#c0392b", hover_color="#922b21",
            height=42, command=self.terminate_easper
        )
        self.terminate_button.grid(row=0, column=1, padx=(8, 0))
        self.terminate_button.grid_remove()

        # Progress
        self.progress_label = ctk.CTkLabel(
            self.process_frame, text="",
            font=ctk.CTkFont(size=12), text_color="gray"
        )
        self.progress_label.grid(row=3, column=0, columnspan=2, padx=12, pady=(4, 2))

        self.progress_bar = ctk.CTkProgressBar(self.process_frame, height=8)
        self.progress_bar.grid(row=4, column=0, columnspan=2, padx=12, pady=(0, 4), sticky="ew")
        self.progress_bar.set(0)

        self.last_transcribed_label = ctk.CTkLabel(
            self.process_frame, text="", wraplength=420,
            font=ctk.CTkFont(size=11), text_color="gray"
        )
        self.last_transcribed_label.grid(row=5, column=0, columnspan=2, padx=12, pady=(0, 5))

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

        # Build display-name → full-path map for models (basename only, cross-platform)
        self._model_path_map = {}
        for full_path in models:
            name = os.path.basename(full_path)
            # Handle unlikely duplicate basenames by appending parent folder name
            if name in self._model_path_map:
                name = os.path.basename(os.path.dirname(full_path)) + "/" + name
            self._model_path_map[name] = full_path

        model_names = list(self._model_path_map.keys())
        if model_names:
            self.asr_model_combobox.configure(values=model_names)
            self.asr_model_combobox.set(model_names[0])
            self.secondary_model_combobox.configure(values=["None"] + model_names)
            self.secondary_model_combobox.set("None")
        else:
            messagebox.showerror("Error", "No ASR models found.")

        # Discover word list .txt files from the word_lists/ folder at project root
        wordlists_dir = os.path.join(current_dir, "word_lists")
        self._wordlist_path_map = {}  # display name → full path
        wordlist_names = ["None"]
        if os.path.isdir(wordlists_dir):
            for f in sorted(os.listdir(wordlists_dir)):
                if f.lower().endswith(".txt"):
                    full_path = os.path.join(wordlists_dir, f)
                    self._wordlist_path_map[f] = full_path
                    wordlist_names.append(f)
        self.wordlist_combobox.configure(values=wordlist_names)
        self.wordlist_combobox.set("None")

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

        # Collect values from UI — resolve display names back to full paths
        model_name = self._model_path_map.get(self.asr_model_combobox.get(),
                                               self.asr_model_combobox.get())
        secondary_display = self.secondary_model_combobox.get()
        secondary_model_name = ("None" if secondary_display == "None"
                                else self._model_path_map.get(secondary_display, secondary_display))
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
            if name == selected_secondary_language:
                secondary_language_code = code

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
        self.transcription_button.configure(state="disabled")
        self.terminate_button.grid()
        self.progress_bar.set(0)
        self.progress_label.configure(text="Initializing...")

        # Load word list into a set (if one is selected)
        wordlist_display = self.wordlist_combobox.get()
        wordlist_path = self._wordlist_path_map.get(wordlist_display, None)
        word_set = None
        if wordlist_path and os.path.isfile(wordlist_path):
            try:
                with open(wordlist_path, 'r', encoding='utf-8') as wf:
                    word_set = {line.strip() for line in wf
                                if line.strip() and not line.strip().startswith('#')}
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load word list: {e}")
                return
        
        # Read confidence score checkbox
        output_confidence = bool(self.output_confidence_checkbox.get())

        # Start the thread with arguments
        threading.Thread(target=self.run_process, args=(model_name, secondary_model_name, segmentation_model, audio_file, min_on, min_off, only_segment, from_elan, start_time, end_time, language_code, secondary_language_code, word_set, output_confidence), daemon=True).start()

    def run_process(self, model_name, secondary_model_name, segmentation_model, audio_file_path, min_on, min_off, only_segment, from_elan, start_time, end_time, language_code, secondary_language_code, word_set=None, output_confidence=True):
        # Initialize Transcriber
        num_speakers = int(self.num_speakers_slider.get())
        transcriber = Wav2ElanTranscriber(
            model_name, 
            secondary_model_name, 
            segmentation_model,
            num_speakers=num_speakers, 
            progress_callback=self.update_progress,
            language=language_code,
            secondary_language=secondary_language_code,
            word_set=word_set,
            output_confidence=output_confidence
        )
        
        # Run transcription
        output_file = transcriber.transcribe_audio(
            audio_file_path, 
            progress_callback=self.update_progress,
            min_on=min_on,
            min_off=min_off,
            only_segment=only_segment,
            segments_file=from_elan,
            start_time=start_time,
            end_time=end_time
        )
        
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

    def terminate_easper(self):
        """Close the entire application immediately."""
        shutil.rmtree(temp_dir, ignore_errors=True)
        import os
        os._exit(0)

    def finish_success(self, output_file):
        def _finish():
            shutil.rmtree(temp_dir, ignore_errors=True)
            self.terminate_button.grid_remove()
            self.terminate_button.configure(state="normal")
            self.progress_bar.set(1)
            self.progress_label.configure(text="Transcription completed successfully.")
            self.transcription_button.configure(state="normal")
            messagebox.showinfo("Success", f"Transcription completed successfully.\nOutput file: {output_file}")
        self.after(0, _finish)

    def finish_error(self, error_msg):
        def _finish():
            shutil.rmtree(temp_dir, ignore_errors=True)
            self.terminate_button.grid_remove()
            self.terminate_button.configure(state="normal")
            self.progress_bar.set(0)
            self.progress_label.configure(text="Transcription failed.")
            self.transcription_button.configure(state="normal")
            messagebox.showerror("Error", error_msg)
        self.after(0, _finish)
