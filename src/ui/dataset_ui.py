"""
Dataset UI module for Elan-ASR Pipeline.
Contains the ElanToASRApp class for the dataset generator GUI.
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import re
from collections import Counter
import pympi
import threading

from src.core.dataset import build_training_dataset


class ElanToASRApp(ctk.CTkFrame):
    def __init__(self, parent, back_callback=None):
        super().__init__(parent)
        
        self.parent = parent
        self.back_callback = back_callback

        # configure grid layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.selected_files = []
        self.train_folder = ""

        # === Back Button (if callback provided)
        if back_callback:
            self.back_button = ctk.CTkButton(self, text="← Back to Menu", command=back_callback, width=120, fg_color="gray")
            self.back_button.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")

        # === Browse Button for ELAN files
        self.browse_files_button = ctk.CTkButton(self, text="Select ELAN Files...", command=self.browse_files)
        self.browse_files_button.grid(row=1, column=0, padx=10, pady=(20, 10), sticky="ewn")

        # === Settings
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")
        self.settings_frame.grid_columnconfigure(0, weight=1)
        self.settings_frame.grid_rowconfigure(4, weight=1)
        # letters
        self.letters_label = ctk.CTkLabel(self.settings_frame, text="Allowed Letters in Transcriptions:")
        self.letters_label.grid(row=0, column=0, padx=10, pady=(5, 0), sticky="w")        
        self.letters_textbox = ctk.CTkTextbox(self.settings_frame, height=30, width=300)
        self.letters_textbox.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="ew")
        self.letters_textbox.insert("0.0", "abcdefghijklmnopqrstuvwxyz")
        # punctuation
        self.punctuation_label = ctk.CTkLabel(self.settings_frame, text="Allowed Punctuation Marks:")
        self.punctuation_label.grid(row=2, column=0, padx=10, pady=(5, 0), sticky="w")        
        self.punctuation_textbox = ctk.CTkTextbox(self.settings_frame, height=30)
        self.punctuation_textbox.grid(row=3, column=0, padx=10, pady=(0, 5), sticky="ew")
        self.punctuation_textbox.insert("0.0", '- . , ; : ! ? "')
        # tiers list placeholder
        self.tiers_frame = ctk.CTkScrollableFrame(self.settings_frame, label_text="Select Target Tiers:")
        self.tiers_frame.grid(row=4, column=0, padx=10, pady=5, sticky="nsew", columnspan=2)
        
        self.tier_widgets = []

        # Main Button to Start Checking
        self.check_button = ctk.CTkButton(self.settings_frame, text="Check!", command=self.start_checking, fg_color="green")
        self.check_button.grid(row=5, column=0, padx=10, pady=5, sticky="n", columnspan=2)
        
        self.settings_frame.grid_remove()

        # === Dataset settings
        self.dataset_settings_frame = ctk.CTkFrame(self)
        self.dataset_settings_frame.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        self.dataset_settings_frame.grid_columnconfigure(1, weight=1)

        self.train_folder_label = ctk.CTkLabel(self.dataset_settings_frame, text="Training Dataset Folder:")
        self.train_folder_label.grid(row=0, column=0, padx=10, pady=(5, 0), sticky="w")

        self.browse_train_folder_button = ctk.CTkButton(self.dataset_settings_frame, text="📂", command=self.select_train_folder)
        self.browse_train_folder_button.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")

        # Button to Build Training Dataset
        self.build_train_button = ctk.CTkButton(self.dataset_settings_frame, text="Build Training Dataset", command=self.build_train_set, fg_color="red")
        self.build_train_button.grid(row=2, column=0, padx=10, pady=5, sticky="")

        # progress bar
        self.progress_bar = ctk.CTkProgressBar(self.dataset_settings_frame)
        self.progress_bar.grid(row=3, column=0, padx=10, pady=5, sticky="ew", columnspan=2)
        self.progress_bar.set(0)
        
        self.dataset_settings_frame.grid_remove()


        # === Issues and Reports (Tabbed Interface)
        self.report_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.report_frame.grid(row=0, column=1, padx=10, pady=5, sticky="nsew", rowspan=6)
        self.report_frame.grid_columnconfigure(0, weight=1)
        self.report_frame.grid_rowconfigure(0, weight=1)

        # Create Tabview
        self.tabview = ctk.CTkTabview(self.report_frame)
        self.tabview.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        # Add tabs
        # Add tabs
        self.tab_names = ["not allowed chars", "long segments", "overlaps", "chars", "words"]
        self.textboxes = {}
        
        for name in self.tab_names:
            self.tabview.add(name)
            self.tabview.tab(name).grid_columnconfigure(0, weight=1)
            self.tabview.tab(name).grid_rowconfigure(0, weight=1)
            
            textbox = ctk.CTkTextbox(self.tabview.tab(name), state="disabled", wrap="none")
            textbox.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
            self.textboxes[name] = textbox


        # hide report frame initially
        self.report_frame.grid_remove()
        
    #========================
    def browse_files(self):
        filetypes = (('ELAN files', '*.eaf'), ('All files', '*.*'))
        filenames = filedialog.askopenfilenames(title="Select ELAN files", filetypes=filetypes)
        if filenames:
            # get the full directory path of the first file
            self.train_folder = os.path.dirname(filenames[0])
            self.browse_train_folder_button.configure(text=self.train_folder)    
            self.selected_files = filenames
            self.settings_frame.grid()

            # Clear existing widgets
            for widget in self.tier_widgets:
                widget.destroy()
            self.tier_widgets = []

            self.tier_vars = {}
            row_idx = 0
            
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
                        count = len(eaf.get_annotation_data_for_tier(tier))
                        if count == 0:
                            continue
                        display_text = f"{tier} ({count} annotations)"
                        var = ctk.StringVar(value=tier)
                        chk = ctk.CTkCheckBox(self.tiers_frame, text=display_text, variable=var, onvalue=tier, offvalue="")
                        if not tier.startswith("tx@"):
                            chk.deselect()
                        chk.grid(row=row_idx, column=0, padx=5, pady=2, sticky="w")
                        row_idx += 1
                        self.tier_widgets.append(chk)
                        
                        self.tier_vars[file_path][tier] = var
                    
                    row_idx += 1

                except Exception as e:
                    print(f"Error processing {basename}: {e}")

    #========================
    def start_checking(self):
        threading.Thread(target=self.check_files).start()
    
    def check_files(self):
        self.report_frame.grid()
        if not self.selected_files:
            return
        
        self.log_reset()
        
        letters = self.letters_textbox.get("0.0", "end").strip()
        punctuation = self.punctuation_textbox.get("0.0", "end").strip()
        allowed = set(list(letters) + list(punctuation) + [" "])
        DELIMITERS = "[" + re.escape(punctuation + " ") + "]"
        
        global_char_list = Counter()
        global_char_bigram = Counter()
        global_word_list = Counter()
        
        if not letters:
            self.log_to_tab("not allowed chars", "Warning: No letters specified.\n")

        for file_path in self.selected_files:
            basename = os.path.basename(file_path)
            try:
                eaf = pympi.Elan.Eaf(file_path)
            except Exception as e:
                self.log_to_tab("not allowed chars", f"Error loading {basename}: {e}\n")
                continue

            file_not_allowed = Counter()
            file_long_segments = []
            file_overlapping = []
            
            all_file_annotations = []

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
                # try:
                    
                # except:
                #     continue

                sorted_anns = sorted(annotations, key=lambda x: x[0])
                
                for i in range(len(sorted_anns)):
                    # sometimes annotation contains more than 3 elements
                    ann = sorted_anns[i]
                    if len(ann) >= 3:
                        start, end, text = ann[0], ann[1], ann[2]
                        if not text: 
                            continue
                        
                        # Collect for overlap check
                        all_file_annotations.append({
                            'tier': tier, 'start': start, 'end': end, 'text': text
                        })

                        # Stats
                        global_char_list.update(text)
                        for j in range(len(text) - 1):
                            if text[j] in allowed and text[j+1] in allowed:
                                global_char_bigram.update(text[j:j+2])
                        
                        word_list = [w for w in re.split(DELIMITERS, text) if w]
                        global_word_list.update(word_list)
                        
                        # Check Not Allowed
                        for char in text:
                            if char not in allowed:
                                file_not_allowed[char] += 1
                        
                        # Check Long Segments
                        duration = end - start
                        if duration > 25 * 1000: 
                            file_long_segments.append((tier, start, end, duration))

            # Check Overlaps (All tiers)
            all_file_annotations.sort(key=lambda x: x['start'])
            for i in range(len(all_file_annotations)):
                for j in range(i + 1, len(all_file_annotations)):
                    seg1 = all_file_annotations[i]
                    seg2 = all_file_annotations[j]

                    overlap = max(0, min(seg1['end'], seg2['end']) -max(seg1['start'], seg2['start']))
                    
                    if overlap > 400:
                        # Overlap found
                        file_overlapping.append((
                            seg1['tier'], seg1['start'], seg1['end'],
                            seg2['tier'], seg2['start'], seg2['end']
                        ))
                    else:
                        break  # Sorted by start, so no further overlaps possible for seg1

            # Log File Issues
            if file_not_allowed:
                 self.log_to_tab("not allowed chars", f"File: {basename}")
                 self.log_to_tab("not allowed chars", "Character\tUnicode\tCount")
                 report_list = ''
                 for char, count in file_not_allowed.most_common():
                    report_list += f"{char}\t{ord(char):x}\t{count}\n"
                 self.log_to_tab("not allowed chars", report_list + "\n")
            
            self.log_to_tab("long segments", f"File: {basename}")
            if file_long_segments:                 
                 self.log_to_tab("long segments", "Tier\t\tStart\tDuration")
                 report_list = ''
                 for item in file_long_segments:
                    report_list += f"{item[0]}\t\t{self.ms_to_min_sec(item[1])}\t{item[3]/1000:.1f}s\n"
                 self.log_to_tab("long segments", report_list + "\n")
            else:
                 self.log_to_tab("long segments", "\tNo long segments found\n")

            self.log_to_tab("overlaps", f"File: {basename}")
            if file_overlapping:
                 self.log_to_tab("overlaps", "Start\tEnd\tTier")
                 for item in file_overlapping:
                      # item: (t1, s1, e1, t2, s2, e2)
                      s1_str = self.ms_to_min_sec(item[1])
                      e1_str = self.ms_to_min_sec(item[2])
                      s2_str = self.ms_to_min_sec(item[4])
                      e2_str = self.ms_to_min_sec(item[5])
                      self.log_to_tab("overlaps", f"{s1_str}\t{e1_str}\t{item[0]}\n{s2_str}\t{e2_str}\t{item[3]}\n")
                 self.log_to_tab("overlaps", "\n")
            else:
                 self.log_to_tab("overlaps", "\tNo overlapping segments found\n")
                    
        # Global Stats output
        unused_bigrams = []
        for c1 in letters:
            for c2 in letters:
                if c1+c2 not in global_char_bigram:
                    unused_bigrams.append(c1+c2)
        
        # self.log_to_tab("chars", "=== Unused Character Bigrams ===\n")
        # self.log_to_tab("chars", " ".join(unused_bigrams))
        self.log_to_tab("chars", "\n\n=== Character Frequencies ===\n")
        self.log_to_tab("chars", "Count\tCharacter")
        char_list = ''
        for char, count in global_char_list.most_common():
            char_list += f"{count}\t{char}\n"
        self.log_to_tab("chars", char_list)

        self.log_to_tab("words", "=== Word Frequencies ===\n")
        self.log_to_tab("words", "Count\tWord\n")
        word_list = ''
        # sort global_word_list first by frequency then by alphabetic order
        sorted_word_list = sorted(global_word_list.items(), key=lambda x: (-x[1], x[0]))
        for word, count in sorted_word_list:
            word_list += f"{count}\t{word}\n"
        self.log_to_tab("words", word_list)
        
        self.dataset_settings_frame.grid()

    def log_report(self, message):
        # Fallback for old calls or build log
        if "warning" in message.lower() or "error" in message.lower():
             self.log_to_tab("not allowed chars", f"LOG: {message}\n")
        else:
             print(f"REPORT: {message}")

    def log_issue(self, message):
        # Deprecated
        pass

    def log_to_tab(self, tab_name, message):
        if tab_name in self.textboxes:
            tb = self.textboxes[tab_name]
            tb.configure(state="normal")
            tb.insert("end", message + "\n")
            tb.see("end")
            tb.configure(state="disabled")
    
    def log_reset(self):
        for tb in self.textboxes.values():
            tb.configure(state="normal")
            tb.delete("1.0", "end")
            tb.configure(state="disabled")


    def ms_to_min_sec(self, milliseconds):
        ''' convert milliseconds to MM:SS format string '''
        total_seconds = milliseconds // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02}"

    #========================
    def select_train_folder(self):
        foldername = filedialog.askdirectory(title="Select Save Folder")
        if foldername:
            self.train_folder = foldername
            self.browse_train_folder_button.configure(text=foldername)

    def build_train_set(self):
        if not self.train_folder:
            self.log_report("Error: No output folder selected.")
            return
        
        def _build():
            self.log_reset()
            zip_path = build_training_dataset(
                self.selected_files,
                self.tier_vars,
                self.train_folder,
                progress_callback=self._update_progress,
                log_callback=self.log_report
            )
            self.after(0, lambda: messagebox.showinfo("Done", f"Training dataset built successfully!\nDataset stored at: {zip_path}"))
        
        threading.Thread(target=_build, daemon=True).start()

    def _update_progress(self, current, total):
        def _update():
            self.progress_bar.set(current / total)
            self.update_idletasks()
        self.after(0, _update)
