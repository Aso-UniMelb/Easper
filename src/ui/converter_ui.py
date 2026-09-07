"""
Converter UI module for Easper.
Provides the BatchMediaConverterApp GUI for converting audio/video files
to 16 kHz mono WAV with optional stereo channel splitting.
"""
import os
import re
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import List, Dict, Any

import customtkinter as ctk

from src.core.media_converter import (
    ALL_SUPPORTED_EXTENSIONS,
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    probe_media,
    convert_media_file,
    format_duration,
    format_size,
    is_supported_media_file
)

try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except Exception:
    HAS_DND = False
    DND_FILES = None


class BatchMediaConverterApp(ctk.CTkScrollableFrame):
    """
    CustomTkinter view for batch media conversion to 16 kHz mono WAV.
    """
    def __init__(self, parent, back_callback=None):
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.back_callback = back_callback

        self.grid_columnconfigure(0, weight=1)

        # State
        self.queued_files: List[Dict[str, Any]] = []
        self.is_converting = False
        self.cancel_requested = False
        self.output_dest_mode = ctk.StringVar(value="source")  # "source" or "custom"
        self.custom_output_dir = ctk.StringVar(value="")
        self.split_channels_var = ctk.BooleanVar(value=False)

        # ── 1. Top Bar (Back button & Header) ──────────────────────
        self.top_bar_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_bar_frame.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="ew")
        self.top_bar_frame.grid_columnconfigure(1, weight=1)

        if back_callback:
            self.back_button = ctk.CTkButton(
                self.top_bar_frame,
                text="← Back to Menu",
                command=self._on_back_clicked,
                width=110,
                height=30,
                font=ctk.CTkFont(size=12),
                fg_color=("gray75", "gray30"),
                hover_color=("gray65", "gray40"),
                text_color=("black", "white")
            )
            self.back_button.grid(row=0, column=0, sticky="w")

        title_box = ctk.CTkFrame(self.top_bar_frame, fg_color="transparent")
        title_box.grid(row=0, column=1, sticky="w", padx=(15, 0))

        title_lbl = ctk.CTkLabel(
            title_box,
            text="Batch Media Converter",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_lbl.grid(row=0, column=0, sticky="w")

        subtitle_lbl = ctk.CTkLabel(
            title_box,
            text="Convert audio & video files to 16 kHz mono WAV for Whisper & ELAN",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        subtitle_lbl.grid(row=1, column=0, sticky="w")

        # ── 2. Drag & Drop / File Selection Zone ────────────────────
        drop_frame = ctk.CTkFrame(self, corner_radius=12)
        drop_frame.grid(row=1, column=0, padx=15, pady=(10, 6), sticky="ew")
        drop_frame.grid_columnconfigure(0, weight=1)

        self.drop_button = ctk.CTkButton(
            drop_frame,
            text="📂  Drag & Drop Media Files Here, or Click to Browse…",
            command=self.browse_files,
            height=46,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=("gray85", "gray22"),
            hover_color=("gray75", "gray28"),
            text_color=("gray10", "gray90"),
            border_width=2,
            border_color=("gray70", "gray35")
        )
        self.drop_button.grid(row=0, column=0, padx=15, pady=(15, 6), sticky="ew")

        self.drop_hint_lbl = ctk.CTkLabel(
            drop_frame,
            text="Supports video (.mp4, .mov, .mkv, .avi, .mts...) and audio (.wav, .mp3, .m4a, .flac, .ogg...)",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.drop_hint_lbl.grid(row=1, column=0, padx=15, pady=(0, 12))

        # Register Drag and Drop if available
        if HAS_DND:
            try:
                for widget in (self, drop_frame, self.drop_button, self.drop_hint_lbl):
                    widget.drop_target_register(DND_FILES)
                    widget.dnd_bind('<<Drop>>', self._on_dnd_drop)
            except Exception as e:
                print(f"DnD registration note in Converter UI: {e}")

        # Action buttons row: Add Files, Add Folder, Clear
        btn_row = ctk.CTkFrame(drop_frame, fg_color="transparent")
        btn_row.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="ew")
        btn_row.grid_columnconfigure((0, 1, 2), weight=1)

        add_files_btn = ctk.CTkButton(
            btn_row,
            text="+ Add Files",
            font=ctk.CTkFont(size=12),
            height=30,
            command=self.browse_files
        )
        add_files_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        add_folder_btn = ctk.CTkButton(
            btn_row,
            text="+ Add Folder",
            font=ctk.CTkFont(size=12),
            height=30,
            command=self.browse_folder
        )
        add_folder_btn.grid(row=0, column=1, padx=5, sticky="ew")

        self.clear_btn = ctk.CTkButton(
            btn_row,
            text="✕ Clear Queue",
            font=ctk.CTkFont(size=12),
            height=30,
            fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"),
            text_color=("black", "white"),
            command=self.clear_queue
        )
        self.clear_btn.grid(row=0, column=2, padx=(5, 0), sticky="ew")

        # ── 3. Queue List Frame ─────────────────────────────────────
        self.queue_frame = ctk.CTkFrame(self, corner_radius=12)
        self.queue_frame.grid(row=2, column=0, padx=15, pady=6, sticky="nsew")
        self.queue_frame.grid_columnconfigure(0, weight=1)

        # Queue header bar
        q_header = ctk.CTkFrame(self.queue_frame, fg_color="transparent")
        q_header.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="ew")
        q_header.grid_columnconfigure(0, weight=1)

        self.queue_title_lbl = ctk.CTkLabel(
            q_header,
            text="Queued Files (0)",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.queue_title_lbl.grid(row=0, column=0, sticky="w")

        self.queue_summary_lbl = ctk.CTkLabel(
            q_header,
            text="No files in queue",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.queue_summary_lbl.grid(row=0, column=1, sticky="e")

        # Scrollable items container
        self.items_container = ctk.CTkScrollableFrame(
            self.queue_frame,
            height=200,
            fg_color=("gray95", "gray14")
        )
        self.items_container.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="nsew")
        self.items_container.grid_columnconfigure(0, weight=1)

        self.empty_label = ctk.CTkLabel(
            self.items_container,
            text="Drag and drop audio/video files here to begin.",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.empty_label.grid(row=0, column=0, pady=40)

        # ── 4. Conversion Settings Card ─────────────────────────────
        settings_frame = ctk.CTkFrame(self, corner_radius=12)
        settings_frame.grid(row=3, column=0, padx=15, pady=6, sticky="ew")
        settings_frame.grid_columnconfigure(1, weight=1)

        st_title = ctk.CTkLabel(
            settings_frame,
            text="Conversion Settings",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        st_title.grid(row=0, column=0, columnspan=2, padx=15, pady=(10, 8), sticky="w")

        # Output Format Selector (Segmented Button)
        spec_lbl = ctk.CTkLabel(
            settings_frame,
            text="Output Format:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        spec_lbl.grid(row=1, column=0, padx=(15, 10), pady=(4, 2), sticky="nw")

        format_box = ctk.CTkFrame(settings_frame, fg_color="transparent")
        format_box.grid(row=1, column=1, padx=(0, 15), pady=(4, 2), sticky="w")

        self.format_var = ctk.StringVar(value="WAV (16 kHz)")
        self.format_segmented_btn = ctk.CTkSegmentedButton(
            format_box,
            values=["WAV (16 kHz)", "MP3 (Sharing)", "FLAC (Lossless)"],
            variable=self.format_var,
            command=self._on_format_changed,
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28
        )
        self.format_segmented_btn.grid(row=0, column=0, sticky="w")
        self.format_segmented_btn.set("WAV (16 kHz)")

        self.format_desc_lbl = ctk.CTkLabel(
            format_box,
            text="WAV (16-bit PCM Mono): Uncompressed standard for ELAN waveforms & ASR training.",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.format_desc_lbl.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # Dynamic Stereo Channels Checkbox
        ch_lbl = ctk.CTkLabel(
            settings_frame,
            text="Channel Mode:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        ch_lbl.grid(row=2, column=0, padx=(15, 10), pady=(8, 4), sticky="w")

        ch_box = ctk.CTkFrame(settings_frame, fg_color="transparent")
        ch_box.grid(row=2, column=1, padx=(0, 15), pady=(8, 4), sticky="w")

        self.split_channels_cb = ctk.CTkCheckBox(
            ch_box,
            text="Split 2-channel (stereo) files into separate mono tracks (_ch1.wav & _ch2.wav)",
            variable=self.split_channels_var,
            font=ctk.CTkFont(size=12),
            state="disabled"
        )
        self.split_channels_cb.grid(row=0, column=0, sticky="w")

        self.split_hint_lbl = ctk.CTkLabel(
            ch_box,
            text="(No 2-channel files in queue)",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.split_hint_lbl.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # Output folder selection
        dest_lbl = ctk.CTkLabel(
            settings_frame,
            text="Destination:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        dest_lbl.grid(row=3, column=0, padx=(15, 10), pady=(8, 12), sticky="nw")

        dest_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        dest_frame.grid(row=3, column=1, padx=(0, 15), pady=(8, 12), sticky="ew")
        dest_frame.grid_columnconfigure(1, weight=1)

        self.radio_source = ctk.CTkRadioButton(
            dest_frame,
            text="Save in the same folder as each source file",
            variable=self.output_dest_mode,
            value="source",
            font=ctk.CTkFont(size=12),
            command=self._on_dest_mode_changed
        )
        self.radio_source.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

        self.radio_custom = ctk.CTkRadioButton(
            dest_frame,
            text="Save to custom folder:",
            variable=self.output_dest_mode,
            value="custom",
            font=ctk.CTkFont(size=12),
            command=self._on_dest_mode_changed
        )
        self.radio_custom.grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.custom_dir_entry = ctk.CTkEntry(
            dest_frame,
            textvariable=self.custom_output_dir,
            font=ctk.CTkFont(size=11),
            height=28,
            state="disabled"
        )
        self.custom_dir_entry.grid(row=1, column=1, padx=(10, 6), sticky="ew")

        self.browse_dest_btn = ctk.CTkButton(
            dest_frame,
            text="Browse…",
            width=75,
            height=28,
            font=ctk.CTkFont(size=11),
            state="disabled",
            command=self._browse_custom_dir
        )
        self.browse_dest_btn.grid(row=1, column=2, sticky="e")

        # ── 5. Action & Progress Bar ────────────────────────────────
        action_frame = ctk.CTkFrame(self, corner_radius=12)
        action_frame.grid(row=4, column=0, padx=15, pady=(6, 20), sticky="ew")
        action_frame.grid_columnconfigure(0, weight=1)

        # Progress bar & status
        self.status_label = ctk.CTkLabel(
            action_frame,
            text="Add media files above to begin.",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.grid(row=0, column=0, padx=20, pady=(12, 4), sticky="w")

        self.progress_bar = ctk.CTkProgressBar(action_frame, height=10)
        self.progress_bar.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.progress_bar.set(0)

        # Buttons
        btn_bar = ctk.CTkFrame(action_frame, fg_color="transparent")
        btn_bar.grid(row=2, column=0, padx=20, pady=(0, 15), sticky="ew")
        btn_bar.grid_columnconfigure(0, weight=1)

        self.start_btn = ctk.CTkButton(
            btn_bar,
            text="🚀 Start Batch Conversion",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            height=40,
            command=self.start_conversion
        )
        self.start_btn.grid(row=0, column=0, padx=(0, 10), sticky="ew")

        self.cancel_btn = ctk.CTkButton(
            btn_bar,
            text="⏹ Cancel",
            font=ctk.CTkFont(size=12),
            fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"),
            text_color=("black", "white"),
            height=40,
            width=100,
            state="disabled",
            command=self.cancel_conversion
        )
        self.cancel_btn.grid(row=0, column=1, sticky="e")

    # ── File Picking & Queue Management ──────────────────────────────

    def _on_dnd_drop(self, event):
        """Handle files/folders dropped via Drag-and-Drop."""
        raw_data = event.data
        if not raw_data:
            return
        
        # Parse TkinterDnD drop string
        file_paths = []
        # Pattern handles space-separated paths and braced paths like {C:\My Files\audio.wav}
        pattern = re.compile(r'\{([^}]+)\}|(\S+)')
        for match in pattern.finditer(raw_data):
            p = match.group(1) or match.group(2)
            if p:
                file_paths.append(p)

        self._add_paths(file_paths)

    def browse_files(self):
        """Open file dialog to select audio/video files."""
        ext_list = [f"*{ext}" for ext in sorted(ALL_SUPPORTED_EXTENSIONS)]
        ext_filter = " ".join(ext_list)
        
        file_types = [
            ("Supported Media Files", ext_filter),
            ("Audio Files", " ".join(f"*{ext}" for ext in sorted(AUDIO_EXTENSIONS))),
            ("Video Files", " ".join(f"*{ext}" for ext in sorted(VIDEO_EXTENSIONS))),
            ("All Files", "*.*")
        ]
        
        selected = filedialog.askopenfilenames(
            title="Select Audio or Video Files",
            filetypes=file_types
        )
        if selected:
            self._add_paths(list(selected))

    def browse_folder(self):
        """Open directory dialog to scan and add all supported files inside."""
        folder = filedialog.askdirectory(title="Select Folder Containing Media Files")
        if folder:
            found = []
            folder_path = Path(folder)
            for p in folder_path.rglob("*"):
                if p.is_file() and is_supported_media_file(str(p)):
                    found.append(str(p))
            if found:
                self._add_paths(found)
            else:
                messagebox.showinfo("No Media Found", f"No supported audio or video files found in:\n{folder}")

    def _add_paths(self, paths: List[str]):
        """Probe and add valid media files to the queue in a background thread."""
        existing_paths = {item["file_path"] for item in self.queued_files}
        new_paths = []
        for p in paths:
            clean_p = str(Path(p).resolve())
            if os.path.isfile(clean_p) and is_supported_media_file(clean_p):
                if clean_p not in existing_paths:
                    new_paths.append(clean_p)

        if not new_paths:
            return

        self.status_label.configure(text=f"Probing {len(new_paths)} media file(s)...")

        def _worker():
            probed_items = []
            for p in new_paths:
                info = probe_media(p)
                info["status"] = "Ready"
                info["widget"] = None
                info["status_lbl"] = None
                probed_items.append(info)
            
            def _apply():
                self.queued_files.extend(probed_items)
                self._refresh_queue_ui()
                self._update_stereo_checkbox_state()
                self.status_label.configure(text=f"Added {len(probed_items)} file(s) to queue. Ready to convert.")
            
            self._safe_after(_apply)

        threading.Thread(target=_worker, daemon=True).start()

    def _safe_after(self, func):
        """Thread-safe dispatch to main UI loop with fallback."""
        try:
            self.after(0, func)
        except Exception:
            try:
                func()
            except Exception:
                pass

    def clear_queue(self):
        """Clear the queued files list."""
        if self.is_converting:
            return
        self.queued_files.clear()
        self._refresh_queue_ui()
        self._update_stereo_checkbox_state()
        self.status_label.configure(text="Queue cleared. Add files above to begin.")
        self.progress_bar.set(0)

    def _remove_item(self, index: int):
        """Remove a single item from the queue."""
        if self.is_converting:
            return
        if 0 <= index < len(self.queued_files):
            self.queued_files.pop(index)
            self._refresh_queue_ui()
            self._update_stereo_checkbox_state()

    def _update_stereo_checkbox_state(self):
        """Check if any 2-channel stereo file is in the queue and update the checkbox."""
        stereo_count = sum(1 for item in self.queued_files if item.get("channels") == 2)
        total_count = len(self.queued_files)

        if stereo_count > 0:
            self.split_channels_cb.configure(state="normal")
            self.split_hint_lbl.configure(
                text=f"✓ Detected {stereo_count} stereo (2-channel) file(s) in queue.",
                text_color=("#059669", "#34d399")
            )
        else:
            self.split_channels_var.set(False)
            self.split_channels_cb.configure(state="disabled")
            if total_count > 0:
                self.split_hint_lbl.configure(
                    text="(All queued files are mono or have no audio stream)",
                    text_color="gray"
                )
            else:
                self.split_hint_lbl.configure(
                    text="(No 2-channel files in queue)",
                    text_color="gray"
                )

    def _refresh_queue_ui(self):
        """Re-render the items container based on self.queued_files."""
        for widget in self.items_container.winfo_children():
            widget.destroy()

        if not self.queued_files:
            self.empty_label = ctk.CTkLabel(
                self.items_container,
                text="Drag and drop audio/video files here to begin.",
                font=ctk.CTkFont(size=12),
                text_color="gray"
            )
            self.empty_label.grid(row=0, column=0, pady=40)
            self.queue_title_lbl.configure(text="Queued Files (0)")
            self.queue_summary_lbl.configure(text="No files in queue")
            return

        total_files = len(self.queued_files)
        stereo_files = sum(1 for item in self.queued_files if item.get("channels") == 2)
        mono_files = sum(1 for item in self.queued_files if item.get("channels") == 1)
        total_dur = sum(item.get("duration", 0.0) for item in self.queued_files)

        self.queue_title_lbl.configure(text=f"Queued Files ({total_files})")
        summary_text = f"{stereo_files} stereo, {mono_files} mono"
        if total_dur > 0:
            summary_text += f" • Total Duration: {format_duration(total_dur)}"
        self.queue_summary_lbl.configure(text=summary_text)

        for idx, item in enumerate(self.queued_files):
            row_frame = ctk.CTkFrame(self.items_container, corner_radius=8, fg_color=("gray90", "gray18"))
            row_frame.grid(row=idx, column=0, padx=5, pady=3, sticky="ew")
            row_frame.grid_columnconfigure(1, weight=1)

            # Media type icon
            is_video = Path(item["file_path"]).suffix.lower() in VIDEO_EXTENSIONS
            icon_text = "🎬" if is_video else "🎵"
            icon_lbl = ctk.CTkLabel(row_frame, text=icon_text, font=ctk.CTkFont(size=16))
            icon_lbl.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=6)

            # Filename & parent directory
            name_box = ctk.CTkFrame(row_frame, fg_color="transparent")
            name_box.grid(row=0, column=1, rowspan=2, sticky="w", pady=4)

            name_lbl = ctk.CTkLabel(
                name_box,
                text=item["filename"],
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w"
            )
            name_lbl.grid(row=0, column=0, sticky="w")

            parent_folder = Path(item["file_path"]).parent.name
            size_str = format_size(item.get("size_bytes", 0))
            dur_str = format_duration(item.get("duration", 0.0))
            meta_lbl = ctk.CTkLabel(
                name_box,
                text=f"📁 {parent_folder}  •  {size_str}  •  {dur_str}",
                font=ctk.CTkFont(size=10),
                text_color="gray",
                anchor="w"
            )
            meta_lbl.grid(row=1, column=0, sticky="w")

            # Channel Badge
            channels = item.get("channels", 0)
            if channels == 2:
                badge_text = "Stereo (2ch)"
                badge_fg = ("#fef3c7", "#78350f")
                badge_tc = ("#b45309", "#fde68a")
            elif channels == 1:
                badge_text = "Mono (1ch)"
                badge_fg = ("#e0f2fe", "#1e3a5f")
                badge_tc = ("#0369a1", "#93c5fd")
            else:
                badge_text = "No Audio"
                badge_fg = ("#fee2e2", "#7f1d1d")
                badge_tc = ("#b91c1c", "#fca5a5")

            badge_lbl = ctk.CTkLabel(
                row_frame,
                text=badge_text,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=badge_fg,
                text_color=badge_tc,
                corner_radius=6,
                padx=8,
                pady=2
            )
            badge_lbl.grid(row=0, column=2, rowspan=2, padx=10)

            # Status Label
            status_text = item.get("status", "Ready")
            status_lbl = ctk.CTkLabel(
                row_frame,
                text=status_text,
                font=ctk.CTkFont(size=11),
                width=85
            )
            status_lbl.grid(row=0, column=3, rowspan=2, padx=(5, 5))
            item["status_lbl"] = status_lbl

            # Delete button
            del_btn = ctk.CTkButton(
                row_frame,
                text="✕",
                width=26,
                height=26,
                font=ctk.CTkFont(size=11),
                fg_color="transparent",
                hover_color=("gray80", "gray30"),
                text_color="gray",
                command=lambda i=idx: self._remove_item(i)
            )
            del_btn.grid(row=0, column=4, rowspan=2, padx=(0, 8))

    # ── Destination Mode Handling ────────────────────────────────────

    def _on_format_changed(self, value: str):
        """Update format description text when user changes format."""
        if "MP3" in value:
            self.format_desc_lbl.configure(
                text="MP3 (16 kHz Mono, 64 kbps): ~80% smaller file size! Perfect for sharing, mobile & email. Whisper compatible."
            )
        elif "FLAC" in value:
            self.format_desc_lbl.configure(
                text="FLAC (16 kHz Mono): Lossless compressed audio (~50% smaller than WAV, bit-for-bit exact)."
            )
        else:
            self.format_desc_lbl.configure(
                text="WAV (16-bit PCM Mono): Uncompressed standard for ELAN waveforms & ASR training."
            )

    def _on_dest_mode_changed(self):
        """Toggle custom directory entry enablement."""
        if self.output_dest_mode.get() == "custom":
            self.custom_dir_entry.configure(state="normal")
            self.browse_dest_btn.configure(state="normal")
        else:
            self.custom_dir_entry.configure(state="disabled")
            self.browse_dest_btn.configure(state="disabled")

    def _browse_custom_dir(self):
        """Pick custom output folder."""
        folder = filedialog.askdirectory(title="Select Output Folder for Converted Audio")
        if folder:
            self.custom_output_dir.set(folder)

    # ── Conversion Execution ─────────────────────────────────────────

    def start_conversion(self):
        """Start the batch conversion in a background worker thread."""
        if not self.queued_files:
            messagebox.showwarning("No Files", "Please add at least one audio or video file to convert.")
            return

        if self.output_dest_mode.get() == "custom":
            custom_dir = self.custom_output_dir.get().strip()
            if not custom_dir:
                messagebox.showwarning("Destination Needed", "Please select a custom output folder.")
                return
            if not os.path.exists(custom_dir):
                try:
                    os.makedirs(custom_dir, exist_ok=True)
                except Exception as e:
                    messagebox.showerror("Invalid Folder", f"Could not create output directory:\n{e}")
                    return

        # Determine target audio format
        format_choice = self.format_var.get()
        if "MP3" in format_choice:
            selected_fmt = "mp3"
        elif "FLAC" in format_choice:
            selected_fmt = "flac"
        else:
            selected_fmt = "wav"

        self.is_converting = True
        self.cancel_requested = False
        self.start_btn.configure(state="disabled", text="Converting...")
        self.cancel_btn.configure(state="normal")
        self.clear_btn.configure(state="disabled")
        self.progress_bar.set(0)

        split_channels = self.split_channels_var.get()
        target_output_dir = self.custom_output_dir.get().strip() if self.output_dest_mode.get() == "custom" else None

        def _worker():
            total = len(self.queued_files)
            success_count = 0
            error_count = 0
            all_generated = []

            for idx, item in enumerate(self.queued_files):
                if self.cancel_requested:
                    break

                file_path = item["file_path"]
                filename = item["filename"]

                # Update live status
                percent = idx / total
                self._update_progress_ui(
                    percent,
                    f"Processing ({idx + 1}/{total}): {filename}...",
                    idx,
                    "Converting..."
                )

                try:
                    gen_files = convert_media_file(
                        input_path=file_path,
                        output_dir=target_output_dir,
                        split_channels=split_channels,
                        output_format=selected_fmt
                    )
                    all_generated.extend(gen_files)
                    success_count += 1
                    self._update_item_status_ui(idx, "Done ✅", ("#059669", "#34d399"))
                except Exception as e:
                    error_count += 1
                    self._update_item_status_ui(idx, "Error ❌", ("#dc2626", "#f87171"))
                    print(f"Error converting {filename}: {e}")

            # Complete
            self._safe_after(lambda: self._on_conversion_finished(
                success_count, error_count, all_generated, self.cancel_requested
            ))

        threading.Thread(target=_worker, daemon=True).start()

    def _update_progress_ui(self, percent: float, message: str, item_idx: int, item_status: str):
        def _apply():
            self.progress_bar.set(percent)
            self.status_label.configure(text=message, text_color=("gray10", "gray90"))
            if 0 <= item_idx < len(self.queued_files):
                lbl = self.queued_files[item_idx].get("status_lbl")
                if lbl and lbl.winfo_exists():
                    lbl.configure(text=item_status, text_color=("gray10", "gray90"))
        self._safe_after(_apply)

    def _update_item_status_ui(self, item_idx: int, status_text: str, color=None):
        def _apply():
            if 0 <= item_idx < len(self.queued_files):
                self.queued_files[item_idx]["status"] = status_text
                lbl = self.queued_files[item_idx].get("status_lbl")
                if lbl and lbl.winfo_exists():
                    target_color = color if color is not None else ("gray10", "gray90")
                    lbl.configure(text=status_text, text_color=target_color)
        self._safe_after(_apply)

    def cancel_conversion(self):
        """Signal worker thread to halt after current file."""
        if self.is_converting:
            self.cancel_requested = True
            self.cancel_btn.configure(state="disabled", text="Stopping...")
            self.status_label.configure(text="Cancelling conversion after current file finishes...")

    def _on_conversion_finished(self, success: int, errors: int, outputs: List[str], cancelled: bool):
        """Called on main UI thread when batch is complete."""
        self.is_converting = False
        self.start_btn.configure(state="normal", text="🚀 Start Batch Conversion")
        self.cancel_btn.configure(state="disabled", text="⏹ Cancel")
        self.clear_btn.configure(state="normal")
        self.progress_bar.set(1.0 if not cancelled else self.progress_bar.get())

        if cancelled:
            msg = f"Conversion stopped. Processed {success} file(s)."
            self.status_label.configure(text=msg, text_color=("gray10", "gray90"))
            messagebox.showinfo("Cancelled", msg)
            return

        summary_msg = f"Completed batch conversion!\n\nSuccessfully converted: {success} file(s)"
        if errors > 0:
            summary_msg += f"\nFailed: {errors} file(s)"
        
        target_color = ("#059669", "#34d399") if errors == 0 else ("#dc2626", "#f87171")
        self.status_label.configure(
            text=f"Batch complete: {success} converted, {errors} errors.",
            text_color=target_color
        )

        # Ask to open output folder
        if outputs:
            first_out_dir = str(Path(outputs[0]).parent)
            if messagebox.askyesno("Conversion Complete", f"{summary_msg}\n\nWould you like to open the output folder?"):
                try:
                    if os.name == "nt":
                        os.startfile(first_out_dir)
                    elif sys.platform == "darwin":
                        import subprocess
                        subprocess.run(["open", first_out_dir])
                    else:
                        import subprocess
                        subprocess.run(["xdg-open", first_out_dir])
                except Exception as e:
                    print(f"Could not open directory: {e}")

    def _on_back_clicked(self):
        """Return to main launcher."""
        if self.is_converting:
            if not messagebox.askyesno("Conversion in Progress", "Conversion is currently running. Do you want to cancel and exit?"):
                return
            self.cancel_requested = True
        
        if self.back_callback:
            self.back_callback()
