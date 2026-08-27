"""
Transcriber UI module for Easper.
Contains the TranscribeToElanApp class for the transcription GUI.
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import sys
import subprocess
import shutil
import threading
from pydub import AudioSegment
import re

from src.core.transcriber import Wav2ElanTranscriber
from src.utils.paths import get_temp_dir, list_asr_models
from src.utils.languages import WHISPER_LANGUAGES
from src.utils.model_downloader import get_available_models

try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except Exception:
    HAS_DND = False
    DND_FILES = None

temp_dir = str(get_temp_dir())


class TranscribeToElanApp(ctk.CTkScrollableFrame):
    def __init__(self, parent, back_callback=None):
        super().__init__(parent, fg_color="transparent")

        self.parent = parent
        self.back_callback = back_callback
        self.grid_columnconfigure(0, weight=1)

        self.audio_file = ""
        self.input_eaf_path = None
        self.output_elan_path = ""

        # ── Top Bar (Back button & Model Status Badge) ───────────────
        self.top_bar_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_bar_frame.grid(row=0, column=0, padx=12, pady=(5, 0), sticky="ew")
        self.top_bar_frame.grid_columnconfigure(1, weight=1)

        if back_callback:
            self.back_button = ctk.CTkButton(
                self.top_bar_frame, text="← Back", command=back_callback,
                width=90, fg_color="gray", hover_color="#555"
            )
            self.back_button.grid(row=0, column=0, sticky="w")

        self.model_status_frame = ctk.CTkFrame(self.top_bar_frame, fg_color="transparent")
        self.model_status_frame.grid(row=0, column=1, sticky="e")

        # ── File picker ──────────────────────────────────────────────
        self.browse_input_file_button = ctk.CTkButton(
            self, text="📂  Drag & Drop or Click to Open Audio / ELAN File…",
            command=self.browse_input_file,
            height=46, font=ctk.CTkFont(size=14, weight="bold")
        )
        self.browse_input_file_button.grid(row=1, column=0, padx=12, pady=(5, 4), sticky="ew")

        self.file_path_label = ctk.CTkLabel(
            self, text="Drop audio (.wav, .mp4, .mp3) or ELAN (.eaf) file here, or click to browse.",
            text_color="gray", font=ctk.CTkFont(size=12)
        )
        self.file_path_label.grid(row=2, column=0, padx=12, pady=(0, 5))

        # Register Drag and Drop
        if HAS_DND:
            try:
                for widget in (self, self.browse_input_file_button, self.file_path_label):
                    widget.drop_target_register(DND_FILES)
                    widget.dnd_bind('<<Drop>>', self._on_file_drop)
            except Exception as e:
                print(f"DnD registration note: {e}")

        # ── Segmentation frame ───────────────────────────────────────
        self.segmentation_options_frame = ctk.CTkFrame(self)
        self.segmentation_options_frame.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        self.segmentation_options_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.segmentation_options_frame, text="Segmentation",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, columnspan=2, padx=12, pady=(5, 4), sticky="w")

        # Time range container frame
        _tf = ctk.CTkFrame(self.segmentation_options_frame, fg_color="transparent")
        _tf.grid(row=1, column=0, columnspan=2, padx=12, pady=4, sticky="ew")
        _tf.grid_columnconfigure((2, 5), weight=1)

        # From Time Controls
        ctk.CTkLabel(_tf, text="From:").grid(row=0, column=0, padx=(0, 4), sticky="e")
        self.start_time_entry = ctk.CTkEntry(_tf, width=80, placeholder_text="00:00:00")
        self.start_time_entry.grid(row=0, column=1, padx=(0, 6), sticky="w")
        self.start_time_entry.insert(0, "00:00:00")
        self.start_time_entry.bind("<FocusOut>", lambda e: self._on_start_entry_change())
        self.start_time_entry.bind("<Return>", lambda e: self._on_start_entry_change())

        self.start_time_slider = ctk.CTkSlider(
            _tf, from_=0, to=100, number_of_steps=1000,
            command=self._on_start_slider_change, width=120
        )
        self.start_time_slider.grid(row=0, column=2, padx=(0, 14), sticky="ew")
        self.start_time_slider.set(0)

        # To Time Controls
        ctk.CTkLabel(_tf, text="To:").grid(row=0, column=3, padx=(0, 4), sticky="e")
        self.end_time_entry = ctk.CTkEntry(_tf, width=80, placeholder_text="00:00:00")
        self.end_time_entry.grid(row=0, column=4, padx=(0, 6), sticky="w")
        self.end_time_entry.bind("<FocusOut>", lambda e: self._on_end_entry_change())
        self.end_time_entry.bind("<Return>", lambda e: self._on_end_entry_change())

        self.end_time_slider = ctk.CTkSlider(
            _tf, from_=0, to=100, number_of_steps=1000,
            command=self._on_end_slider_change, width=120
        )
        self.end_time_slider.grid(row=0, column=5, padx=(0, 8), sticky="ew")
        self.end_time_slider.set(100)

        # Reset to Full Audio Button
        self.full_audio_btn = ctk.CTkButton(
            _tf, text="↺ Full", width=52, height=28,
            font=ctk.CTkFont(size=11),
            fg_color="transparent", border_width=1,
            text_color=("gray20", "gray80"),
            hover_color=("gray85", "gray25"),
            command=self.reset_time_range_to_full
        )
        self.full_audio_btn.grid(row=0, column=6, sticky="e")

        # Range Duration Info Label
        self.time_range_info_label = ctk.CTkLabel(
            _tf, text="Selected: 00:00:00",
            font=ctk.CTkFont(size=11), text_color="gray"
        )
        self.time_range_info_label.grid(row=1, column=0, columnspan=7, pady=(2, 0), sticky="w")

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
        
        ctk.CTkLabel(_pmf, text="Speech Recognition Model:").grid(row=0, column=0, padx=(0, 4), sticky="e")
        self.asr_model_combobox = ctk.CTkComboBox(_pmf, values=[], width=180, command=self._on_asr_model_change)
        self.asr_model_combobox.grid(row=0, column=1, padx=(0, 20), sticky="w")

        self.language_label = ctk.CTkLabel(_pmf, text="Language:")
        self.language_label.grid(row=0, column=2, padx=(0, 4), sticky="e")
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

        ctk.CTkLabel(_qf, text="Word List (Valid Vocabulary):").grid(row=0, column=1, padx=(0, 4), sticky="e")
        self.wordlist_combobox = ctk.CTkComboBox(
            _qf, values=["None"], width=180
        )
        self.wordlist_combobox.grid(row=0, column=2, sticky="w")
        self.wordlist_combobox.set("None")

        # Second language sub-section
        ctk.CTkLabel(
            self.transcription_options_frame, text="Fallback Speech Recognition (optional, helps with multi-language code-switching)",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="gray"
        ).grid(row=4, column=0, columnspan=2, padx=12, pady=(5, 2), sticky="w")

        # Second ASR model and language - side by side
        _smf = ctk.CTkFrame(self.transcription_options_frame, fg_color="transparent")
        _smf.grid(row=5, column=0, columnspan=2, padx=12, pady=(4, 5), sticky="ew")

        ctk.CTkLabel(_smf, text="Fallback Model:").grid(row=0, column=0, padx=(0, 4), sticky="e")
        self.secondary_model_combobox = ctk.CTkComboBox(
            _smf, values=[], width=180, command=self._on_secondary_model_change
        )
        self.secondary_model_combobox.grid(row=0, column=1, padx=(0, 20), sticky="w")

        self.secondary_language_label = ctk.CTkLabel(_smf, text="Language:")
        self.secondary_language_label.grid(row=0, column=2, padx=(0, 4), sticky="e")
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
        self.open_output_folder_button = ctk.CTkButton(
            _op, text="📂 Open",
            width=70, height=28,
            font=ctk.CTkFont(size=12),
            fg_color="gray", hover_color="#555",
            command=self.open_output_folder
        )
        self.open_output_folder_button.grid(row=0, column=2, padx=(8, 0), sticky="e")

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

        # Multi-Stage Visual Stepper Container (Visual Proportions: 30% - 60% - 10%)
        self.stage_container_frame = ctk.CTkFrame(self.process_frame, fg_color="transparent")
        self.stage_container_frame.grid(row=3, column=0, columnspan=2, padx=12, pady=(6, 4), sticky="ew")
        self.stage_container_frame.grid_columnconfigure(0, weight=30)
        self.stage_container_frame.grid_columnconfigure(1, weight=0)
        self.stage_container_frame.grid_columnconfigure(2, weight=60)
        self.stage_container_frame.grid_columnconfigure(3, weight=0)
        self.stage_container_frame.grid_columnconfigure(4, weight=10)

        self.stage1_badge = ctk.CTkLabel(
            self.stage_container_frame, text="❶ Segmentation",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("gray85", "gray25"), text_color="gray",
            corner_radius=12, padx=10, pady=4
        )
        self.stage1_badge.grid(row=0, column=0, sticky="ew")

        self.stage_arrow_1 = ctk.CTkLabel(
            self.stage_container_frame, text="──>",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="gray"
        )
        self.stage_arrow_1.grid(row=0, column=1, padx=4)

        self.stage2_badge = ctk.CTkLabel(
            self.stage_container_frame, text="❷ Speech Recognition",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("gray85", "gray25"), text_color="gray",
            corner_radius=12, padx=10, pady=4
        )
        self.stage2_badge.grid(row=0, column=2, sticky="ew")

        self.stage_arrow_2 = ctk.CTkLabel(
            self.stage_container_frame, text="──>",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="gray"
        )
        self.stage_arrow_2.grid(row=0, column=3, padx=4)

        self.stage3_badge = ctk.CTkLabel(
            self.stage_container_frame, text="❸ Generating ELAN",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("gray85", "gray25"), text_color="gray",
            corner_radius=12, padx=10, pady=4
        )
        self.stage3_badge.grid(row=0, column=4, sticky="ew")

        # Progress detail label & Bar
        self.progress_label = ctk.CTkLabel(
            self.process_frame, text="",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray20", "gray85")
        )
        self.progress_label.grid(row=4, column=0, columnspan=2, padx=12, pady=(4, 2))

        self.progress_bar = ctk.CTkProgressBar(self.process_frame, height=10, corner_radius=5)
        self.progress_bar.grid(row=5, column=0, columnspan=2, padx=12, pady=(2, 6), sticky="ew")
        self.progress_bar.set(0)

        # Rich Segment Preview Feed
        self.preview_feed_frame = ctk.CTkFrame(self.process_frame, fg_color="transparent")
        self.preview_feed_frame.grid(row=6, column=0, columnspan=2, padx=12, pady=(2, 8), sticky="nsew")
        self.preview_feed_frame.grid_columnconfigure(0, weight=1)

        self.preview_feed_header = ctk.CTkLabel(
            self.preview_feed_frame, text="Live Transcription Feed:",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=("gray30", "gray70")
        )
        self.preview_feed_header.grid(row=0, column=0, sticky="w", pady=(0, 2))

        self.preview_textbox = ctk.CTkTextbox(
            self.preview_feed_frame,
            height=135,
            font=ctk.CTkFont(family="Consolas" if os.name == "nt" else "Monospace", size=11),
            corner_radius=8
        )
        self.preview_textbox.grid(row=1, column=0, sticky="nsew")
        self.preview_textbox.tag_config("hdr", foreground="#0284c7")
        self.preview_textbox.tag_config("sep", foreground="#6b7280")
        self.preview_textbox.tag_config("ts", foreground="#2563eb")
        self.preview_textbox.tag_config("txt")
        self._init_preview_feed()

        self.process_frame.grid_remove()

        self.populate_models()


    def on_only_segment_change(self):
        models = get_available_models()
        has_file = bool(getattr(self, "audio_file", "") or getattr(self, "input_eaf_path", None))

        if not models or self.only_segment_switch.get():
            self._current_only_segment = True
            self.transcription_options_frame.grid_remove()
            self.transcription_button.configure(text="Segmentise!")
            self.stage2_badge.grid_remove()
            self.stage_arrow_2.grid_remove()
            self.stage3_badge.configure(text="❷ Generating ELAN")
            self.stage_container_frame.grid_columnconfigure(0, weight=70)
            self.stage_container_frame.grid_columnconfigure(4, weight=30)
            if not models:
                self.only_segment_switch.select()
                self.only_segment_switch.configure(state="disabled")
        else:
            self._current_only_segment = False
            self.only_segment_switch.configure(state="normal")
            if has_file:
                self.transcription_options_frame.grid()
            else:
                self.transcription_options_frame.grid_remove()
            self.transcription_button.configure(text="Transcribe!")
            self.stage2_badge.grid()
            self.stage_arrow_2.grid()
            self.stage3_badge.configure(text="❸ Generating ELAN")
            self.stage_container_frame.grid_columnconfigure(0, weight=30)
            self.stage_container_frame.grid_columnconfigure(2, weight=60)
            self.stage_container_frame.grid_columnconfigure(4, weight=10)

    def _set_stage_ui_state(self, stage_idx, state):
        """
        Set visual styling for a stage badge.
        state: 'pending', 'active' (Blue), 'completed' (Green)
        """
        badges = [self.stage1_badge, self.stage2_badge, self.stage3_badge]
        titles = ["❶ Segmentation", "❷ Speech Recognition", "❸ Generating ELAN"]
        if getattr(self, "_current_only_segment", False):
            titles = ["❶ Segmentation", "", "❷ Generating ELAN"]

        if 0 <= stage_idx < len(badges):
            badge = badges[stage_idx]
            base_title = titles[stage_idx]
            clean_name = base_title.split(" ", 1)[-1] if " " in base_title else base_title
            num_prefix = base_title.split(" ", 1)[0] if " " in base_title else ""
            if state == 'pending':
                badge.configure(
                    text=base_title,
                    fg_color=("gray85", "gray25"),
                    text_color="gray"
                )
            elif state == 'active':
                # Started: Blue indicator
                badge.configure(
                    text=f"⏳ {num_prefix} {clean_name}",
                    fg_color=("#2563eb", "#1d4ed8"),
                    text_color="white"
                )
            elif state == 'completed':
                # Finished: Green indicator
                badge.configure(
                    text=f"✔ {clean_name}",
                    fg_color=("#16a34a", "#15803d"),
                    text_color="white"
                )

    def _init_preview_feed(self):
        """Initialize the preview feed with table header."""
        if not hasattr(self, "preview_textbox") or not self.preview_textbox.winfo_exists():
            return
        self.preview_textbox.configure(state="normal")
        self.preview_textbox.delete("1.0", "end")
        h_text = f"{'Time':<18} {'Transcription'}\n"
        sep = "-" * 65 + "\n"
        self.preview_textbox.insert("end", h_text, "hdr")
        self.preview_textbox.insert("end", sep, "sep")
        self.preview_textbox.configure(state="disabled")

    def _append_preview_row(self, time_str, text_str):
        """Append a live transcription row to the preview feed."""
        if not hasattr(self, "preview_textbox") or not self.preview_textbox.winfo_exists():
            return
        if not text_str and not time_str:
            return
        self.preview_textbox.configure(state="normal")
        if time_str:
            self.preview_textbox.insert("end", f"{time_str:<18} ", "ts")
        self.preview_textbox.insert("end", f"{text_str}\n", "txt")
        self.preview_textbox.see("end")
        self.preview_textbox.configure(state="disabled")

    def populate_models(self):
        models = get_available_models()

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
            self.only_segment_switch.configure(state="normal")
        else:
            self.asr_model_combobox.configure(values=["None"])
            self.asr_model_combobox.set("None")
            self.secondary_model_combobox.configure(values=["None"])
            self.secondary_model_combobox.set("None")
            self.only_segment_switch.select()
            self.only_segment_switch.configure(state="disabled")
        
        self._on_asr_model_change()
        self._on_secondary_model_change()
        self.on_only_segment_change()

        # Discover word list .txt files from the word_lists/ folder at project root
        current_dir = os.getcwd()
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

        self._refresh_model_status()

    def _refresh_model_status(self):
        """Update the model status indicator badge in Transcriber UI."""
        if not hasattr(self, "model_status_frame") or not self.model_status_frame.winfo_exists():
            return

        for widget in self.model_status_frame.winfo_children():
            widget.destroy()

        models = get_available_models()
        if models:
            names = [os.path.basename(m) for m in models]
            if len(names) == 1:
                display_text = f"✅ 1 ASR Model Ready ({names[0]})"
            elif len(names) == 2:
                display_text = f"✅ 2 ASR Models Ready ({names[0]}, {names[1]})"
            elif len(names) == 3:
                display_text = f"✅ 3 ASR Models Ready ({', '.join(names)})"
            else:
                display_text = f"✅ {len(names)} ASR Models Ready ({names[0]}, {names[1]}, +{len(names)-2} more)"

            badge = ctk.CTkLabel(
                self.model_status_frame,
                text=display_text,
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color=("gray85", "gray20"),
                text_color=("#15803d", "#4ade80"),
                corner_radius=12,
                padx=12,
                pady=4
            )
            badge.grid(row=0, column=0)
        else:
            badge_btn = ctk.CTkButton(
                self.model_status_frame,
                text="⚠️ No Models Found — Click to download (Multilingual Whisper small)",
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color="#d97706",
                hover_color="#b45309",
                text_color="white",
                height=28,
                corner_radius=14,
                command=self.open_model_download_dialog
            )
            badge_btn.grid(row=0, column=0)

    def _is_multilingual_whisper(self, model_display_name):
        """Check if a model is an exact official multilingual Whisper model (e.g. whisper-small, whisper-base)."""
        if not model_display_name or model_display_name == "None":
            return False
        full_path = self._model_path_map.get(model_display_name, model_display_name) if hasattr(self, "_model_path_map") else model_display_name
        base = os.path.basename(full_path).lower().strip()
        exact_multilingual = {
            "whisper-small",
            "whisper-base",
            "whisper-tiny",
            "whisper-medium",
            "whisper-large",
            "whisper-large-v1",
            "whisper-large-v2",
            "whisper-large-v3",
            "whisper-large-v3-turbo",
        }
        return base in exact_multilingual

    def _on_asr_model_change(self, choice=None):
        model_choice = self.asr_model_combobox.get()
        if self._is_multilingual_whisper(model_choice):
            self.language_label.grid()
            self.language_combobox.grid()
        else:
            self.language_combobox.set("english")
            self.language_label.grid_remove()
            self.language_combobox.grid_remove()

    def _on_secondary_model_change(self, choice=None):
        model_choice = self.secondary_model_combobox.get()
        if self._is_multilingual_whisper(model_choice):
            self.secondary_language_label.grid()
            self.secondary_language_combobox.grid()
        else:
            self.secondary_language_combobox.set("english")
            self.secondary_language_label.grid_remove()
            self.secondary_language_combobox.grid_remove()

    def open_model_download_dialog(self):
        """Open the model download dialog from transcriber UI."""
        from src.ui.launcher import DownloadModelModalDialog
        DownloadModelModalDialog(self, on_complete_callback=self._on_model_downloaded)

    def open_output_folder(self):
        """Open destination output directory in default file manager."""
        folder = self.output_elan_path_entry.get().strip() or getattr(self, "output_elan_path", "")
        if folder and os.path.exists(folder):
            try:
                if sys.platform == "win32":
                    os.startfile(folder)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", folder])
                else:
                    subprocess.Popen(["xdg-open", folder])
            except Exception as e:
                print(f"Could not open directory {folder}: {e}")
        else:
            messagebox.showwarning("Folder Not Found", f"The directory does not exist:\n{folder}")

    def _on_model_downloaded(self):
        self.populate_models()

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
                return None
        except ValueError:
            return None

    def _on_start_slider_change(self, value):
        """Called when start time slider is dragged."""
        end_val = self.end_time_slider.get()
        if value > end_val:
            value = end_val
            self.start_time_slider.set(value)

        self.start_time_entry.delete(0, 'end')
        self.start_time_entry.insert(0, self.format_seconds_to_hms(value))
        self._update_time_range_info()

    def _on_end_slider_change(self, value):
        """Called when end time slider is dragged."""
        start_val = self.start_time_slider.get()
        if value < start_val:
            value = start_val
            self.end_time_slider.set(value)

        self.end_time_entry.delete(0, 'end')
        self.end_time_entry.insert(0, self.format_seconds_to_hms(value))
        self._update_time_range_info()

    def _on_start_entry_change(self):
        """Validate and format start time text entry."""
        text = self.start_time_entry.get().strip()
        secs = self.parse_time_string(text)
        max_dur = getattr(self, "audio_duration_sec", 0)

        if secs is None or secs < 0:
            secs = 0
        elif max_dur > 0 and secs > max_dur:
            secs = max_dur

        end_secs = self.parse_time_string(self.end_time_entry.get().strip())
        if end_secs is not None and secs > end_secs:
            secs = end_secs

        self.start_time_entry.delete(0, 'end')
        self.start_time_entry.insert(0, self.format_seconds_to_hms(secs))
        self.start_time_slider.set(secs)
        self._update_time_range_info()

    def _on_end_entry_change(self):
        """Validate and format end time text entry."""
        text = self.end_time_entry.get().strip()
        secs = self.parse_time_string(text)
        max_dur = getattr(self, "audio_duration_sec", 0)

        if secs is None:
            secs = max_dur if max_dur > 0 else 0
        elif max_dur > 0 and secs > max_dur:
            secs = max_dur

        start_secs = self.parse_time_string(self.start_time_entry.get().strip())
        if start_secs is not None and secs < start_secs:
            secs = start_secs

        self.end_time_entry.delete(0, 'end')
        self.end_time_entry.insert(0, self.format_seconds_to_hms(secs))
        self.end_time_slider.set(secs)
        self._update_time_range_info()

    def reset_time_range_to_full(self):
        """Reset time range to cover full audio duration."""
        max_dur = getattr(self, "audio_duration_sec", 0)
        self.start_time_slider.set(0)
        self.start_time_entry.delete(0, 'end')
        self.start_time_entry.insert(0, "00:00:00")

        self.end_time_slider.set(max_dur)
        self.end_time_entry.delete(0, 'end')
        self.end_time_entry.insert(0, self.format_seconds_to_hms(max_dur))
        self._update_time_range_info()

    def _update_time_range_info(self):
        """Update the selected duration summary label."""
        if not hasattr(self, "time_range_info_label") or not self.time_range_info_label.winfo_exists():
            return
        start_secs = self.parse_time_string(self.start_time_entry.get()) or 0
        end_secs = self.parse_time_string(self.end_time_entry.get())
        max_dur = getattr(self, "audio_duration_sec", 0)

        if end_secs is None:
            end_secs = max_dur

        dur = max(0, end_secs - start_secs)
        dur_hms = self.format_seconds_to_hms(dur)
        total_hms = self.format_seconds_to_hms(max_dur) if max_dur > 0 else "N/A"
        self.time_range_info_label.configure(
            text=f"Selected: {dur_hms} ({self.ms_to_min_sec(int(dur*1000))}) of {total_hms} total"
        )

    def _on_file_drop(self, event):
        """Handle files dropped directly onto the window or drop targets."""
        if not event.data:
            return
        try:
            files = self.tk.splitlist(event.data)
            if files:
                first_file = files[0].strip()
                self.load_input_file(first_file)
        except Exception as e:
            messagebox.showerror("Drag & Drop Error", f"Could not open dropped file: {e}")

    def browse_input_file(self):
        filetypes = (('WAV files', '*.wav'), ('MP4 files', '*.mp4'), ('ELAN files', '*.eaf'), ('All files', '*.*'))
        filename = filedialog.askopenfilename(title="Select File", filetypes=filetypes)
        if filename:
            self.load_input_file(filename)
        else:
            if not self.audio_file and not self.input_eaf_path:
                self.process_frame.grid_remove()
                self.transcription_options_frame.grid_remove()
                self.segmentation_options_frame.grid_remove()

    def load_input_file(self, filename):
        """Load and configure UI for selected or dropped audio/ELAN file."""
        if not filename or not os.path.exists(filename):
            return

        valid_exts = ('.wav', '.mp4', '.eaf', '.mp3', '.m4a', '.flac', '.ogg')
        if not filename.lower().endswith(valid_exts):
            messagebox.showwarning(
                "Unsupported File Format",
                f"Please drop a supported audio file (.wav, .mp4, .mp3, .m4a) or an ELAN file (.eaf).\n\nReceived: {os.path.basename(filename)}"
            )
            return

        self.process_frame.grid()
        self.input_eaf_path = None  # Reset

        if filename.lower().endswith('.eaf'):
            models = get_available_models()
            if not models:
                messagebox.showwarning(
                    "No ASR Model Available",
                    "Transcribing an ELAN (.eaf) file requires an ASR model, but no models were found.\n\nPlease download a model first (e.g. Whisper Small) using the button at the top, or select an audio file for segmentation."
                )
                return
            self.input_eaf_path = filename
            self.segmentation_options_frame.grid_remove()
            # Handle ELAN file: find .wav or .mp4 in the same directory as the .eaf file
            directory = os.path.dirname(filename)
            fname = os.path.basename(filename).lower()
            fname = re.sub(r'@.*\.eaf$', '.eaf', fname)
            files = [f for f in os.listdir(directory) if f.lower() == fname.replace('.eaf', '.wav') or f.lower() == fname.replace('.eaf', '.mp4')]
            if files:
                self.audio_file = os.path.join(directory, files[0])
            else:
                messagebox.showerror("Error", "Please put the audio file for this Elan file in the same directory with the same name.")
                return
            # UI Logic for EAF
            self.only_segment_switch.grid_remove()  # Hide only segment
            self.file_path_label.configure(text=f"EAF: {os.path.basename(filename)}\nAudio: {os.path.basename(self.audio_file)}")
            self.transcription_options_frame.grid()
        else:
            # Handle Audio file
            self.segmentation_options_frame.grid()
            self.audio_file = filename
            self.input_eaf_path = None
            self.only_segment_switch.grid()  # Show "Only Segment"
            self.file_path_label.configure(text=f"{self.audio_file}")
            self.on_only_segment_change()

        # Common setup
        try:
            audio = AudioSegment.from_file(self.audio_file)
            self.file_path_label.configure(text=self.file_path_label.cget("text") + f" [Len:{self.ms_to_min_sec(len(audio))}]")
        except Exception:
            pass  # safely ignore if pydub fails to load for display

        self.output_elan_path = os.path.dirname(self.audio_file)
        self.output_elan_path_entry.delete(0, 'end')
        self.output_elan_path_entry.insert(0, self.output_elan_path)

        # Auto-populate start and end times & configure sliders
        try:
            audio_len_sec = len(AudioSegment.from_file(self.audio_file)) / 1000.0
            self.audio_duration_sec = audio_len_sec

            self.start_time_slider.configure(from_=0, to=audio_len_sec)
            self.start_time_slider.set(0)
            self.end_time_slider.configure(from_=0, to=audio_len_sec)
            self.end_time_slider.set(audio_len_sec)

            self.start_time_entry.delete(0, 'end')
            self.start_time_entry.insert(0, "00:00:00")
            self.end_time_entry.delete(0, 'end')
            self.end_time_entry.insert(0, self.format_seconds_to_hms(audio_len_sec))
            self._update_time_range_info()
        except Exception:
            pass

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

        # Ensure entries are validated & formatted before reading
        self._on_start_entry_change()
        self._on_end_entry_change()

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

        if not only_segment:
            models = get_available_models()
            if not models or model_name == "None" or not model_name:
                messagebox.showerror(
                    "No ASR Model Available",
                    "No speech recognition model is available for transcription.\n\nPlease download a model or enable 'Segmentation only'."
                )
                return

        # Reset stage indicators, progress bar, and preview feed
        self._current_only_segment = only_segment
        self._set_stage_ui_state(0, 'active')
        self._set_stage_ui_state(1, 'pending')
        self._set_stage_ui_state(2, 'pending')
        self.progress_bar.set(0)
        self._init_preview_feed()

        # Disable UI and show stop button
        self.transcription_button.configure(state="disabled")
        self.terminate_button.grid()
        self.progress_label.configure(text="[Step 1: Segmentation] Initializing process...")

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
                prog_val = max(0.0, min(1.0, float(current) / float(total)))
            else:
                prog_val = 0.0

            self.progress_bar.set(prog_val)
            pct = int(round(prog_val * 100))
            self.progress_label.configure(text=f"{message} ({pct}%)")

            # Update stage indicator badges based on message markers
            msg_lower = message.lower()
            if "step 3" in msg_lower or "generating elan" in msg_lower or "writing .eaf" in msg_lower:
                self._set_stage_ui_state(0, 'completed')
                self._set_stage_ui_state(1, 'completed')
                self._set_stage_ui_state(2, 'active')
            elif "step 2" in msg_lower or "speech recognition" in msg_lower or "transcrib" in msg_lower or "loading asr" in msg_lower:
                if getattr(self, "_current_only_segment", False):
                    # In only_segment mode, step 2 is Generating ELAN
                    self._set_stage_ui_state(0, 'completed')
                    self._set_stage_ui_state(2, 'active')
                else:
                    self._set_stage_ui_state(0, 'completed')
                    self._set_stage_ui_state(1, 'active')
                    self._set_stage_ui_state(2, 'pending')
            elif "step 1" in msg_lower or "segmentation" in msg_lower or "diariz" in msg_lower:
                self._set_stage_ui_state(0, 'active')
                self._set_stage_ui_state(1, 'pending')
                self._set_stage_ui_state(2, 'pending')
            elif "complet" in msg_lower or "created" in msg_lower:
                self._set_stage_ui_state(0, 'completed')
                self._set_stage_ui_state(1, 'completed')
                self._set_stage_ui_state(2, 'completed')

            # Append new row into the Rich Segment Preview Feed
            if transcribed:
                if isinstance(transcribed, dict):
                    t_time = transcribed.get("time", "")
                    t_text = transcribed.get("text", "")
                    self._append_preview_row(t_time, t_text)
                elif isinstance(transcribed, str):
                    clean_trans = transcribed.strip()
                    if clean_trans:
                        if "\t" in clean_trans:
                            parts = clean_trans.split("\t", 1)
                            self._append_preview_row(parts[0], parts[1])
                        elif not clean_trans.startswith("="):
                            self._append_preview_row("", clean_trans)
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
            self._set_stage_ui_state(0, 'completed')
            self._set_stage_ui_state(1, 'completed')
            self._set_stage_ui_state(2, 'completed')
            self.progress_bar.set(1.0)
            self.progress_label.configure(text="🎉 Transcription completed successfully! (100%)")
            self.transcription_button.configure(state="normal")
            messagebox.showinfo("Success", f"Transcription completed successfully.\n\nOutput file: {output_file}")
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
