# 🛠️ Building the Windows Installer

This folder contains the scripts and configurations required to build the standalone Windows installer for Easper using **Inno Setup**.

## 💡 Key Features of the Installer
- **Low Privilege**: Installs directly to the user's `LocalAppData` folder, requiring **no administrator rights**.
- **Managed Environment**: Automatically creates a localized Python virtual environment (`venv`) within the application directory.
- **Offline-Ready**: Designed to work in field conditions with **minimal internet access** by bundling dependencies.
- **Python Setup**: Detects if Python 3.11 is missing and offers to download and install it automatically.

## 📋 Prerequisites

1. **Inno Setup**: Download and install Inno Setup 6+ from [jrsoftware.org](https://jrsoftware.org/isdl.php).
2. **FFmpeg**: Ensure the `ffmpeg-7.1.1-full_build` directory is present in this folder.
   - [Download FFmpeg 7.1.1 Full Build (GitHub Mirror)](https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/ffmpeg-7.1.1-full_build.7z)
   - Alternatively, browse the [gyan.dev build archive](https://www.gyan.dev/ffmpeg/builds/) or [VideoHelp archives](https://www.videohelp.com/software/ffmpeg/old-versions).
3. **Pip Packages**: Pre-downloaded wheels for offline installation (see Build Steps).

## 🚀 Build Steps

1. **Download Pip Packages**:
   Run the following script to fetch all necessary Python dependencies into the `pip_packages` folder. This ensures the installer can set up the environment offline:
   ```cmd
   download_pip_packages.bat
   ```

2. **Prepare Models (Optional)**:
   Ensure any default models (e.g., whisper-base) are placed in the `user_models` directory if you wish to bundle them with the installer.

3. **Compile Installer**:
   - Open `Easper_installer.iss` in the **Inno Setup Compiler**.
   - Click **Build > Compile** (or press `Ctrl+F9`).
   - The compiled setup executable will be generated in the `Output` directory.

---

> [!TIP]
> Always verify that `ffmpeg` and `pip_packages` are correctly populated before compiling, as they are large assets that are not automatically included in the repository source.
