"""
Dataset UI module for Elan-ASR Pipeline.
Contains the ElanToASRApp class for the dataset generator GUI.
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk
import os
import re
from collections import Counter
import threading
import pympi
import webbrowser
try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except Exception:
    HAS_DND = False
    DND_FILES = None

from src.core.dataset import build_training_dataset, get_wav_file


class ElanToASRApp(ctk.CTkScrollableFrame):
    def __init__(self, parent, back_callback=None):
        super().__init__(parent, fg_color="transparent")
        
        self.parent = parent
        self.back_callback = back_callback

        # configure 1-column layout
        self.grid_columnconfigure(0, weight=1)

        self.selected_files = []
        self.train_folder = ""
        self.replacements_file = ""
        self.is_settings_expanded = True
        self.is_report_expanded = True

        # === Back Button (if callback provided)
        if back_callback:
            self.back_button = ctk.CTkButton(self, text="← Back to Menu", command=back_callback, width=120, fg_color="gray")
            self.back_button.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")

        # === Browse Button for ELAN files
        self.browse_files_button = ctk.CTkButton(
            self, text="📂  Drag & Drop or Click to Select ELAN (.eaf) Files…",
            command=self.browse_files,
            height=42, font=ctk.CTkFont(size=13, weight="bold")
        )
        self.browse_files_button.grid(row=1, column=0, padx=10, pady=(15, 4), sticky="ew")

        self.dnd_hint_label = ctk.CTkLabel(
            self, text="Drop .eaf files or a folder of ELAN files anywhere in the window",
            font=ctk.CTkFont(size=11), text_color="gray"
        )
        self.dnd_hint_label.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="ew")

        # Register Drag and Drop
        if HAS_DND:
            try:
                for widget in (self, self.browse_files_button, self.dnd_hint_label):
                    widget.drop_target_register(DND_FILES)
                    widget.dnd_bind('<<Drop>>', self._on_file_drop)
            except Exception as e:
                print(f"DnD registration note in Dataset UI: {e}")

        # === 1. Settings (Collapsible Card at Row 3)
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        self.settings_frame.grid_columnconfigure(0, weight=1)

        # Header for Collapsible Settings
        self.settings_header_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.settings_header_frame.grid(row=0, column=0, padx=10, pady=6, sticky="ew")
        self.settings_header_frame.grid_columnconfigure(0, weight=1)

        self.settings_header_title = ctk.CTkLabel(
            self.settings_header_frame, text="Tier Selection & Transcription Settings",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.settings_header_title.grid(row=0, column=0, sticky="w")

        self.settings_toggle_btn = ctk.CTkButton(
            self.settings_header_frame, text="Collapse Settings", width=140, height=26,
            font=ctk.CTkFont(size=11), fg_color=("gray75", "gray30"), hover_color=("gray65", "gray40"),
            text_color=("black", "white"), command=self.toggle_settings_collapse
        )
        self.settings_toggle_btn.grid(row=0, column=1, sticky="e")

        # Collapsible Content Frame
        self.settings_content_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.settings_content_frame.grid(row=1, column=0, padx=5, pady=(0, 6), sticky="ew")
        self.settings_content_frame.grid_columnconfigure(0, weight=1)

        # letters
        self.letters_label = ctk.CTkLabel(self.settings_content_frame, text="Allowed Letters in Transcriptions:")
        self.letters_label.grid(row=0, column=0, padx=10, pady=(5, 0), sticky="w")        
        self.letters_textbox = ctk.CTkTextbox(self.settings_content_frame, height=30)
        self.letters_textbox.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="ew")
        self.letters_textbox.insert("0.0", "abcdefghijklmnopqrstuvwxyz")
        # punctuation
        self.punctuation_label = ctk.CTkLabel(self.settings_content_frame, text="Allowed Punctuation Marks:")
        self.punctuation_label.grid(row=2, column=0, padx=10, pady=(5, 0), sticky="w")        
        self.punctuation_textbox = ctk.CTkTextbox(self.settings_content_frame, height=30)
        self.punctuation_textbox.grid(row=3, column=0, padx=10, pady=(0, 5), sticky="ew")
        self.punctuation_textbox.insert("0.0", '- . , ; : ! ? "')
        # Tier Selection & Search Toolbar Frame
        self.tier_tools_frame = ctk.CTkFrame(self.settings_content_frame, fg_color="transparent")
        self.tier_tools_frame.grid(row=4, column=0, padx=10, pady=(6, 2), sticky="ew")
        self.tier_tools_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.tier_tools_frame, text="Select by Tier Name:", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, padx=(0, 6), sticky="w"
        )
        self.tier_filter_entry = ctk.CTkEntry(
            self.tier_tools_frame, placeholder_text="Enter part of name (or leave empty for all)...",
            height=28
        )
        self.tier_filter_entry.grid(row=0, column=1, padx=(0, 6), sticky="ew")
        self.tier_filter_entry.bind("<KeyRelease>", self._update_tier_action_buttons)

        self.select_matching_btn = ctk.CTkButton(
            self.tier_tools_frame, text="Select All", width=125, height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.select_matching_tiers
        )
        self.select_matching_btn.grid(row=0, column=2, padx=(0, 4), sticky="e")

        self.deselect_matching_btn = ctk.CTkButton(
            self.tier_tools_frame, text="Deselect All", width=135, height=28,
            font=ctk.CTkFont(size=11),
            fg_color="gray", hover_color="#555",
            command=self.deselect_matching_tiers
        )
        self.deselect_matching_btn.grid(row=0, column=3, sticky="e")

        # tiers list placeholder
        self.tiers_frame = ctk.CTkScrollableFrame(self.settings_content_frame, label_text="Select Target Tiers:", height=200, border_width=1)
        self.tiers_frame.grid(row=5, column=0, padx=10, pady=5, sticky="nsew")
        
        self.tier_widgets = []
        self.tier_item_records = []

        # Main Button to Start Checking
        self.check_button = ctk.CTkButton(self.settings_content_frame, text="Check!", command=self.start_checking, fg_color="green")
        self.check_button.grid(row=6, column=0, padx=10, pady=8, sticky="n")
        
        self.settings_frame.grid_remove()

        # === 2. Issues and Reports (Interactive Tabbed Interface at Row 4)
        self.report_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=("#e0f2fe", "#0f2744"))
        self.report_frame.grid(row=4, column=0, padx=10, pady=5, sticky="nsew")
        self.report_frame.grid_columnconfigure(0, weight=1)
        self.report_frame.grid_rowconfigure(0, weight=0)
        self.report_frame.grid_rowconfigure(1, weight=1)

        # Header for Collapsible Report Frame
        self.report_header_frame = ctk.CTkFrame(self.report_frame, fg_color="transparent")
        self.report_header_frame.grid(row=0, column=0, padx=12, pady=6, sticky="ew")
        self.report_header_frame.grid_columnconfigure(0, weight=1)

        self.report_header_title = ctk.CTkLabel(
            self.report_header_frame, text="Validation Issues & Reports",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.report_header_title.grid(row=0, column=0, sticky="w")

        self.report_toggle_btn = ctk.CTkButton(
            self.report_header_frame, text="Collapse Reports", width=140, height=26,
            font=ctk.CTkFont(size=11), fg_color=("gray75", "gray30"), hover_color=("gray65", "gray40"),
            text_color=("black", "white"), command=self.toggle_report_collapse
        )
        self.report_toggle_btn.grid(row=0, column=1, sticky="e")

        self.report_content_frame = ctk.CTkFrame(self.report_frame, fg_color="transparent")
        self.report_content_frame.grid(row=1, column=0, padx=0, pady=(0, 6), sticky="nsew")
        self.report_content_frame.grid_columnconfigure(0, weight=1)
        self.report_content_frame.grid_rowconfigure(0, weight=0)
        self.report_content_frame.grid_rowconfigure(1, weight=1)

        self._create_interactive_tabs()
        self.report_frame.grid_remove()

        # === 3. Dataset settings (at Row 5)
        self.dataset_settings_frame = ctk.CTkFrame(self, corner_radius=10)
        self.dataset_settings_frame.grid(row=5, column=0, padx=10, pady=5, sticky="ew")
        self.dataset_settings_frame.grid_columnconfigure(0, weight=1)

        # Header
        self.dataset_settings_header = ctk.CTkLabel(
            self.dataset_settings_frame, text="Dataset Output & Build",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.dataset_settings_header.grid(row=0, column=0, padx=15, pady=(12, 8), sticky="w")

        # Destination Folder Row
        self.folder_box = ctk.CTkFrame(self.dataset_settings_frame, fg_color="transparent")
        self.folder_box.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="ew")
        self.folder_box.grid_columnconfigure(0, weight=1)

        self.train_folder_label = ctk.CTkLabel(
            self.folder_box, text="Output Destination Folder:",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.train_folder_label.grid(row=0, column=0, sticky="w", pady=(0, 2), columnspan=2)

        self.train_folder_entry = ctk.CTkEntry(
            self.folder_box, placeholder_text="Select destination folder...", height=32
        )
        self.train_folder_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))

        self.browse_train_folder_button = ctk.CTkButton(
            self.folder_box, text="📂 Browse Folder", width=135, height=32,
            font=ctk.CTkFont(size=11, weight="bold"), command=self.select_train_folder
        )
        self.browse_train_folder_button.grid(row=1, column=1, sticky="e")

        # Find and Replace Row (Optional)
        self.replacements_box = ctk.CTkFrame(self.dataset_settings_frame, fg_color="transparent")
        self.replacements_box.grid(row=2, column=0, padx=15, pady=(0, 12), sticky="ew")
        self.replacements_box.grid_columnconfigure(0, weight=1)

        self.replacements_label = ctk.CTkLabel(
            self.replacements_box, text="Find & Replace Normalization File (Optional):",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.replacements_label.grid(row=0, column=0, sticky="w", pady=(0, 2), columnspan=3)

        self.replacements_entry = ctk.CTkEntry(
            self.replacements_box, placeholder_text="No find & replace file selected (.tsv, .txt)...", height=32
        )
        self.replacements_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))

        self.browse_replacements_button = ctk.CTkButton(
            self.replacements_box, text="📄 Select File…", width=120, height=32,
            font=ctk.CTkFont(size=11), command=self.select_replacements_file
        )
        self.browse_replacements_button.grid(row=1, column=1, sticky="e", padx=(0, 6))

        self.clear_replacements_button = ctk.CTkButton(
            self.replacements_box, text="✕ Clear", width=70, height=32,
            font=ctk.CTkFont(size=11), fg_color=("gray75", "gray35"), hover_color=("gray65", "gray45"),
            text_color=("black", "white"), command=self.clear_replacements_file
        )
        self.clear_replacements_button.grid(row=1, column=2, sticky="e")

        # Button to Build Training Dataset
        self.build_train_button = ctk.CTkButton(
            self.dataset_settings_frame, text="Build Training Dataset (ZIP)", height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=("#16a34a", "#22c55e"), hover_color=("#15803d", "#16a34a"),
            text_color="white", command=self.build_train_set
        )
        self.build_train_button.grid(row=3, column=0, padx=15, pady=(0, 8), sticky="ew")

        # Green Success Box below build button
        self.build_success_card = ctk.CTkFrame(
            self.dataset_settings_frame, fg_color=("#dcfce7", "#064e3b"),
            border_width=1, border_color=("#86efac", "#15803d"), corner_radius=10
        )
        self.build_success_card.grid(row=4, column=0, padx=15, pady=(4, 12), sticky="ew")
        self.build_success_card.grid_columnconfigure(0, weight=1)

        self.build_success_title = ctk.CTkLabel(
            self.build_success_card, text="Training Dataset Built Successfully!",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=("#15803d", "#86efac")
        )
        self.build_success_title.grid(row=0, column=0, padx=15, pady=(12, 6), sticky="w")

        # File Path and Open Folder button
        self.succ_path_frame = ctk.CTkFrame(self.build_success_card, fg_color="transparent")
        self.succ_path_frame.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="ew")
        self.succ_path_frame.grid_columnconfigure(0, weight=1)

        self.build_success_path_lbl = ctk.CTkLabel(
            self.succ_path_frame, text="",
            font=ctk.CTkFont(size=12), text_color=("#166534", "#bbf7d0"),
            wraplength=600, justify="left"
        )
        self.build_success_path_lbl.grid(row=0, column=0, sticky="w")

        self.open_folder_btn = ctk.CTkButton(
            self.succ_path_frame, text="Open Folder", width=110, height=28,
            font=ctk.CTkFont(size=11, weight="bold"), fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"), text_color=("black", "white"),
            command=self.open_output_folder
        )
        self.open_folder_btn.grid(row=0, column=1, sticky="e", padx=(8, 0))

        # Next Steps Section
        # Step 1: Google Drive upload
        self.succ_step1_frame = ctk.CTkFrame(self.build_success_card, fg_color="transparent")
        self.succ_step1_frame.grid(row=2, column=0, padx=15, pady=(0, 8), sticky="ew")
        self.succ_step1_frame.grid_columnconfigure(0, weight=1)

        self.step1_lbl = ctk.CTkLabel(
            self.succ_step1_frame,
            text='1. Upload the zipped dataset file into the "Colab" folder in your Google Drive:',
            font=ctk.CTkFont(size=12, weight="bold"), text_color=("#15803d", "#86efac"),
            wraplength=650, justify="left"
        )
        self.step1_lbl.grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.btn_open_drive = ctk.CTkButton(
            self.succ_step1_frame, text="Open Google Drive (drive.google.com)",
            font=ctk.CTkFont(size=12, weight="bold"), height=32,
            fg_color=("#0284c7", "#0369a1"), hover_color=("#0369a1", "#075985"),
            text_color="white", command=self.open_google_drive
        )
        self.btn_open_drive.grid(row=1, column=0, sticky="w")

        # Step 2: Google Colab training notebook
        self.succ_step2_frame = ctk.CTkFrame(self.build_success_card, fg_color="transparent")
        self.succ_step2_frame.grid(row=3, column=0, padx=15, pady=(0, 14), sticky="ew")
        self.succ_step2_frame.grid_columnconfigure(0, weight=1)

        self.step2_lbl = ctk.CTkLabel(
            self.succ_step2_frame,
            text='2. Run the Speech Recognition Training notebook on Google Colab:',
            font=ctk.CTkFont(size=12, weight="bold"), text_color=("#15803d", "#86efac"),
            wraplength=650, justify="left"
        )
        self.step2_lbl.grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.btn_open_colab = ctk.CTkButton(
            self.succ_step2_frame, text="Open Training Colab Notebook",
            font=ctk.CTkFont(size=12, weight="bold"), height=32,
            fg_color=("#ea580c", "#c2410c"), hover_color=("#c2410c", "#9a3412"),
            text_color="white", command=self.open_training_colab
        )
        self.btn_open_colab.grid(row=1, column=0, sticky="w")

        self.build_success_card.grid_remove()

        # Progress bar & status
        self.progress_box = ctk.CTkFrame(self.dataset_settings_frame, fg_color="transparent")
        self.progress_box.grid(row=5, column=0, padx=15, pady=(0, 14), sticky="ew")
        self.progress_box.grid_columnconfigure(0, weight=1)

        self.progress_status_label = ctk.CTkLabel(
            self.progress_box, text="Ready to build dataset.",
            font=ctk.CTkFont(size=11), text_color=("gray40", "gray60")
        )
        self.progress_status_label.grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.progress_bar = ctk.CTkProgressBar(
            self.progress_box, height=10, progress_color=("#16a34a", "#22c55e")
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew")
        self.progress_bar.set(0)

        self.dataset_settings_frame.grid_remove()
        
    #========================
    def _on_file_drop(self, event):
        """Handle files or folders dropped onto the Dataset Generator UI."""
        if not event.data:
            return
        try:
            raw_paths = self.tk.splitlist(event.data)
            collected_eaf_files = []
            replacements_file = None

            for path in raw_paths:
                p = path.strip()
                if os.path.isfile(p):
                    if p.lower().endswith(".eaf"):
                        collected_eaf_files.append(p)
                    elif p.lower().endswith((".tsv", ".txt")):
                        replacements_file = p
                elif os.path.isdir(p):
                    for root, _, files in os.walk(p):
                        for f in sorted(files):
                            if f.lower().endswith(".eaf"):
                                collected_eaf_files.append(os.path.join(root, f))

            if replacements_file:
                self.set_replacements_file(replacements_file)

            if collected_eaf_files:
                self.load_elan_files(collected_eaf_files)
            elif not replacements_file:
                messagebox.showwarning(
                    "Unsupported File Format",
                    "Please drop ELAN (.eaf) files or a folder containing .eaf files."
                )
        except Exception as e:
            messagebox.showerror("Drag & Drop Error", f"Could not process dropped files: {e}")

    def toggle_settings_collapse(self):
        """Toggle collapsing/expanding the tier selection settings frame."""
        if getattr(self, "is_settings_expanded", True):
            self.collapse_settings()
        else:
            self.expand_settings()

    def collapse_settings(self):
        """Collapse the tier selection settings frame."""
        self.settings_content_frame.grid_remove()
        count = len(self.selected_files)
        files_str = f" ({count} file{'s' if count != 1 else ''} loaded)" if count else ""
        self.settings_toggle_btn.configure(text=f"Expand Settings{files_str}")
        self.is_settings_expanded = False

    def expand_settings(self):
        """Expand the tier selection settings frame."""
        self.settings_content_frame.grid()
        self.settings_toggle_btn.configure(text="Collapse Settings")
        self.is_settings_expanded = True

    def toggle_report_collapse(self):
        """Toggle collapsing/expanding the validation reports frame."""
        if getattr(self, "is_report_expanded", True):
            self.collapse_report()
        else:
            self.expand_report()

    def collapse_report(self):
        """Collapse the validation reports frame."""
        self.report_content_frame.grid_remove()
        self.report_toggle_btn.configure(text="Expand Reports")
        self.is_report_expanded = False

    def expand_report(self):
        """Expand the validation reports frame."""
        self.report_content_frame.grid()
        self.report_toggle_btn.configure(text="Collapse Reports")
        self.is_report_expanded = True

    def load_elan_files(self, filenames):
        """Load and display tiers from selected or dropped ELAN files, verifying audio files exist."""
        if not filenames:
            return
        import pympi
        seen = set()
        unique_files = [f for f in filenames if not (f in seen or seen.add(f))]
        
        # Verify matching audio file existence for every ELAN file
        valid_files = []
        missing_audio_files = []
        for file_path in unique_files:
            wav_path = get_wav_file(file_path)
            if wav_path and os.path.exists(wav_path):
                valid_files.append(file_path)
            else:
                missing_audio_files.append(os.path.basename(file_path))

        # Show warning if any ELAN file lacks a matching audio file
        if missing_audio_files:
            file_list_str = "\n".join(f"• {f}" for f in missing_audio_files)
            messagebox.showwarning(
                "Missing Audio File(s)",
                f"The following ELAN file(s) do not have a matching audio (.wav) file and were dismissed from the dataset:\n\n{file_list_str}\n\nPlease ensure each .eaf file has a corresponding audio file in the same folder."
            )

        if not valid_files:
            # If no valid files remain, clear tier widgets and remove settings frame
            self.selected_files = []
            for widget in self.tier_widgets:
                widget.destroy()
            self.tier_widgets = []
            self.tier_vars = {}
            self.settings_frame.grid_remove()
            return

        self.selected_files = valid_files
        self.set_train_folder(os.path.dirname(valid_files[0]))
        self.settings_frame.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        self.expand_settings()
        count = len(self.selected_files)
        self.settings_header_title.configure(text=f"Target Tiers & Settings ({count} ELAN file{'s' if count != 1 else ''} loaded)")

        # Clear existing widgets
        for widget in self.tier_widgets:
            widget.destroy()
        self.tier_widgets = []
        self.tier_vars = {}
        row_idx = 0
        
        # Punctuation to exclude when auto-detecting allowed letters
        punct_text = self.punctuation_textbox.get("0.0", "end").strip()
        punct_set = set(list(punct_text) + list('-.,;:!?"') + ['\t', '\n', '\r', ' '])
        extracted_chars = set()

        for file_path in self.selected_files:
            basename = os.path.basename(file_path)
            try:
                eaf = pympi.Elan.Eaf(file_path)

                file_lbl = ctk.CTkLabel(self.tiers_frame, text=basename, font=ctk.CTkFont(weight="bold"))
                file_lbl.grid(row=row_idx, column=0, padx=10, pady=(5, 0), sticky="w", columnspan=20)
                self.tier_widgets.append(file_lbl)
                row_idx += 1
                
                self.tier_vars[file_path] = {}
                
                for tier in eaf.get_tier_names():
                    annotations = eaf.get_annotation_data_for_tier(tier)
                    count = len(annotations)
                    if count == 0:
                        continue
                    
                    for ann in annotations:
                        text = ann[2] if len(ann) >= 3 else ""
                        for ch in text:
                            if ch not in punct_set:
                                extracted_chars.add(ch)

                    display_text = f"{tier} ({count} annotations)"
                    var = ctk.StringVar(value="")
                    chk = ctk.CTkCheckBox(self.tiers_frame, text=display_text, variable=var, onvalue=tier, offvalue="")
                    chk.grid(row=row_idx, column=0, padx=5, pady=2, sticky="w")
                    row_idx += 1
                    self.tier_widgets.append(chk)
                    
                    self.tier_vars[file_path][tier] = var
                
                row_idx += 1

            except Exception as e:
                print(f"Error processing {basename}: {e}")

        # Auto-populate letters_textbox with sorted extracted characters
        if extracted_chars:
            sorted_letters = " ".join(sorted(list(extracted_chars)))
            self.letters_textbox.delete("0.0", "end")
            self.letters_textbox.insert("0.0", sorted_letters)

        self._update_tier_action_buttons()

    def _update_tier_action_buttons(self, event=None):
        """Update button labels dynamically based on whether the search textbox has content."""
        pattern = self.tier_filter_entry.get().strip()
        if pattern:
            self.select_matching_btn.configure(text="Select Matching")
            self.deselect_matching_btn.configure(text="Deselect Matching")
        else:
            self.select_matching_btn.configure(text="Select All")
            self.deselect_matching_btn.configure(text="Deselect All")

    def select_matching_tiers(self):
        """Select tiers matching filter query, or select all if filter is empty."""
        pattern = self.tier_filter_entry.get().strip().lower()
        for file_path, tiers in getattr(self, "tier_vars", {}).items():
            for tier, var in tiers.items():
                if not pattern or pattern in tier.lower():
                    var.set(tier)

    def deselect_matching_tiers(self):
        """Deselect tiers matching filter query, or deselect all if filter is empty."""
        pattern = self.tier_filter_entry.get().strip().lower()
        for file_path, tiers in getattr(self, "tier_vars", {}).items():
            for tier, var in tiers.items():
                if not pattern or pattern in tier.lower():
                    var.set("")

    def browse_files(self):
        filetypes = (('ELAN files', '*.eaf'), ('All files', '*.*'))
        filenames = filedialog.askopenfilenames(title="Select ELAN files", filetypes=filetypes)
        if filenames:
            self.load_elan_files(filenames)

    def _create_interactive_tabs(self):
        """Construct interactive table views with two button navigation sets (Issues & Reports)."""
        self._treeview_style = ttk.Style()
        self._treeview_style.theme_use("default")
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg_col = "#1e293b" if is_dark else "#f8fafc"
        fg_col = "#f1f5f9" if is_dark else "#0f172a"
        hdr_bg = "#334155" if is_dark else "#e2e8f0"
        hdr_fg = "#ffffff" if is_dark else "#1e293b"

        self._treeview_style.configure(
            "Dataset.Treeview",
            background=bg_col,
            foreground=fg_col,
            fieldbackground=bg_col,
            rowheight=26,
            font=("Segoe UI", 11)
        )
        self._treeview_style.configure(
            "Dataset.Treeview.Heading",
            background=hdr_bg,
            foreground=hdr_fg,
            font=("Segoe UI", 11, "bold"),
            relief="flat"
        )
        self._treeview_style.map("Dataset.Treeview", background=[("selected", "#2563eb")])

        # ── Navigation Header (Two Button Groups) ─────────────────────
        self.nav_frame = ctk.CTkFrame(self.report_content_frame, fg_color="transparent")
        self.nav_frame.grid(row=0, column=0, padx=12, pady=(4, 6), sticky="ew")
        self.nav_frame.grid_columnconfigure(0, weight=1)

        # 1. Issues Row (Red buttons)
        self.issues_row = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
        self.issues_row.grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.lbl_issues_header = ctk.CTkLabel(
            self.issues_row, text="Issues:", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#dc2626", "#f87171")
        )
        self.lbl_issues_header.pack(side="left", padx=(0, 6))

        self.btn_not_allowed = ctk.CTkButton(
            self.issues_row, text="Disallowed Chars", fg_color="#dc2626", hover_color="#b91c1c",
            font=ctk.CTkFont(size=11, weight="bold"), height=28, command=lambda: self.switch_view("not allowed chars")
        )
        self.btn_long_segments = ctk.CTkButton(
            self.issues_row, text="Long Segments", fg_color="#dc2626", hover_color="#b91c1c",
            font=ctk.CTkFont(size=11, weight="bold"), height=28, command=lambda: self.switch_view("long segments")
        )
        self.btn_overlaps = ctk.CTkButton(
            self.issues_row, text="Overlaps", fg_color="#dc2626", hover_color="#b91c1c",
            font=ctk.CTkFont(size=11, weight="bold"), height=28, command=lambda: self.switch_view("overlaps")
        )
        self.lbl_no_issues = ctk.CTkLabel(
            self.issues_row, text="No issues found", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("#16a34a", "#4ade80")
        )
        self.lbl_no_issues.pack(side="left", padx=(0, 6))

        # 2. Reports Row
        self.reports_row = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
        self.reports_row.grid(row=1, column=0, sticky="w", pady=(0, 2))

        self.lbl_reports_header = ctk.CTkLabel(
            self.reports_row, text="Reports:", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#0284c7", "#38bdf8")
        )
        self.lbl_reports_header.pack(side="left", padx=(0, 6))

        self.btn_chars = ctk.CTkButton(
            self.reports_row, text="Characters", fg_color="#2563eb", hover_color="#1d4ed8",
            font=ctk.CTkFont(size=11, weight="bold"), height=28, command=lambda: self.switch_view("chars")
        )
        self.btn_chars.pack(side="left", padx=(0, 6))

        self.btn_bigrams = ctk.CTkButton(
            self.reports_row, text="Bigrams", fg_color="#2563eb", hover_color="#1d4ed8",
            font=ctk.CTkFont(size=11, weight="bold"), height=28, command=lambda: self.switch_view("bigrams")
        )
        self.btn_bigrams.pack(side="left", padx=(0, 6))

        self.btn_words = ctk.CTkButton(
            self.reports_row, text="Words", fg_color="#2563eb", hover_color="#1d4ed8",
            font=ctk.CTkFont(size=11, weight="bold"), height=28, command=lambda: self.switch_view("words")
        )
        self.btn_words.pack(side="left", padx=(0, 6))

        self.btn_assessment = ctk.CTkButton(
            self.reports_row, text="Assessment", fg_color="#7c3aed", hover_color="#6d28d9",
            font=ctk.CTkFont(size=11, weight="bold"), height=28, command=lambda: self.switch_view("assessment")
        )
        self.btn_assessment.pack(side="left", padx=(0, 6))

        # ── Views Content Container ──────────────────────────────────
        self.views_container = ctk.CTkFrame(self.report_content_frame, fg_color="transparent")
        self.views_container.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="nsew")
        self.views_container.grid_columnconfigure(0, weight=1)
        self.views_container.grid_rowconfigure(0, weight=1)

        self.views = {}
        self.tab_banners = {}
        self.tab_raw_records = {}
        self.current_view_name = "not allowed chars"

        # ── 1. View: Disallowed Characters ───────────────────────────
        t_not_allowed = ctk.CTkFrame(self.views_container, fg_color="transparent")
        t_not_allowed.grid_columnconfigure(0, weight=1)
        t_not_allowed.grid_rowconfigure(1, weight=1)
        self.views["not allowed chars"] = t_not_allowed

        self.tab_banners["not allowed chars"] = ctk.CTkLabel(
            t_not_allowed, text="Click 'Check!' to scan for disallowed characters.",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray30", "gray70")
        )
        self.tab_banners["not allowed chars"].grid(row=0, column=0, padx=8, pady=(4, 4), sticky="w")

        _na_frame = ctk.CTkFrame(t_not_allowed, fg_color="transparent")
        _na_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)
        _na_frame.grid_columnconfigure(0, weight=1)
        _na_frame.grid_rowconfigure(0, weight=1)

        cols_na = [('file', 'File', 140), ('char', 'Char', 60), ('hex', 'Unicode', 85), ('count', 'Count', 65), ('tiers', 'Tier(s)', 180)]
        self.not_allowed_tv = ttk.Treeview(_na_frame, columns=[c[0] for c in cols_na], show="headings", style="Dataset.Treeview", height=8)
        for cid, cname, cwidth in cols_na:
            self.not_allowed_tv.heading(cid, text=cname, command=lambda c=cid: self._sort_treeview_column(self.not_allowed_tv, c, False))
            self.not_allowed_tv.column(cid, width=cwidth, anchor="center" if cid in ('char', 'hex', 'count') else "w")
        
        na_scroll_y = ttk.Scrollbar(_na_frame, orient="vertical", command=self.not_allowed_tv.yview)
        self.not_allowed_tv.configure(yscrollcommand=na_scroll_y.set)
        self.not_allowed_tv.grid(row=0, column=0, sticky="nsew")
        na_scroll_y.grid(row=0, column=1, sticky="ns")

        # Click-to-Highlight Inspector
        self.not_allowed_inspector = ctk.CTkFrame(t_not_allowed, corner_radius=8)
        self.not_allowed_inspector.grid(row=2, column=0, sticky="ew", padx=4, pady=(6, 4))
        self.not_allowed_inspector.grid_columnconfigure(1, weight=1)

        self.na_insp_title = ctk.CTkLabel(
            self.not_allowed_inspector, text="Click any row above to inspect disallowed character details",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.na_insp_title.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="w")

        self.na_copy_btn = ctk.CTkButton(
            self.not_allowed_inspector, text="Copy Char", width=105, height=24,
            font=ctk.CTkFont(size=11), command=self._copy_na_char
        )
        self.na_copy_btn.grid(row=0, column=1, padx=10, pady=(6, 2), sticky="e")

        self.na_insp_detail = ctk.CTkLabel(
            self.not_allowed_inspector, text="No issue selected.",
            font=ctk.CTkFont(size=11), text_color=("gray20", "gray85"), wraplength=480, justify="left"
        )
        self.na_insp_detail.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="w")
        self.not_allowed_tv.bind("<<TreeviewSelect>>", self._on_select_not_allowed)


        # ── 2. View: Long Segments (>25s) ────────────────────────────
        t_long = ctk.CTkFrame(self.views_container, fg_color="transparent")
        t_long.grid_columnconfigure(0, weight=1)
        t_long.grid_rowconfigure(1, weight=1)
        self.views["long segments"] = t_long

        self.tab_banners["long segments"] = ctk.CTkLabel(
            t_long, text="Click 'Check!' to find speech segments longer than 25 seconds.",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray30", "gray70")
        )
        self.tab_banners["long segments"].grid(row=0, column=0, padx=8, pady=(4, 4), sticky="w")

        _long_frame = ctk.CTkFrame(t_long, fg_color="transparent")
        _long_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)
        _long_frame.grid_columnconfigure(0, weight=1)
        _long_frame.grid_rowconfigure(0, weight=1)

        cols_long = [('file', 'File', 130), ('tier', 'Tier', 110), ('start', 'Start', 85), ('end', 'End', 85), ('dur', 'Duration', 75), ('text', 'Text Preview', 200)]
        self.long_segments_tv = ttk.Treeview(_long_frame, columns=[c[0] for c in cols_long], show="headings", style="Dataset.Treeview", height=8)
        for cid, cname, cwidth in cols_long:
            self.long_segments_tv.heading(cid, text=cname, command=lambda c=cid: self._sort_treeview_column(self.long_segments_tv, c, False))
            self.long_segments_tv.column(cid, width=cwidth, anchor="center" if cid in ('start', 'end', 'dur') else "w")
        
        long_scroll_y = ttk.Scrollbar(_long_frame, orient="vertical", command=self.long_segments_tv.yview)
        self.long_segments_tv.configure(yscrollcommand=long_scroll_y.set)
        self.long_segments_tv.grid(row=0, column=0, sticky="nsew")
        long_scroll_y.grid(row=0, column=1, sticky="ns")

        # Long Segments Inspector
        self.long_inspector = ctk.CTkFrame(t_long, corner_radius=8)
        self.long_inspector.grid(row=2, column=0, sticky="ew", padx=4, pady=(6, 4))
        self.long_inspector.grid_columnconfigure(1, weight=1)

        self.long_insp_title = ctk.CTkLabel(
            self.long_inspector, text="Click any long segment above to view exact ELAN timecode and full text",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.long_insp_title.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="w")

        self.long_copy_btn = ctk.CTkButton(
            self.long_inspector, text="Copy Timecode", width=125, height=24,
            font=ctk.CTkFont(size=11), command=self._copy_long_timecode
        )
        self.long_copy_btn.grid(row=0, column=1, padx=10, pady=(6, 2), sticky="e")

        self.long_insp_detail = ctk.CTkLabel(
            self.long_inspector, text="No long segment selected.",
            font=ctk.CTkFont(size=11), text_color=("gray20", "gray85"), wraplength=480, justify="left"
        )
        self.long_insp_detail.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="w")
        self.long_segments_tv.bind("<<TreeviewSelect>>", self._on_select_long_segment)


        # ── 3. View: Overlapping Segments ────────────────────────────
        t_overlaps = ctk.CTkFrame(self.views_container, fg_color="transparent")
        t_overlaps.grid_columnconfigure(0, weight=1)
        t_overlaps.grid_rowconfigure(1, weight=1)
        self.views["overlaps"] = t_overlaps

        self.tab_banners["overlaps"] = ctk.CTkLabel(
            t_overlaps, text="Click 'Check!' to detect overlapping speaker segments (>400ms).",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray30", "gray70")
        )
        self.tab_banners["overlaps"].grid(row=0, column=0, padx=8, pady=(4, 4), sticky="w")

        _ol_frame = ctk.CTkFrame(t_overlaps, fg_color="transparent")
        _ol_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)
        _ol_frame.grid_columnconfigure(0, weight=1)
        _ol_frame.grid_rowconfigure(0, weight=1)

        cols_ol = [('file', 'File', 150), ('tier1', 'Tier 1', 50), ('time1', 'Time 1', 135), ('tier2', 'Tier 2', 50), ('time2', 'Time 2', 135), ('dur', 'Overlap', 40)]
        self.overlaps_tv = ttk.Treeview(_ol_frame, columns=[c[0] for c in cols_ol], show="headings", style="Dataset.Treeview", height=8)
        for cid, cname, cwidth in cols_ol:
            self.overlaps_tv.heading(cid, text=cname, command=lambda c=cid: self._sort_treeview_column(self.overlaps_tv, c, False))
            self.overlaps_tv.column(cid, width=cwidth, anchor="center" if cid in ('time1', 'time2', 'dur') else "w")
        
        ol_scroll_y = ttk.Scrollbar(_ol_frame, orient="vertical", command=self.overlaps_tv.yview)
        self.overlaps_tv.configure(yscrollcommand=ol_scroll_y.set)
        self.overlaps_tv.grid(row=0, column=0, sticky="nsew")
        ol_scroll_y.grid(row=0, column=1, sticky="ns")

        # Overlaps Inspector
        self.overlaps_inspector = ctk.CTkFrame(t_overlaps, corner_radius=8)
        self.overlaps_inspector.grid(row=2, column=0, sticky="ew", padx=4, pady=(6, 4))
        self.overlaps_inspector.grid_columnconfigure(1, weight=1)

        self.ol_insp_title = ctk.CTkLabel(
            self.overlaps_inspector, text="Click any overlap above to compare overlapping tiers",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.ol_insp_title.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="w")

        self.ol_copy_btn = ctk.CTkButton(
            self.overlaps_inspector, text="Copy Overlap Time", width=145, height=24,
            font=ctk.CTkFont(size=11), command=self._copy_overlap_timecode
        )
        self.ol_copy_btn.grid(row=0, column=1, padx=10, pady=(6, 2), sticky="e")

        self.ol_insp_detail = ctk.CTkLabel(
            self.overlaps_inspector, text="No overlapping segment selected.",
            font=ctk.CTkFont(size=11), text_color=("gray20", "gray85"), wraplength=480, justify="left"
        )
        self.ol_insp_detail.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="w")
        self.overlaps_tv.bind("<<TreeviewSelect>>", self._on_select_overlap)


        # ── 4. View: Assessment ──────────────────────────────────────
        t_assessment = ctk.CTkFrame(self.views_container, fg_color="transparent")
        t_assessment.grid_columnconfigure(0, weight=1)
        t_assessment.grid_rowconfigure(1, weight=1)
        self.views["assessment"] = t_assessment

        _ass_top = ctk.CTkFrame(t_assessment, fg_color="transparent")
        _ass_top.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 2))
        _ass_top.grid_columnconfigure(1, weight=1)

        self.tab_banners["assessment"] = ctk.CTkLabel(
            _ass_top, text="Dataset Assessment per ELAN file",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray30", "gray70")
        )
        self.tab_banners["assessment"].grid(row=0, column=0, sticky="w", padx=(0, 10))

        _ass_actions = ctk.CTkFrame(_ass_top, fg_color="transparent")
        _ass_actions.grid(row=0, column=1, sticky="e")

        self.assessment_search_entry = ctk.CTkEntry(
            _ass_actions, placeholder_text="Search file...", height=26, width=150, border_width=0
        )
        self.assessment_search_entry.pack(side="left", padx=(0, 6))
        self.assessment_search_entry.bind("<KeyRelease>", lambda e: self._filter_assessment_table())

        self.export_assessment_btn = ctk.CTkButton(
            _ass_actions, text="Export", width=80, height=26,
            font=ctk.CTkFont(size=11, weight="bold"), fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"), text_color=("black", "white"),
            command=self.export_assessment_report
        )
        self.export_assessment_btn.pack(side="left")

        _ass_frame = ctk.CTkFrame(t_assessment, fg_color="transparent")
        _ass_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)
        _ass_frame.grid_columnconfigure(0, weight=1)
        _ass_frame.grid_rowconfigure(0, weight=1)

        cols_ass = [
            ('rank', '#', 40),
            ('file', 'File', 180),
            ('segments', 'Segments', 75),
            ('duration', 'Total Duration', 110),
            ('tokens', 'Tokens', 70),
            ('types', 'Types', 65),
            ('ttr', 'Type-Token Ratio', 130),
            ('nttr', 'Normalised Token to Type', 160)
        ]
        self.assessment_tv = ttk.Treeview(_ass_frame, columns=[c[0] for c in cols_ass], show="headings", style="Dataset.Treeview", height=12)
        for cid, cname, cwidth in cols_ass:
            self.assessment_tv.heading(cid, text=cname, command=lambda c=cid: self._sort_treeview_column(self.assessment_tv, c, False))
            self.assessment_tv.column(cid, width=cwidth, anchor="center" if cid != 'file' else "w")
        
        ass_scroll_y = ttk.Scrollbar(_ass_frame, orient="vertical", command=self.assessment_tv.yview)
        self.assessment_tv.configure(yscrollcommand=ass_scroll_y.set)
        self.assessment_tv.grid(row=0, column=0, sticky="nsew")
        ass_scroll_y.grid(row=0, column=1, sticky="ns")

        # ── 5. View: Characters ──────────────────────────────────────
        t_chars = ctk.CTkFrame(self.views_container, fg_color="transparent")
        t_chars.grid_columnconfigure(0, weight=1)
        t_chars.grid_rowconfigure(1, weight=1)
        self.views["chars"] = t_chars

        _char_top = ctk.CTkFrame(t_chars, fg_color="transparent")
        _char_top.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 2))
        _char_top.grid_columnconfigure(1, weight=1)

        self.tab_banners["chars"] = ctk.CTkLabel(
            _char_top, text="Character frequency distribution",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray30", "gray70")
        )
        self.tab_banners["chars"].grid(row=0, column=0, sticky="w", padx=(0, 10))

        _char_actions = ctk.CTkFrame(_char_top, fg_color="transparent")
        _char_actions.grid(row=0, column=1, sticky="e")

        self.char_search_entry = ctk.CTkEntry(
            _char_actions, placeholder_text="Search char...", height=26, width=150, border_width=0
        )
        self.char_search_entry.pack(side="left", padx=(0, 6))
        self.char_search_entry.bind("<KeyRelease>", lambda e: self._filter_chars_table())

        self.export_chars_btn = ctk.CTkButton(
            _char_actions, text="Export", width=80, height=26,
            font=ctk.CTkFont(size=11, weight="bold"), fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"), text_color=("black", "white"),
            command=self.export_chars_report
        )
        self.export_chars_btn.pack(side="left")

        _char_frame = ctk.CTkFrame(t_chars, fg_color="transparent")
        _char_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)
        _char_frame.grid_columnconfigure(0, weight=1)
        _char_frame.grid_rowconfigure(0, weight=1)

        cols_ch = [('rank', '#', 45), ('char', 'Character', 80), ('hex', 'Unicode', 85), ('count', 'Count', 75), ('pct', 'Percentage', 95)]
        self.chars_tv = ttk.Treeview(_char_frame, columns=[c[0] for c in cols_ch], show="headings", style="Dataset.Treeview", height=12)
        for cid, cname, cwidth in cols_ch:
            self.chars_tv.heading(cid, text=cname, command=lambda c=cid: self._sort_treeview_column(self.chars_tv, c, False))
            self.chars_tv.column(cid, width=cwidth, anchor="center")
        
        ch_scroll_y = ttk.Scrollbar(_char_frame, orient="vertical", command=self.chars_tv.yview)
        self.chars_tv.configure(yscrollcommand=ch_scroll_y.set)
        self.chars_tv.grid(row=0, column=0, sticky="nsew")
        ch_scroll_y.grid(row=0, column=1, sticky="ns")

        # ── 6. View: Character Bigrams ───────────────────────────────
        t_bigrams = ctk.CTkFrame(self.views_container, fg_color="transparent")
        t_bigrams.grid_columnconfigure(0, weight=1)
        t_bigrams.grid_rowconfigure(1, weight=1)
        self.views["bigrams"] = t_bigrams

        _bg_top = ctk.CTkFrame(t_bigrams, fg_color="transparent")
        _bg_top.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 2))
        _bg_top.grid_columnconfigure(1, weight=1)

        self.tab_banners["bigrams"] = ctk.CTkLabel(
            _bg_top, text="Character bigram frequency distribution",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray30", "gray70")
        )
        self.tab_banners["bigrams"].grid(row=0, column=0, sticky="w", padx=(0, 10))

        _bg_actions = ctk.CTkFrame(_bg_top, fg_color="transparent")
        _bg_actions.grid(row=0, column=1, sticky="e")

        self.bigram_search_entry = ctk.CTkEntry(
            _bg_actions, placeholder_text="Search bigram...", height=26, width=150, border_width=0
        )
        self.bigram_search_entry.pack(side="left", padx=(0, 6))
        self.bigram_search_entry.bind("<KeyRelease>", lambda e: self._filter_bigrams_table())

        self.export_bigrams_btn = ctk.CTkButton(
            _bg_actions, text="Export", width=80, height=26,
            font=ctk.CTkFont(size=11, weight="bold"), fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"), text_color=("black", "white"),
            command=self.export_bigrams_report
        )
        self.export_bigrams_btn.pack(side="left")

        _bg_frame = ctk.CTkFrame(t_bigrams, fg_color="transparent")
        _bg_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)
        _bg_frame.grid_columnconfigure(0, weight=1)
        _bg_frame.grid_rowconfigure(0, weight=1)

        cols_bg = [('rank', '#', 45), ('bigram', 'Bigram', 120), ('count', 'Count', 75), ('pct', 'Percentage', 95)]
        self.bigrams_tv = ttk.Treeview(_bg_frame, columns=[c[0] for c in cols_bg], show="headings", style="Dataset.Treeview", height=12)
        for cid, cname, cwidth in cols_bg:
            self.bigrams_tv.heading(cid, text=cname, command=lambda c=cid: self._sort_treeview_column(self.bigrams_tv, c, False))
            self.bigrams_tv.column(cid, width=cwidth, anchor="center")

        bg_scroll_y = ttk.Scrollbar(_bg_frame, orient="vertical", command=self.bigrams_tv.yview)
        self.bigrams_tv.configure(yscrollcommand=bg_scroll_y.set)
        self.bigrams_tv.grid(row=0, column=0, sticky="nsew")
        bg_scroll_y.grid(row=0, column=1, sticky="ns")

        # ── 7. View: Words ───────────────────────────────────────────
        t_words = ctk.CTkFrame(self.views_container, fg_color="transparent")
        t_words.grid_columnconfigure(0, weight=1)
        t_words.grid_rowconfigure(1, weight=1)
        self.views["words"] = t_words

        _w_top = ctk.CTkFrame(t_words, fg_color="transparent")
        _w_top.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 2))
        _w_top.grid_columnconfigure(1, weight=1)

        self.tab_banners["words"] = ctk.CTkLabel(
            _w_top, text="Word frequency vocabulary",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray30", "gray70")
        )
        self.tab_banners["words"].grid(row=0, column=0, sticky="w", padx=(0, 10))

        _w_actions = ctk.CTkFrame(_w_top, fg_color="transparent")
        _w_actions.grid(row=0, column=1, sticky="e")

        self.word_search_entry = ctk.CTkEntry(
            _w_actions, placeholder_text="Search word...", height=26, width=150, border_width=0
        )
        self.word_search_entry.pack(side="left", padx=(0, 6))
        self.word_search_entry.bind("<KeyRelease>", lambda e: self._filter_words_table())

        self.export_words_btn = ctk.CTkButton(
            _w_actions, text="Export", width=80, height=26,
            font=ctk.CTkFont(size=11, weight="bold"), fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"), text_color=("black", "white"),
            command=self.export_words_report
        )
        self.export_words_btn.pack(side="left")

        _w_frame = ctk.CTkFrame(t_words, fg_color="transparent")
        _w_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)
        _w_frame.grid_columnconfigure(0, weight=1)
        _w_frame.grid_rowconfigure(0, weight=1)

        cols_w = [('rank', '#', 45), ('word', 'Word', 160), ('count', 'Count', 75), ('pct', 'Percentage', 95), ('len', 'Length', 65)]
        self.words_tv = ttk.Treeview(_w_frame, columns=[c[0] for c in cols_w], show="headings", style="Dataset.Treeview", height=12)
        for cid, cname, cwidth in cols_w:
            self.words_tv.heading(cid, text=cname, command=lambda c=cid: self._sort_treeview_column(self.words_tv, c, False))
            self.words_tv.column(cid, width=cwidth, anchor="center" if cid in ('rank', 'count', 'pct', 'len') else "w")
        
        w_scroll_y = ttk.Scrollbar(_w_frame, orient="vertical", command=self.words_tv.yview)
        self.words_tv.configure(yscrollcommand=w_scroll_y.set)
        self.words_tv.grid(row=0, column=0, sticky="nsew")
        w_scroll_y.grid(row=0, column=1, sticky="ns")

        # Show initial default view
        self.switch_view("not allowed chars")

    def switch_view(self, view_name):
        """Switch active view and update button highlight states."""
        self.current_view_name = view_name
        for name, frame in self.views.items():
            if name == view_name:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_remove()

        # Update button active state styling
        buttons_map = {
            "not allowed chars": (self.btn_not_allowed, "issue"),
            "long segments": (self.btn_long_segments, "issue"),
            "overlaps": (self.btn_overlaps, "issue"),
            "assessment": (self.btn_assessment, "report"),
            "chars": (self.btn_chars, "report"),
            "bigrams": (self.btn_bigrams, "report"),
            "words": (self.btn_words, "report"),
        }

        for v_name, (btn, b_type) in buttons_map.items():
            is_active = (v_name == view_name)
            if b_type == "issue":
                if is_active:
                    btn.configure(fg_color="#991b1b", border_width=2, border_color="#fca5a5")
                else:
                    btn.configure(fg_color="#dc2626", border_width=0)
            else:
                if is_active:
                    act_color = "#6d28d9" if v_name == "assessment" else "#1d4ed8"
                    border_col = "#c4b5fd" if v_name == "assessment" else "#93c5fd"
                    btn.configure(fg_color=act_color, border_width=2, border_color=border_col)
                else:
                    norm_color = "#7c3aed" if v_name == "assessment" else "#2563eb"
                    btn.configure(fg_color=norm_color, border_width=0)

    def _sort_treeview_column(self, tv, col, reverse):
        """Sort treeview items when column header is clicked."""
        l = [(tv.set(k, col), k) for k in tv.get_children('')]
        try:
            def _num_key(t):
                s = str(t[0]).replace('s', '').replace('%', '').replace('#', '').replace('ms', '').replace('∑', '').strip()
                if '(' in s and ')' in s:
                    s = s.split('(')[-1].replace(')', '').replace('s', '').strip()
                return float(s)
            l.sort(key=_num_key, reverse=reverse)
        except Exception:
            l.sort(key=lambda t: str(t[0]).lower(), reverse=reverse)

        for index, (val, k) in enumerate(l):
            tv.move(k, '', index)

        tv.heading(col, command=lambda: self._sort_treeview_column(tv, col, not reverse))

    def _on_select_not_allowed(self, event):
        sel = self.not_allowed_tv.selection()
        if not sel:
            return
        vals = self.not_allowed_tv.item(sel[0], 'values')
        if not vals:
            return
        file_name, char_val, hex_val, count_val, tiers_val = vals
        record = self.tab_raw_records.get("not_allowed", {}).get(sel[0], {})
        sample_text = record.get("sample", "")
        self.na_insp_title.configure(text=f"Flagged Character '{char_val}' ({hex_val}) in {file_name}")
        self.na_insp_detail.configure(
            text=f"• Count: {count_val} occurrences across tier(s): {tiers_val}\n• Sample Occurrence: \"{sample_text}\""
        )
        self._selected_na_char = char_val

    def _copy_na_char(self):
        char_val = getattr(self, "_selected_na_char", None)
        if char_val:
            self._copy_to_clipboard(char_val, self.na_copy_btn, "Copied!")

    def _on_select_long_segment(self, event):
        sel = self.long_segments_tv.selection()
        if not sel:
            return
        vals = self.long_segments_tv.item(sel[0], 'values')
        if not vals:
            return
        file_name, tier, start, end, dur, text_preview = vals
        record = self.tab_raw_records.get("long_segments", {}).get(sel[0], {})
        full_text = record.get("full_text", text_preview)
        s_ms = record.get("start_ms", 0)
        e_ms = record.get("end_ms", 0)
        self.long_insp_title.configure(text=f"{file_name} -> [{tier}] ({dur})")
        self.long_insp_detail.configure(
            text=f"• Timecode: {self.format_time_ms_precise(s_ms)} --> {self.format_time_ms_precise(e_ms)}\n• Text: \"{full_text}\""
        )
        self._selected_long_timecode = f"{self.format_time_ms_precise(s_ms)} - {self.format_time_ms_precise(e_ms)}"

    def _copy_long_timecode(self):
        tc = getattr(self, "_selected_long_timecode", None)
        if tc:
            self._copy_to_clipboard(tc, self.long_copy_btn, "Copied!")

    def _on_select_overlap(self, event):
        sel = self.overlaps_tv.selection()
        if not sel:
            return
        vals = self.overlaps_tv.item(sel[0], 'values')
        if not vals:
            return
        file_name, tier1, time1, tier2, time2, dur = vals
        record = self.tab_raw_records.get("overlaps", {}).get(sel[0], {})
        t1_text = record.get("text1", "")
        t2_text = record.get("text2", "")
        ol_start_ms = record.get("overlap_start_ms", 0)
        ol_start_str = record.get("overlap_start", self.ms_to_hh_mm_ss(ol_start_ms))
        self.ol_insp_title.configure(text=f"Overlap in {file_name} ({dur})")
        self.ol_insp_detail.configure(
            text=f"• Overlap Start: {ol_start_str} ({self.format_time_ms_precise(ol_start_ms)})\n• Tier 1 [{tier1}] ({time1}): \"{t1_text}\"\n• Tier 2 [{tier2}] ({time2}): \"{t2_text}\""
        )
        self._selected_overlap_timecode = ol_start_str

    def _copy_overlap_timecode(self):
        tc = getattr(self, "_selected_overlap_timecode", None)
        if tc:
            self._copy_to_clipboard(tc, self.ol_copy_btn, "Copied!")

    def _copy_to_clipboard(self, text, button_widget=None, feedback_text="Copied!"):
        """Helper to copy text to clipboard and give visual feedback."""
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            if button_widget:
                orig_text = button_widget.cget("text")
                button_widget.configure(text=feedback_text)
                self.after(1500, lambda: button_widget.configure(text=orig_text))
        except Exception as e:
            print(f"Clipboard copy error: {e}")

    def format_time_ms_precise(self, milliseconds):
        """Format milliseconds into HH:MM:SS.mmm string."""
        total_seconds = int(milliseconds) // 1000
        ms = int(milliseconds) % 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"

    def ms_to_hh_mm_ss(self, milliseconds):
        """Convert milliseconds to HH:MM:SS format string."""
        total_seconds = int(milliseconds) // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _filter_assessment_table(self):
        """Filter assessment treeview based on search entry."""
        query = self.assessment_search_entry.get().strip().lower()
        records = getattr(self, "_all_assessment_records", [])
        for item in self.assessment_tv.get_children():
            self.assessment_tv.delete(item)
        for r in records:
            if not query or query in r['file'].lower() or r.get('is_summary', False):
                self.assessment_tv.insert('', 'end', values=(
                    r['rank'], r['file'], r['segments'], r['duration'],
                    r['tokens'], r['types'], r['ttr'], r['nttr']
                ))

    def export_assessment_report(self):
        """Export Assessment report as TSV/CSV."""
        records = getattr(self, "_all_assessment_records", [])
        if not records:
            messagebox.showinfo("Export", "No assessment records to export.")
            return
        filename = filedialog.asksaveasfilename(
            title="Export Assessment Report",
            defaultextension=".tsv",
            initialfile="dataset_assessment.tsv",
            filetypes=[("TSV file", "*.tsv"), ("CSV file", "*.csv"), ("Text file", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            delimiter = "," if filename.endswith(".csv") else "\t"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"Rank{delimiter}File{delimiter}Segments{delimiter}Total_Duration_Sec{delimiter}Tokens{delimiter}Types{delimiter}Type_Token_Ratio{delimiter}Normalised_Token_to_Type\n")
                for r in records:
                    f.write(f"{r['rank']}{delimiter}{r['file']}{delimiter}{r['segments']}{delimiter}{r.get('duration_sec', 0):.2f}{delimiter}{r['tokens']}{delimiter}{r['types']}{delimiter}{r['ttr']}{delimiter}{r['nttr']}\n")
            messagebox.showinfo("Export Success", f"Assessment report exported successfully:\n{filename}")

    def _filter_chars_table(self):
        """Filter characters treeview based on search entry."""
        query = self.char_search_entry.get().strip().lower()
        records = getattr(self, "_all_char_records", [])
        for item in self.chars_tv.get_children():
            self.chars_tv.delete(item)
        for r in records:
            if not query or query in r['char'].lower() or query in r['hex'].lower():
                self.chars_tv.insert('', 'end', values=(r['rank'], r['char'], r['hex'], r['count'], r['pct']))

    def _filter_bigrams_table(self):
        """Filter bigrams treeview based on search entry."""
        query = self.bigram_search_entry.get().strip().lower()
        records = getattr(self, "_all_bigram_records", [])
        for item in self.bigrams_tv.get_children():
            self.bigrams_tv.delete(item)
        for r in records:
            if not query or query in r['bigram'].lower():
                self.bigrams_tv.insert('', 'end', values=(r['rank'], r['bigram'], r['count'], r['pct']))

    def _filter_words_table(self):
        """Filter words treeview based on search entry."""
        query = self.word_search_entry.get().strip().lower()
        records = getattr(self, "_all_word_records", [])
        for item in self.words_tv.get_children():
            self.words_tv.delete(item)
        for r in records:
            if not query or query in r['word'].lower():
                self.words_tv.insert('', 'end', values=(r['rank'], r['word'], r['count'], r['pct'], r['len']))

    def export_chars_report(self):
        """Export Character frequencies report as TSV/CSV."""
        records = getattr(self, "_all_char_records", [])
        if not records:
            messagebox.showinfo("Export", "No character records to export.")
            return
        filename = filedialog.asksaveasfilename(
            title="Export Character Frequencies",
            defaultextension=".tsv",
            initialfile="character_frequencies.tsv",
            filetypes=[("TSV file", "*.tsv"), ("CSV file", "*.csv"), ("Text file", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            delimiter = "," if filename.endswith(".csv") else "\t"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"Rank{delimiter}Character{delimiter}Unicode{delimiter}Count{delimiter}Percentage\n")
                for r in records:
                    f.write(f"{r['rank']}{delimiter}{r['char']}{delimiter}{r['hex']}{delimiter}{r['count']}{delimiter}{r['pct']}\n")
            messagebox.showinfo("Export Success", f"Character report exported successfully:\n{filename}")

    def export_bigrams_report(self):
        """Export Bigram frequencies report as TSV/CSV."""
        records = getattr(self, "_all_bigram_records", [])
        if not records:
            messagebox.showinfo("Export", "No bigram records to export.")
            return
        filename = filedialog.asksaveasfilename(
            title="Export Bigram Frequencies",
            defaultextension=".tsv",
            initialfile="bigram_frequencies.tsv",
            filetypes=[("TSV file", "*.tsv"), ("CSV file", "*.csv"), ("Text file", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            delimiter = "," if filename.endswith(".csv") else "\t"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"Rank{delimiter}Bigram{delimiter}Count{delimiter}Percentage\n")
                for r in records:
                    f.write(f"{r['rank']}{delimiter}{r['bigram']}{delimiter}{r['count']}{delimiter}{r['pct']}\n")
            messagebox.showinfo("Export Success", f"Bigram report exported successfully:\n{filename}")

    def export_words_report(self):
        """Export Word frequencies report as TSV/CSV."""
        records = getattr(self, "_all_word_records", [])
        if not records:
            messagebox.showinfo("Export", "No word records to export.")
            return
        filename = filedialog.asksaveasfilename(
            title="Export Word Frequencies",
            defaultextension=".tsv",
            initialfile="word_frequencies.tsv",
            filetypes=[("TSV file", "*.tsv"), ("CSV file", "*.csv"), ("Text file", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            delimiter = "," if filename.endswith(".csv") else "\t"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"Rank{delimiter}Word{delimiter}Count{delimiter}Percentage{delimiter}Length\n")
                for r in records:
                    f.write(f"{r['rank']}{delimiter}{r['word']}{delimiter}{r['count']}{delimiter}{r['pct']}{delimiter}{r['len']}\n")
            messagebox.showinfo("Export Success", f"Word report exported successfully:\n{filename}")

    def _populate_interactive_reports(self, na_records, long_records, overlap_records, assessment_records, char_records, bigram_records, word_records):
        """Populate all interactive Treeviews, inspector cards, and button badges."""
        # 1. Disallowed Chars
        for item in self.not_allowed_tv.get_children():
            self.not_allowed_tv.delete(item)
        self.tab_raw_records["not_allowed"] = {}
        for idx, r in enumerate(na_records):
            iid = f"na_{idx}"
            self.not_allowed_tv.insert('', 'end', iid=iid, values=(r['file'], r['char'], r['hex'], r['count'], r['tiers']))
            self.tab_raw_records["not_allowed"][iid] = r

        if na_records:
            self.btn_not_allowed.configure(text=f"Disallowed Chars ({len(na_records)})")
            self.btn_not_allowed.pack(side="left", padx=(0, 6))
            self.tab_banners["not allowed chars"].configure(
                text=f"{len(na_records)} Disallowed Character issue(s) flagged",
                text_color=("#b45309", "#fbbf24")
            )
            self.not_allowed_tv.selection_set("na_0")
            self._on_select_not_allowed(None)
        else:
            self.btn_not_allowed.pack_forget()
            self.tab_banners["not allowed chars"].configure(
                text="No disallowed characters found.",
                text_color=("#15803d", "#4ade80")
            )
            self.na_insp_title.configure(text="All characters match the allowed letter & punctuation set.")
            self.na_insp_detail.configure(text="")

        # 2. Long Segments
        for item in self.long_segments_tv.get_children():
            self.long_segments_tv.delete(item)
        self.tab_raw_records["long_segments"] = {}
        for idx, r in enumerate(long_records):
            iid = f"long_{idx}"
            self.long_segments_tv.insert('', 'end', iid=iid, values=(r['file'], r['tier'], r['start'], r['end'], r['dur'], r['preview']))
            self.tab_raw_records["long_segments"][iid] = r

        if long_records:
            self.btn_long_segments.configure(text=f"Long Segments ({len(long_records)})")
            self.btn_long_segments.pack(side="left", padx=(0, 6))
            self.tab_banners["long segments"].configure(
                text=f"{len(long_records)} Speech Segment(s) exceed 25 seconds",
                text_color=("#b45309", "#fbbf24")
            )
            self.long_segments_tv.selection_set("long_0")
            self._on_select_long_segment(None)
        else:
            self.btn_long_segments.pack_forget()
            self.tab_banners["long segments"].configure(
                text="No segments exceed 25 seconds.",
                text_color=("#15803d", "#4ade80")
            )
            self.long_insp_title.configure(text="All speech segment lengths are within the 25-second limit.")
            self.long_insp_detail.configure(text="")

        # 3. Overlaps
        for item in self.overlaps_tv.get_children():
            self.overlaps_tv.delete(item)
        self.tab_raw_records["overlaps"] = {}
        for idx, r in enumerate(overlap_records):
            iid = f"ol_{idx}"
            self.overlaps_tv.insert('', 'end', iid=iid, values=(r['file'], r['tier1'], r['time1'], r['tier2'], r['time2'], r['dur']))
            self.tab_raw_records["overlaps"][iid] = r

        if overlap_records:
            self.btn_overlaps.configure(text=f"Overlaps ({len(overlap_records)})")
            self.btn_overlaps.pack(side="left", padx=(0, 6))
            self.tab_banners["overlaps"].configure(
                text=f"{len(overlap_records)} Overlapping Segment(s) found (>400ms)",
                text_color=("#b45309", "#fbbf24")
            )
            self.overlaps_tv.selection_set("ol_0")
            self._on_select_overlap(None)
        else:
            self.btn_overlaps.pack_forget()
            self.tab_banners["overlaps"].configure(
                text="No overlapping segments found.",
                text_color=("#15803d", "#4ade80")
            )
            self.ol_insp_title.configure(text="No overlapping segments detected between target tiers.")
            self.ol_insp_detail.configure(text="")

        # Manage "No issues found" label
        if not na_records and not long_records and not overlap_records:
            self.lbl_no_issues.pack(side="left", padx=(0, 6))
        else:
            self.lbl_no_issues.pack_forget()

        # 4. Assessment
        self._all_assessment_records = assessment_records
        self._filter_assessment_table()
        file_count = sum(1 for r in assessment_records if not r.get('is_summary', False))
        self.btn_assessment.configure(text=f"Assessment ({file_count})")
        self.tab_banners["assessment"].configure(
            text=f"Assessment for {file_count} ELAN file(s) and Whole Dataset"
        )

        # 5. Chars
        self._all_char_records = char_records
        self._filter_chars_table()
        self.btn_chars.configure(text=f"Characters ({len(char_records)})")
        self.tab_banners["chars"].configure(text=f"{len(char_records)} Unique Characters in target tiers")

        # 6. Bigrams
        self._all_bigram_records = bigram_records
        self._filter_bigrams_table()
        self.btn_bigrams.configure(text=f"Bigrams ({len(bigram_records)})")
        self.tab_banners["bigrams"].configure(text=f"{len(bigram_records)} Unique Character Bigrams in target tiers")

        # 7. Words
        self._all_word_records = word_records
        self._filter_words_table()
        self.btn_words.configure(text=f"Words ({len(word_records)})")
        self.tab_banners["words"].configure(text=f"{len(word_records)} Unique Words in vocabulary")

        # Auto-switch to first available issue view, or fallback to Words
        if na_records:
            self.switch_view("not allowed chars")
        elif long_records:
            self.switch_view("long segments")
        elif overlap_records:
            self.switch_view("overlaps")
        else:
            self.switch_view("words")

        # Automatically expand report frame and collapse settings frame when reports are ready
        self.expand_report()
        self.collapse_settings()

    #========================
    def start_checking(self):
        # Check if at least one tier is selected
        any_selected = any(
            var.get() != "" 
            for tiers in getattr(self, "tier_vars", {}).values() 
            for var in tiers.values()
        )
        if not any_selected:
            messagebox.showwarning(
                "No Tiers Selected",
                "Please select at least one tier from the loaded ELAN file(s) before checking."
            )
            return

        self.report_frame.grid(row=4, column=0, padx=10, pady=5, sticky="nsew")
        self.dataset_settings_frame.grid(row=5, column=0, padx=10, pady=5, sticky="ew")
        threading.Thread(target=self.check_files, daemon=True).start()
    
    def check_files(self):
        if not self.selected_files:
            return
        
        letters = self.letters_textbox.get("0.0", "end").strip()
        punctuation = self.punctuation_textbox.get("0.0", "end").strip()
        allowed = set(list(letters) + list(punctuation) + [" "])
        DELIMITERS = "[" + re.escape(punctuation + " ") + "]"
        
        global_char_list = Counter()
        global_char_bigram = Counter()
        global_word_list = Counter()

        na_records = []
        long_records = []
        overlap_records = []
        assessment_records = []

        for file_path in self.selected_files:
            basename = os.path.basename(file_path)
            try:
                eaf = pympi.Elan.Eaf(file_path)
            except Exception as e:
                print(f"Error loading {basename}: {e}")
                continue

            file_not_allowed = Counter()
            file_na_tiers = {}
            file_na_samples = {}
            file_long_segments = []
            all_file_annotations = []
            file_tokens = 0
            file_word_set = set()
            file_total_duration_ms = 0
            file_segments_count = 0

            for tier in eaf.get_tier_names():
                # Skip unchecked tiers
                if file_path in self.tier_vars and tier in self.tier_vars[file_path]:
                    if self.tier_vars[file_path][tier].get() == "":
                        continue
                else:
                    continue
                
                annotations = []
                temp_ann = ()
                for ann in eaf.get_annotation_data_for_tier(tier):
                    if len(ann) == 3:
                        annotations.append(ann)
                    elif len(ann) == 4:
                        if temp_ann == ():
                            temp_ann = (ann[0], ann[1], ann[2])
                        elif ann[0] == temp_ann[0] and ann[1] == temp_ann[1]:
                            temp_ann = (ann[0], ann[1], temp_ann[2] + " " + ann[2])
                        else:
                            annotations.append(temp_ann)
                            temp_ann = (ann[0], ann[1], ann[2])
                if temp_ann != ():
                    annotations.append(temp_ann)

                sorted_anns = sorted(annotations, key=lambda x: x[0])
                
                for i in range(len(sorted_anns)):
                    ann = sorted_anns[i]
                    if len(ann) >= 3:
                        start, end, text = ann[0], ann[1], ann[2]
                        if not text: 
                            continue
                        
                        dur_ann = max(0, end - start)
                        file_total_duration_ms += dur_ann
                        file_segments_count += 1

                        all_file_annotations.append({
                            'tier': tier, 'start': start, 'end': end, 'text': text
                        })

                        for c in text:
                            if c not in (' ', '\t', '\n', '\r'):
                                global_char_list[c] += 1

                        for j in range(len(text) - 1):
                            bg = text[j:j+2]
                            if ' ' not in bg and '\t' not in bg and '\n' not in bg:
                                global_char_bigram[bg] += 1
                        
                        word_list = [w for w in re.split(DELIMITERS, text) if w]
                        file_tokens += len(word_list)
                        file_word_set.update([w.lower() for w in word_list])
                        global_word_list.update(word_list)
                        
                        # Check Disallowed
                        for char in text:
                            if char not in allowed:
                                file_not_allowed[char] += 1
                                if char not in file_na_tiers:
                                    file_na_tiers[char] = set()
                                file_na_tiers[char].add(tier)
                                if char not in file_na_samples:
                                    file_na_samples[char] = text
                        
                        # Check Long Segments (>25s)
                        duration = end - start
                        if duration > 25 * 1000: 
                            file_long_segments.append((tier, start, end, duration, text))

            # Compile Not Allowed for file
            for char, count in file_not_allowed.most_common():
                na_records.append({
                    'file': basename,
                    'char': char,
                    'hex': f"U+{ord(char):04X}",
                    'count': count,
                    'tiers': ', '.join(sorted(file_na_tiers.get(char, []))),
                    'sample': file_na_samples.get(char, "")
                })

            # Compile Long Segments for file
            for item in file_long_segments:
                tier_val, s_val, e_val, dur_val, text_val = item
                long_records.append({
                    'file': basename,
                    'tier': tier_val,
                    'start_ms': s_val,
                    'end_ms': e_val,
                    'start': self.ms_to_hh_mm_ss(s_val),
                    'end': self.ms_to_hh_mm_ss(e_val),
                    'dur': f"{dur_val/1000:.1f}s",
                    'preview': (text_val[:40] + '...') if len(text_val) > 40 else text_val,
                    'full_text': text_val
                })

            # Check Overlaps (>400ms)
            all_file_annotations.sort(key=lambda x: x['start'])
            for i in range(len(all_file_annotations)):
                for j in range(i + 1, len(all_file_annotations)):
                    seg1 = all_file_annotations[i]
                    seg2 = all_file_annotations[j]

                    overlap_start = max(seg1['start'], seg2['start'])
                    overlap_end = min(seg1['end'], seg2['end'])
                    overlap = max(0, overlap_end - overlap_start)
                    
                    if overlap > 400:
                        overlap_records.append({
                            'file': basename,
                            'tier1': seg1['tier'],
                            'time1': f"{self.ms_to_hh_mm_ss(seg1['start'])}-{self.ms_to_hh_mm_ss(seg1['end'])}",
                            'text1': seg1['text'],
                            'tier2': seg2['tier'],
                            'time2': f"{self.ms_to_hh_mm_ss(seg2['start'])}-{self.ms_to_hh_mm_ss(seg2['end'])}",
                            'text2': seg2['text'],
                            'dur': f"{overlap/1000:.1f} s",
                            'overlap_start_ms': overlap_start,
                            'overlap_end_ms': overlap_end,
                            'overlap_start': self.ms_to_hh_mm_ss(overlap_start)
                        })
                    else:
                        break

            # Compile Assessment for file
            duration_sec = file_total_duration_ms / 1000.0
            count_tokens = file_tokens
            count_types = len(file_word_set)
            ttr = (count_types / count_tokens) if count_tokens > 0 else 0.0
            nttr = (count_tokens / (count_types * duration_sec)) if (count_types > 0 and duration_sec > 0) else 0.0

            assessment_records.append({
                'rank': len(assessment_records) + 1,
                'file': basename,
                'segments': file_segments_count,
                'duration': f"{self.ms_to_min_sec(file_total_duration_ms)} ({duration_sec:.1f}s)",
                'duration_sec': duration_sec,
                'tokens': count_tokens,
                'types': count_types,
                'ttr': f"{ttr:.4f}",
                'nttr': f"{nttr:.4f}"
            })

        # Calculate Whole Dataset Assessment Summary
        if assessment_records:
            total_ds_segments = sum(r['segments'] for r in assessment_records)
            total_ds_duration_ms = sum(int(r['duration_sec'] * 1000) for r in assessment_records)
            total_ds_duration_sec = total_ds_duration_ms / 1000.0
            total_ds_tokens = sum(global_word_list.values())
            total_ds_types = len(global_word_list)
            total_ds_ttr = (total_ds_types / total_ds_tokens) if total_ds_tokens > 0 else 0.0
            total_ds_nttr = (total_ds_tokens / (total_ds_types * total_ds_duration_sec)) if (total_ds_types > 0 and total_ds_duration_sec > 0) else 0.0

            summary_record = {
                'rank': 'Total',
                'file': '[ALL FILES / ENTIRE DATASET]',
                'segments': total_ds_segments,
                'duration': f"{self.ms_to_min_sec(total_ds_duration_ms)} ({total_ds_duration_sec:.1f}s)",
                'duration_sec': total_ds_duration_sec,
                'tokens': total_ds_tokens,
                'types': total_ds_types,
                'ttr': f"{total_ds_ttr:.4f}",
                'nttr': f"{total_ds_nttr:.4f}",
                'is_summary': True
            }
            assessment_records = [summary_record] + assessment_records

        # Compile Chars, Bigrams & Words
        total_chars = sum(global_char_list.values()) or 1
        char_records = []
        char_freq_text = "Count\tPercentage\tCharacter\n"
        for rank, (char, count) in enumerate(global_char_list.most_common(), start=1):
            pct_val = f"{(count / total_chars * 100):.2f}%"
            char_records.append({
                'rank': rank, 'char': char, 'hex': f"U+{ord(char):04X}", 'count': count, 'pct': pct_val
            })
            char_freq_text += f"{count}\t{pct_val}\t{char}\n"
        self.saved_char_freqs = char_freq_text

        total_bigrams = sum(global_char_bigram.values()) or 1
        bigram_records = []
        bigram_freq_text = "Count\tPercentage\tBigram\n"
        for rank, (bg, count) in enumerate(global_char_bigram.most_common(), start=1):
            pct_val = f"{(count / total_bigrams * 100):.2f}%"
            hex_repr = " ".join(f"U+{ord(c):04X}" for c in bg)
            bigram_records.append({
                'rank': rank, 'bigram': bg, 'hex': hex_repr, 'count': count, 'pct': pct_val
            })
            bigram_freq_text += f"{count}\t{pct_val}\t{bg}\n"
        self.saved_bigram_freqs = bigram_freq_text

        total_words = sum(global_word_list.values()) or 1
        word_records = []
        word_freq_text = "Count\tPercentage\tWord\n"
        sorted_word_list = sorted(global_word_list.items(), key=lambda x: (-x[1], x[0]))
        for rank, (word, count) in enumerate(sorted_word_list, start=1):
            pct_val = f"{(count / total_words * 100):.2f}%"
            word_records.append({
                'rank': rank, 'word': word, 'count': count, 'pct': pct_val, 'len': len(word)
            })
            word_freq_text += f"{count}\t{pct_val}\t{word}\n"
        self.saved_word_freqs = word_freq_text

        self.after(0, lambda: self._populate_interactive_reports(
            na_records, long_records, overlap_records, assessment_records, char_records, bigram_records, word_records
        ))

    def log_report(self, message):
        pass

    def log_issue(self, message):
        pass

    def log_to_tab(self, tab_name, message):
        pass
    
    def log_reset(self):
        pass

    def ms_to_min_sec(self, milliseconds):
        ''' convert milliseconds to MM:SS format string '''
        total_seconds = milliseconds // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    #========================
    def set_train_folder(self, foldername):
        """Update train folder path and entry box."""
        self.train_folder = foldername or ""
        self.train_folder_entry.delete(0, "end")
        if foldername:
            self.train_folder_entry.insert(0, foldername)

    def select_train_folder(self):
        """Open directory dialog to choose output training dataset destination."""
        initial = self.train_folder_entry.get().strip() or getattr(self, "train_folder", "") or None
        foldername = filedialog.askdirectory(title="Select Destination Folder", initialdir=initial)
        if foldername:
            self.set_train_folder(foldername)

    def set_replacements_file(self, filename):
        """Update find & replace mapping file and entry box."""
        self.replacements_file = filename or ""
        self.replacements_entry.delete(0, "end")
        if filename:
            self.replacements_entry.insert(0, filename)
            self.browse_replacements_button.configure(text=f"📄 {os.path.basename(filename)}")
        else:
            self.browse_replacements_button.configure(text="📄 Select File…")

    def select_replacements_file(self):
        """Open file dialog to choose Find & Replace TSV/TXT file."""
        filename = filedialog.askopenfilename(
            title="Select Find & Replace TSV/TXT File",
            filetypes=(("TSV files", "*.tsv"), ("Text files", "*.txt"), ("All files", "*.*"))
        )
        if filename:
            self.set_replacements_file(filename)

    def clear_replacements_file(self):
        """Clear currently selected Find & Replace mapping file."""
        self.set_replacements_file("")

    def build_train_set(self):
        """Build the training dataset ZIP package with progress tracking."""
        any_selected = any(
            var.get() != "" 
            for tiers in getattr(self, "tier_vars", {}).values() 
            for var in tiers.values()
        )
        if not any_selected:
            messagebox.showwarning(
                "No Tiers Selected",
                "Please select at least one tier to build the training dataset."
            )
            return

        folder = self.train_folder_entry.get().strip() or self.train_folder
        if not folder:
            messagebox.showerror("Error", "Please select a destination output folder.")
            return
        
        self.train_folder = folder
        repl_file = self.replacements_entry.get().strip() or self.replacements_file
        self.replacements_file = repl_file

        self.build_train_button.configure(state="disabled", text="Building Training Dataset…")
        self.progress_status_label.configure(text="Preparing dataset build and extracting audio clips…")
        self.build_success_card.grid_remove()
        self.progress_bar.set(0)

        def _build():
            try:
                zip_path = build_training_dataset(
                    self.selected_files,
                    self.tier_vars,
                    self.train_folder,
                    progress_callback=self._update_progress,
                    log_callback=self.log_report,
                    replacements_file=self.replacements_file
                )
                def _on_success():
                    self.build_train_button.configure(state="normal", text="Build Training Dataset (ZIP)")
                    self.progress_status_label.configure(text="Training dataset generated successfully!")
                    self.build_success_path_lbl.configure(text=f"File: {zip_path}")
                    self.build_success_card.grid()
                    self.collapse_report()
                self.after(0, _on_success)
            except Exception as e:
                def _on_err():
                    self.build_train_button.configure(state="normal", text="Build Training Dataset (ZIP)")
                    self.progress_status_label.configure(text=f"Error: {e}")
                    self.build_success_card.grid_remove()
                    messagebox.showerror("Build Error", f"Failed to build training dataset:\n{e}")
                self.after(0, _on_err)

        threading.Thread(target=_build, daemon=True).start()

    def open_google_drive(self):
        """Open Google Drive in default web browser."""
        webbrowser.open("https://drive.google.com/drive/my-drive")

    def open_training_colab(self):
        """Open Training Colab notebook in default web browser."""
        webbrowser.open("https://colab.research.google.com/drive/1vRt5T4FHj_z3KHv0_Z4fReHYW8IMOxNv?usp=sharing")

    def open_output_folder(self):
        """Open destination output directory in default file manager."""
        folder = self.train_folder_entry.get().strip() or getattr(self, "train_folder", "")
        if folder and os.path.exists(folder):
            try:
                os.startfile(folder)
            except Exception as e:
                print(f"Could not open directory {folder}: {e}")

    def _update_progress(self, current, total):
        def _update():
            frac = (current / total) if total else 0
            self.progress_bar.set(frac)
            self.progress_status_label.configure(text=f"Exporting audio clips and manifests: {current}/{total} ({int(frac*100)}%)")
            self.update_idletasks()
        self.after(0, _update)
