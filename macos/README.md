# 🍏 macOS Setup for Easper

This directory contains the automation script to prepare your macOS system for Easper.

## 🚀 Quick Start

1. **Open Terminal** in the root folder of the project.
2. **Run the setup script** (type `y` if prompted in the terminal to install Homebrew/dependencies):
   ```bash
   bash macos/setup.sh
   ```
3. **Download the Whisper-small model**:
   ```bash
   source venv/bin/activate
   python download-whisper-small.py
   ```
4. **Run the App**:
   ```bash
   bash run-macos.sh
   ```

## 📋 What the script does:
- Checks for **Homebrew** and installs it if missing.
- Installs **Python 3.12** and Tkinter bindings via Homebrew.
- Installs **FFmpeg** (version 7+).
- Creates a **virtual environment (`venv`)** in the project root.
- Installs all dependencies from `requirements.txt`.

---

> [!NOTE]
> Installing Homebrew may require your macOS user password. The script will prompt you if necessary.
