"""
Silence Trimmer & VAD Cutter UI module for Easper.
Provides the SilenceTrimmerApp GUI for trimming dead air, condensing silences,
and slicing audio/video files into utterance chunks with CSV timestamps.
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
    format_duration,
    format_size,
    is_supported_media_file
)
from src.core.silence_cutter import (
    trim_edges,
    strip_all_silence
)

try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except Exception:
    HAS_DND = False
    DND_FILES = None


class SilenceTrimmerApp(ctk.CTkScrollableFrame):
    """
    CustomTkinter view for silence trimming and condensing.
    """
    def __init__(self, parent, back_callback=None):
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.back_callback = back_callback

        self.grid_columnconfigure(0, weight=1)

        # State
        self.queued_files: List[Dict[str, Any]] = []
        self.is_processing = False
        self.cancel_requested = False
        self.output_dest_mode = ctk.StringVar(value="source")  # "source" or "custom"
        self.custom_output_dir = ctk.StringVar(value="")

        # Operation mode: "edges", "strip"
        self.mode_var = ctk.StringVar(value="Trim Edges Only")

        # Thresholds
        self.threshold_var = ctk.StringVar(value="-40 dB (Normal)")
        self.min_silence_var = ctk.StringVar(value="0.8s")
        self.padding_var = ctk.StringVar(value="250 ms")
        self.format_var = ctk.StringVar(value="WAV (16 kHz Mono)")

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
            text="Silence Trimmer",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_lbl.grid(row=0, column=0, sticky="w")

        subtitle_lbl = ctk.CTkLabel(
            title_box,
            text="Trim start/end dead air or condense pauses across audio and video recordings",
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
            text="Supports audio (.wav, .mp3, .m4a, .flac, .ogg...) and video (.mp4, .mov, .mkv, .avi...)",
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
                print(f"DnD registration note in Silence Trimmer UI: {e}")

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

        self.items_container = ctk.CTkScrollableFrame(
            self.queue_frame,
            height=160,
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
        self.empty_label.grid(row=0, column=0, pady=30)

        # ── 4. Operation Mode & Settings Card ───────────────────────
        settings_frame = ctk.CTkFrame(self, corner_radius=12)
        settings_frame.grid(row=3, column=0, padx=15, pady=6, sticky="ew")
        settings_frame.grid_columnconfigure(1, weight=1)

        st_title = ctk.CTkLabel(
            settings_frame,
            text="Processing Options",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        st_title.grid(row=0, column=0, columnspan=2, padx=15, pady=(10, 6), sticky="w")

        # 1. Operation Mode
        mode_lbl = ctk.CTkLabel(
            settings_frame,
            text="Operation Mode:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        mode_lbl.grid(row=1, column=0, padx=(15, 10), pady=(4, 2), sticky="nw")

        mode_box = ctk.CTkFrame(settings_frame, fg_color="transparent")
        mode_box.grid(row=1, column=1, padx=(0, 15), pady=(4, 2), sticky="w")

        self.mode_btn = ctk.CTkSegmentedButton(
            mode_box,
            values=["Trim Edges Only", "Remove All Silences"],
            variable=self.mode_var,
            command=self._on_mode_changed,
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28
        )
        self.mode_btn.grid(row=0, column=0, sticky="w")
        self.mode_btn.set("Trim Edges Only")

        self.mode_desc_lbl = ctk.CTkLabel(
            mode_box,
            text="Strips start & end dead air. Interior speech and natural pauses remain 100% untouched.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=520,
            justify="left"
        )
        self.mode_desc_lbl.grid(row=1, column=0, sticky="w", pady=(2, 4))

        # 2. Silence Thresholds & Padding Controls
        params_row = ctk.CTkFrame(settings_frame, fg_color="transparent")
        params_row.grid(row=2, column=0, columnspan=2, padx=15, pady=(4, 6), sticky="ew")
        params_row.grid_columnconfigure((0, 1, 2), weight=1)

        # Threshold
        thresh_card = ctk.CTkFrame(params_row, fg_color=("gray90", "gray18"), corner_radius=8)
        thresh_card.grid(row=0, column=0, padx=(0, 5), pady=2, sticky="ew")
        ctk.CTkLabel(thresh_card, text="Silence Threshold", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=0, padx=10, pady=(6, 2), sticky="w")
        self.thresh_menu = ctk.CTkOptionMenu(
            thresh_card,
            values=["-30 dB (Aggressive)", "-35 dB", "-40 dB (Normal)", "-45 dB", "-50 dB (Quiet Room)"],
            variable=self.threshold_var,
            height=26,
            font=ctk.CTkFont(size=11)
        )
        self.thresh_menu.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")

        # Min Silence Duration
        dur_card = ctk.CTkFrame(params_row, fg_color=("gray90", "gray18"), corner_radius=8)
        dur_card.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
        ctk.CTkLabel(dur_card, text="Min Silence Gap", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=0, padx=10, pady=(6, 2), sticky="w")
        self.dur_menu = ctk.CTkOptionMenu(
            dur_card,
            values=["0.4s", "0.6s", "0.8s (Default)", "1.0s", "1.5s", "2.0s"],
            variable=self.min_silence_var,
            height=26,
            font=ctk.CTkFont(size=11)
        )
        self.dur_menu.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")

        # Padding Margin
        pad_card = ctk.CTkFrame(params_row, fg_color=("gray90", "gray18"), corner_radius=8)
        pad_card.grid(row=0, column=2, padx=(5, 0), pady=2, sticky="ew")
        ctk.CTkLabel(pad_card, text="Speech Padding Margin", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=0, padx=10, pady=(6, 2), sticky="w")
        self.pad_menu = ctk.CTkOptionMenu(
            pad_card,
            values=["100 ms", "200 ms", "250 ms (Default)", "350 ms", "500 ms"],
            variable=self.padding_var,
            height=26,
            font=ctk.CTkFont(size=11)
        )
        self.pad_menu.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")

        # 3. Output Format Selector
        fmt_lbl = ctk.CTkLabel(
            settings_frame,
            text="Output Format:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        fmt_lbl.grid(row=3, column=0, padx=(15, 10), pady=(6, 4), sticky="w")

        fmt_box = ctk.CTkFrame(settings_frame, fg_color="transparent")
        fmt_box.grid(row=3, column=1, padx=(0, 15), pady=(6, 4), sticky="w")

        self.fmt_btn = ctk.CTkSegmentedButton(
            fmt_box,
            values=["WAV (16 kHz Mono)", "MP3 (Compact Sharing)", "FLAC (Lossless)"],
            variable=self.format_var,
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28
        )
        self.fmt_btn.grid(row=0, column=0, sticky="w")
        self.fmt_btn.set("WAV (16 kHz Mono)")

        # 4. Destination Mode
        dest_lbl = ctk.CTkLabel(
            settings_frame,
            text="Destination:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        dest_lbl.grid(row=4, column=0, padx=(15, 10), pady=(6, 12), sticky="nw")

        dest_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        dest_frame.grid(row=4, column=1, padx=(0, 15), pady=(6, 12), sticky="ew")
        dest_frame.grid_columnconfigure(1, weight=1)

        self.radio_source = ctk.CTkRadioButton(
            dest_frame,
            text="Save alongside each source file",
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
        action_frame.grid(row=5, column=0, padx=15, pady=(6, 20), sticky="ew")
        action_frame.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            action_frame,
            text="Add media files above to begin.",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.grid(row=0, column=0, padx=20, pady=(12, 4), sticky="w")

        self.progress_bar = ctk.CTkProgressBar(action_frame, height=10)
        self.progress_bar.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.progress_bar.set(0)

        btn_bar = ctk.CTkFrame(action_frame, fg_color="transparent")
        btn_bar.grid(row=2, column=0, padx=20, pady=(0, 15), sticky="ew")
        btn_bar.grid_columnconfigure(0, weight=1)

        self.start_btn = ctk.CTkButton(
            btn_bar,
            text="🚀 Process Files",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            height=40,
            command=self.start_processing
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
            command=self.cancel_processing
        )
        self.cancel_btn.grid(row=0, column=1, sticky="e")

    # ── Helpers & Callbacks ──────────────────────────────────────────

    def _safe_after(self, func):
        """Thread-safe UI callback scheduling with fallback."""
        try:
            self.after(0, func)
        except Exception:
            try:
                func()
            except Exception:
                pass

    def _on_mode_changed(self, choice: str):
        if "Edges" in choice:
            self.mode_desc_lbl.configure(
                text="Strips start & end dead air. Interior speech and natural pauses remain 100% untouched."
            )
        else:
            self.mode_desc_lbl.configure(
                text="Removes silent gaps throughout the entire recording, producing a condensed speech file."
            )

    def _on_dest_mode_changed(self):
        if self.output_dest_mode.get() == "custom":
            self.custom_dir_entry.configure(state="normal")
            self.browse_dest_btn.configure(state="normal")
        else:
            self.custom_dir_entry.configure(state="disabled")
            self.browse_dest_btn.configure(state="disabled")

    def _browse_custom_dir(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.custom_output_dir.set(folder)

    # ── File Picking & Queue ─────────────────────────────────────────

    def _on_dnd_drop(self, event):
        raw_data = event.data
        if not raw_data:
            return
        file_paths = []
        pattern = re.compile(r'\{([^}]+)\}|(\S+)')
        for match in pattern.finditer(raw_data):
            p = match.group(1) or match.group(2)
            if p:
                file_paths.append(p)
        self._add_paths(file_paths)

    def browse_files(self):
        ext_list = [f"*{ext}" for ext in sorted(ALL_SUPPORTED_EXTENSIONS)]
        file_types = [
            ("Supported Media Files", " ".join(ext_list)),
            ("Audio Files", " ".join(f"*{ext}" for ext in sorted(AUDIO_EXTENSIONS))),
            ("Video Files", " ".join(f"*{ext}" for ext in sorted(VIDEO_EXTENSIONS))),
            ("All Files", "*.*")
        ]
        selected = filedialog.askopenfilenames(title="Select Media Files", filetypes=file_types)
        if selected:
            self._add_paths(list(selected))

    def browse_folder(self):
        folder = filedialog.askdirectory(title="Select Folder")
        if folder:
            found = []
            for p in Path(folder).rglob("*"):
                if p.is_file() and is_supported_media_file(str(p)):
                    found.append(str(p))
            if found:
                self._add_paths(found)
            else:
                messagebox.showinfo("No Media Found", f"No supported audio or video files found in:\n{folder}")

    def _add_paths(self, paths: List[str]):
        existing = {item["file_path"] for item in self.queued_files}
        new_paths = []
        for p in paths:
            clean_p = str(Path(p).resolve())
            if os.path.isfile(clean_p) and is_supported_media_file(clean_p):
                if clean_p not in existing:
                    new_paths.append(clean_p)

        if not new_paths:
            return

        self.status_label.configure(text=f"Probing {len(new_paths)} media file(s)...", text_color=("gray10", "gray90"))

        def _worker():
            probed_items = []
            for p in new_paths:
                info = probe_media(p)
                info["status"] = "Ready"
                info["status_lbl"] = None
                probed_items.append(info)

            def _apply():
                self.queued_files.extend(probed_items)
                self._refresh_queue_ui()
                self.status_label.configure(
                    text=f"Added {len(probed_items)} file(s) to queue. Ready to process.",
                    text_color=("gray10", "gray90")
                )

            self._safe_after(_apply)

        threading.Thread(target=_worker, daemon=True).start()

    def clear_queue(self):
        if self.is_processing:
            return
        self.queued_files.clear()
        self._refresh_queue_ui()
        self.status_label.configure(text="Queue cleared. Add files above to begin.", text_color=("gray10", "gray90"))
        self.progress_bar.set(0)

    def _remove_item(self, index: int):
        if self.is_processing:
            return
        if 0 <= index < len(self.queued_files):
            self.queued_files.pop(index)
            self._refresh_queue_ui()

    def _refresh_queue_ui(self):
        for widget in self.items_container.winfo_children():
            widget.destroy()

        if not self.queued_files:
            self.empty_label = ctk.CTkLabel(
                self.items_container,
                text="Drag and drop audio/video files here to begin.",
                font=ctk.CTkFont(size=12),
                text_color="gray"
            )
            self.empty_label.grid(row=0, column=0, pady=30)
            self.queue_title_lbl.configure(text="Queued Files (0)")
            self.queue_summary_lbl.configure(text="No files in queue")
            return

        total_files = len(self.queued_files)
        total_dur = sum(item.get("duration", 0.0) for item in self.queued_files)
        self.queue_title_lbl.configure(text=f"Queued Files ({total_files})")
        self.queue_summary_lbl.configure(text=f"Total Duration: {format_duration(total_dur)}")

        for idx, item in enumerate(self.queued_files):
            row_frame = ctk.CTkFrame(self.items_container, corner_radius=8, fg_color=("gray90", "gray18"))
            row_frame.grid(row=idx, column=0, padx=5, pady=3, sticky="ew")
            row_frame.grid_columnconfigure(1, weight=1)

            is_video = Path(item["file_path"]).suffix.lower() in VIDEO_EXTENSIONS
            icon_text = "🎬" if is_video else "🎵"
            icon_lbl = ctk.CTkLabel(row_frame, text=icon_text, font=ctk.CTkFont(size=16))
            icon_lbl.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=6)

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

            status_lbl = ctk.CTkLabel(
                row_frame,
                text=item.get("status", "Ready"),
                font=ctk.CTkFont(size=11),
                width=85
            )
            status_lbl.grid(row=0, column=2, rowspan=2, padx=10)
            item["status_lbl"] = status_lbl

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
            del_btn.grid(row=0, column=3, rowspan=2, padx=(0, 8))

    # ── Execution ────────────────────────────────────────────────────

    def start_processing(self):
        if not self.queued_files:
            messagebox.showwarning("No Files", "Please add at least one audio or video file to process.")
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

        # Parse threshold parameters
        try:
            # e.g. "-40 dB (Normal)" -> -40.0
            thresh_str = self.threshold_var.get().split()[0].replace("dB", "")
            noise_db = float(thresh_str)
        except Exception:
            noise_db = -40.0

        try:
            # e.g. "0.8s (Default)" -> 0.8
            dur_str = self.min_silence_var.get().split()[0].replace("s", "")
            min_silence = float(dur_str)
        except Exception:
            min_silence = 0.8

        try:
            # e.g. "250 ms (Default)" -> 0.25
            pad_str = self.padding_var.get().split()[0].replace("ms", "")
            padding_sec = float(pad_str) / 1000.0
        except Exception:
            padding_sec = 0.25

        # Format
        fmt_choice = self.format_var.get()
        if "MP3" in fmt_choice:
            output_format = "mp3"
        elif "FLAC" in fmt_choice:
            output_format = "flac"
        else:
            output_format = "wav"

        mode = self.mode_var.get()
        target_dir = self.custom_output_dir.get().strip() if self.output_dest_mode.get() == "custom" else None

        self.is_processing = True
        self.cancel_requested = False
        self.start_btn.configure(state="disabled", text="Processing...")
        self.cancel_btn.configure(state="normal")
        self.clear_btn.configure(state="disabled")
        self.progress_bar.set(0)

        def _worker():
            total = len(self.queued_files)
            success_count = 0
            error_count = 0
            all_outputs = []

            for idx, item in enumerate(self.queued_files):
                if self.cancel_requested:
                    break

                file_path = item["file_path"]
                filename = item["filename"]

                percent = idx / total
                self._update_progress_ui(
                    percent,
                    f"Processing ({idx + 1}/{total}): {filename}...",
                    idx,
                    "Running..."
                )

                try:
                    if "Edges" in mode:
                        res = trim_edges(
                            input_path=file_path,
                            output_dir=target_dir,
                            noise_threshold_db=noise_db,
                            min_silence_sec=min_silence,
                            padding_sec=padding_sec,
                            output_format=output_format
                        )
                    else:  # Remove All Silences
                        res = strip_all_silence(
                            input_path=file_path,
                            output_dir=target_dir,
                            noise_threshold_db=noise_db,
                            min_silence_sec=min_silence,
                            padding_sec=padding_sec,
                            output_format=output_format
                        )

                    out_files = res.get("output_files", [])
                    if res.get("status") == "no_speech":
                        self._update_item_status_ui(idx, "No Speech ⚠️", ("#d97706", "#f59e0b"))
                    elif out_files:
                        all_outputs.extend(out_files)
                        success_count += 1
                        self._update_item_status_ui(idx, "Done ✅", ("#059669", "#34d399"))
                    else:
                        error_count += 1
                        self._update_item_status_ui(idx, "Failed ❌", ("#dc2626", "#f87171"))

                except Exception as e:
                    error_count += 1
                    self._update_item_status_ui(idx, "Error ❌", ("#dc2626", "#f87171"))
                    print(f"Error processing {filename}: {e}")

            self._safe_after(lambda: self._on_processing_finished(
                success_count, error_count, all_outputs, self.cancel_requested
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

    def cancel_processing(self):
        if self.is_processing:
            self.cancel_requested = True
            self.cancel_btn.configure(state="disabled", text="Stopping...")
            self.status_label.configure(text="Cancelling processing after current file finishes...", text_color=("gray10", "gray90"))

    def _on_processing_finished(self, success: int, errors: int, outputs: List[str], cancelled: bool):
        self.is_processing = False
        self.start_btn.configure(state="normal", text="🚀 Process Files")
        self.cancel_btn.configure(state="disabled", text="⏹ Cancel")
        self.clear_btn.configure(state="normal")
        self.progress_bar.set(1.0 if not cancelled else self.progress_bar.get())

        if cancelled:
            msg = f"Processing stopped. Processed {success} file(s)."
            self.status_label.configure(text=msg, text_color=("gray10", "gray90"))
            messagebox.showinfo("Cancelled", msg)
            return

        target_color = ("#059669", "#34d399") if errors == 0 else ("#dc2626", "#f87171")
        self.status_label.configure(
            text=f"Processing complete: {success} successful, {errors} errors.",
            text_color=target_color
        )

        summary_msg = f"Processing finished!\n\nSuccessfully processed: {success} file(s)"
        if errors > 0:
            summary_msg += f"\nErrors: {errors} file(s)"

        if outputs:
            first_out_dir = str(Path(outputs[0]).parent)
            if messagebox.askyesno("Processing Complete", f"{summary_msg}\n\nWould you like to open the output folder?"):
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
        if self.is_processing:
            if not messagebox.askyesno("Task Running", "Processing is running. Do you want to cancel and leave?"):
                return
            self.cancel_requested = True
        if self.back_callback:
            self.back_callback()

