"""
Main Launcher UI for Easper.
Provides a modern interface to select between Transcriber and ASR Dataset Generator,
with built-in in-app auto-update capabilities.
"""
import threading
import customtkinter as ctk
from tkinter import messagebox

from src.utils.updater import (
    get_local_version,
    check_for_updates,
    download_and_apply_update,
    restart_application
)

# Set appearance before creating window
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class UpdateModalDialog(ctk.CTkToplevel):
    """Modern modal dialog for reviewing and applying application updates."""
    
    def __init__(self, parent, update_info):
        super().__init__(parent)
        self.parent = parent
        self.update_info = update_info
        
        self.title("Easper - Update Available")
        self.geometry("520x440")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center dialog relative to parent
        self.update_idletasks()
        try:
            x = parent.winfo_x() + (parent.winfo_width() // 2) - 260
            y = parent.winfo_y() + (parent.winfo_height() // 2) - 220
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=25, pady=(25, 10), sticky="ew")
        
        title_lbl = ctk.CTkLabel(
            header_frame,
            text=f"✨ New Update Available: v{update_info.get('latest_version')}",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_lbl.grid(row=0, column=0, sticky="w")

        curr_ver_lbl = ctk.CTkLabel(
            header_frame,
            text=f"Current version: v{update_info.get('current_version')}",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        curr_ver_lbl.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # Changelog / Release notes
        cl_frame = ctk.CTkFrame(self)
        cl_frame.grid(row=1, column=0, padx=25, pady=10, sticky="nsew")
        cl_frame.grid_columnconfigure(0, weight=1)
        cl_frame.grid_rowconfigure(1, weight=1)

        cl_title = ctk.CTkLabel(
            cl_frame,
            text="What's New:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        cl_title.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")

        self.changelog_box = ctk.CTkTextbox(cl_frame, height=130, font=ctk.CTkFont(size=12))
        self.changelog_box.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="nsew")
        
        changelog_text = update_info.get("changelog", "Bug fixes and performance improvements.")
        self.changelog_box.insert("1.0", changelog_text)
        self.changelog_box.configure(state="disabled")

        # Progress Area
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(row=2, column=0, padx=25, pady=(5, 10), sticky="ew")
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            self.progress_frame,
            text="Safe update: your downloaded models and settings will be preserved.",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.status_label.grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, height=10)
        self.progress_bar.grid(row=1, column=0, sticky="ew")
        self.progress_bar.set(0)
        self.progress_bar.grid_remove()

        # Action Buttons Frame
        self.button_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.button_frame.grid(row=3, column=0, padx=25, pady=(10, 25), sticky="ew")
        self.button_frame.grid_columnconfigure((0, 1), weight=1)

        self.later_button = ctk.CTkButton(
            self.button_frame,
            text="Remind Me Later",
            fg_color="gray",
            hover_color="#555555",
            command=self.destroy,
            height=38
        )
        self.later_button.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        self.update_button = ctk.CTkButton(
            self.button_frame,
            text="🚀 Update Now",
            font=ctk.CTkFont(weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            command=self.start_update_process,
            height=38
        )
        self.update_button.grid(row=0, column=1, padx=(8, 0), sticky="ew")

    def start_update_process(self):
        """Begin downloading and applying the update in a background thread."""
        self.later_button.configure(state="disabled")
        self.update_button.configure(state="disabled", text="Updating...")
        self.progress_bar.grid()
        self.progress_bar.set(0.05)
        self.status_label.configure(text="Preparing update download...", text_color=None)

        def _worker():
            try:
                download_url = self.update_info.get("download_url")
                download_and_apply_update(
                    download_url=download_url,
                    progress_callback=self._update_progress_ui
                )
                self.after(0, self._on_update_success)
            except Exception as e:
                self.after(0, lambda err=str(e): self._on_update_error(err))

        threading.Thread(target=_worker, daemon=True).start()

    def _update_progress_ui(self, percent, message):
        def _apply():
            self.progress_bar.set(percent)
            self.status_label.configure(text=message)
        self.after(0, _apply)

    def _on_update_success(self):
        self.progress_bar.set(1.0)
        self.status_label.configure(
            text="✅ Update completed successfully! Restarting Easper...",
            text_color="#10b981"
        )
        self.later_button.grid_remove()
        
        self.update_button.configure(
            state="normal",
            text="🔄 Restart Easper Now",
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=restart_application
        )
        self.update_button.grid(row=0, column=0, columnspan=2, sticky="ew")

    def _on_update_error(self, error_message):
        self.later_button.configure(state="normal")
        self.update_button.configure(state="normal", text="Retry Update")
        self.status_label.configure(
            text=f"❌ Error: {error_message}",
            text_color="#ef4444"
        )


class LauncherApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.version = get_local_version()
        self.title(f"Easper v{self.version}")
        self.geometry("900x800")
        self.minsize(600, 450)

        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Current frame reference
        self.current_frame = None
        self.update_badge = None
        
        # Show main menu
        self.show_main_menu()

        # Background update check (silent)
        self._start_background_update_check()

    def show_main_menu(self):
        """Show the main launcher menu."""
        # Clear current frame if exists
        if self.current_frame:
            self.current_frame.destroy()
        
        self.current_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.current_frame.grid(row=0, column=0, sticky="nsew", rowspan=2)
        self.current_frame.grid_columnconfigure(0, weight=1)
        self.current_frame.grid_rowconfigure(2, weight=1)

        # Header
        header_frame = ctk.CTkFrame(self.current_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, pady=(35, 15), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            header_frame, 
            text="🎙️ Easper",
            font=ctk.CTkFont(size=32, weight="bold")
        )
        title_label.grid(row=0, column=0)

        subtitle_label = ctk.CTkLabel(
            header_frame, 
            text="Audio Transcription & ASR Dataset Generation Tools",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        subtitle_label.grid(row=1, column=0, pady=(5, 0))

        # Dynamic Update Notification Banner Frame
        self.update_banner_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        self.update_banner_frame.grid(row=2, column=0, pady=(10, 0))
        self.cached_update_info = getattr(self, "cached_update_info", None)
        if self.cached_update_info and self.cached_update_info.get("has_update"):
            self._render_update_badge(self.cached_update_info)

        # Main content area with cards
        content_frame = ctk.CTkFrame(self.current_frame, fg_color="transparent")
        content_frame.grid(row=1, column=0, padx=40, pady=15, sticky="nsew")
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=1)
        content_frame.grid_rowconfigure(0, weight=1)

        # Transcriber Card
        transcriber_card = ctk.CTkFrame(content_frame, corner_radius=15)
        transcriber_card.grid(row=0, column=0, padx=15, pady=10, sticky="nsew")
        transcriber_card.grid_columnconfigure(0, weight=1)

        transcriber_icon = ctk.CTkLabel(
            transcriber_card,
            text="📝",
            font=ctk.CTkFont(size=48)
        )
        transcriber_icon.grid(row=0, column=0, pady=(30, 10))

        transcriber_title = ctk.CTkLabel(
            transcriber_card,
            text="Transcriber",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        transcriber_title.grid(row=1, column=0, pady=(0, 10))

        transcriber_desc = ctk.CTkLabel(
            transcriber_card,
            text="Transcribe audio files to ELAN\nformat with speaker diarization\nand automatic segmentation.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            justify="center"
        )
        transcriber_desc.grid(row=2, column=0, pady=(0, 20), padx=20)

        transcriber_button = ctk.CTkButton(
            transcriber_card,
            text="Open Transcriber",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            height=40,
            command=self.show_transcriber
        )
        transcriber_button.grid(row=3, column=0, pady=(0, 30), padx=30, sticky="ew")

        # Dataset Generator Card
        dataset_card = ctk.CTkFrame(content_frame, corner_radius=15)
        dataset_card.grid(row=0, column=1, padx=15, pady=10, sticky="nsew")
        dataset_card.grid_columnconfigure(0, weight=1)

        dataset_icon = ctk.CTkLabel(
            dataset_card,
            text="📊",
            font=ctk.CTkFont(size=48)
        )
        dataset_icon.grid(row=0, column=0, pady=(30, 10))

        dataset_title = ctk.CTkLabel(
            dataset_card,
            text="Dataset Generator",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        dataset_title.grid(row=1, column=0, pady=(0, 10))

        dataset_desc = ctk.CTkLabel(
            dataset_card,
            text="Create ASR training datasets\nfrom ELAN annotated files.\nExport as ready-to-use packages.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            justify="center"
        )
        dataset_desc.grid(row=2, column=0, pady=(0, 20), padx=20)

        dataset_button = ctk.CTkButton(
            dataset_card,
            text="Open Dataset Generator",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=40,
            command=self.show_dataset_generator
        )
        dataset_button.grid(row=3, column=0, pady=(0, 30), padx=30, sticky="ew")

        # Footer with version, check for updates, and theme toggle
        footer_frame = ctk.CTkFrame(self.current_frame, fg_color="transparent")
        footer_frame.grid(row=2, column=0, pady=(0, 20), padx=30, sticky="ew")
        footer_frame.grid_columnconfigure(1, weight=1)

        version_label = ctk.CTkLabel(
            footer_frame,
            text=f"v{self.version}",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        version_label.grid(row=0, column=0, padx=(0, 15))

        self.check_updates_btn = ctk.CTkButton(
            footer_frame,
            text="🔄 Check for Updates",
            font=ctk.CTkFont(size=12),
            width=130,
            height=28,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray80"),
            hover_color=("gray85", "gray25"),
            command=self.manual_check_for_updates
        )
        self.check_updates_btn.grid(row=0, column=1, sticky="w")

        # Theme switch on the right
        theme_controls_frame = ctk.CTkFrame(footer_frame, fg_color="transparent")
        theme_controls_frame.grid(row=0, column=2, sticky="e")

        theme_label = ctk.CTkLabel(theme_controls_frame, text="Theme:", font=ctk.CTkFont(size=12))
        theme_label.grid(row=0, column=0, padx=(0, 10))

        self.theme_switch = ctk.CTkSwitch(
            theme_controls_frame,
            text="Dark Mode",
            command=self.toggle_theme,
            font=ctk.CTkFont(size=12)
        )
        self.theme_switch.grid(row=0, column=1)
        
        # Set switch state based on current mode
        if ctk.get_appearance_mode() == "Dark":
            self.theme_switch.select()

    def toggle_theme(self):
        """Toggle between light and dark theme."""
        if self.theme_switch.get():
            ctk.set_appearance_mode("dark")
        else:
            ctk.set_appearance_mode("light")

    def _start_background_update_check(self):
        """Check for updates asynchronously on startup without blocking the UI."""
        def _check():
            info = check_for_updates(timeout=4.0)
            self.cached_update_info = info
            if info.get("has_update"):
                self.after(0, lambda: self._render_update_badge(info))

        threading.Thread(target=_check, daemon=True).start()

    def _render_update_badge(self, info):
        """Display an update notification badge in the header."""
        if not hasattr(self, "update_banner_frame") or not self.update_banner_frame.winfo_exists():
            return
        
        # Clear any existing child widgets
        for widget in self.update_banner_frame.winfo_children():
            widget.destroy()

        badge_btn = ctk.CTkButton(
            self.update_banner_frame,
            text=f"✨ Update Available: v{info.get('latest_version')}  (Click to Install)",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=30,
            corner_radius=15,
            command=lambda: self.open_update_dialog(info)
        )
        badge_btn.grid(row=0, column=0)

    def manual_check_for_updates(self):
        """Trigger a manual update check from the footer button."""
        self.check_updates_btn.configure(state="disabled", text="Checking...")

        def _worker():
            info = check_for_updates(timeout=6.0)
            self.cached_update_info = info

            def _handle_result():
                self.check_updates_btn.configure(state="normal", text="🔄 Check for Updates")
                if info.get("has_update"):
                    self._render_update_badge(info)
                    self.open_update_dialog(info)
                elif info.get("error"):
                    messagebox.showwarning(
                        "Update Check",
                        f"Could not connect to update server:\n{info.get('error')}\n\nPlease check your internet connection."
                    )
                else:
                    messagebox.showinfo(
                        "Up to Date",
                        f"Easper is up to date! (Version {self.version})"
                    )

            self.after(0, _handle_result)

        threading.Thread(target=_worker, daemon=True).start()

    def open_update_dialog(self, update_info):
        """Open the update modal."""
        UpdateModalDialog(self, update_info)

    def show_transcriber(self):
        """Show the transcriber UI."""
        if self.current_frame:
            self.current_frame.destroy()
        
        # Import here to avoid circular imports
        from src.ui.transcriber_ui import TranscribeToElanApp
        
        self.current_frame = TranscribeToElanApp(self, back_callback=self.show_main_menu)
        self.current_frame.grid(row=0, column=0, sticky="nsew", rowspan=2, padx=10, pady=10)
        self.title("Easper - Transcriber")

    def show_dataset_generator(self):
        """Show the dataset generator UI."""
        if self.current_frame:
            self.current_frame.destroy()
        
        # Import here to avoid circular imports
        from src.ui.dataset_ui import ElanToASRApp
        
        self.current_frame = ElanToASRApp(self, back_callback=self.show_main_menu)
        self.current_frame.grid(row=0, column=0, sticky="nsew", rowspan=2, padx=10, pady=10)
        self.title("Easper - Dataset Generator")


def main():
    app = LauncherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
