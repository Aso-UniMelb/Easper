# 🍏 macOS Setup for Easper

This directory contains the automation script to prepare your macOS system for Easper.

## 🚀 Quick Start

1. **Open Terminal** in this folder (or the root folder).
2. **Run the setup script**:
   ```bash
   bash macos/setup.sh
   ```

## 📋 What the script does:
- Checks for **Homebrew** and installs it if missing.
- Installs **Python 3.11** via Homebrew.
- Installs **FFmpeg** (version 7+).
- Creates a **virtual environment (`venv`)** in the project root.
- Installs all dependencies from `requirements.txt`.

## 🛠️ Manual Usage
Once the setup is complete, you can start Easper by running:
```bash
bash run-macos.sh
```

---

> [!NOTE]
> Installing Homebrew may require your macOS user password. The script will prompt you if necessary.
