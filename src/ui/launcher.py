"""
Main Launcher UI for Easper.
Provides a modern interface to select between Transcriber and ASR Dataset Generator.
"""
import customtkinter as ctk

# Set appearance before creating window
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class LauncherApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Easper")
        self.geometry("900x800")
        self.minsize(600, 450)

        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Current frame reference
        self.current_frame = None
        
        # Show main menu
        self.show_main_menu()

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
        header_frame.grid(row=0, column=0, pady=(40, 20), sticky="ew")
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

        # Main content area with cards
        content_frame = ctk.CTkFrame(self.current_frame, fg_color="transparent")
        content_frame.grid(row=1, column=0, padx=40, pady=20, sticky="nsew")
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

        # Footer with theme toggle
        footer_frame = ctk.CTkFrame(self.current_frame, fg_color="transparent")
        footer_frame.grid(row=2, column=0, pady=(0, 20), sticky="s")

        theme_label = ctk.CTkLabel(footer_frame, text="Theme:", font=ctk.CTkFont(size=12))
        theme_label.grid(row=0, column=0, padx=(0, 10))

        self.theme_switch = ctk.CTkSwitch(
            footer_frame,
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
