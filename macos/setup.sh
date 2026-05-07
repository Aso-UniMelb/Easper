#!/bin/bash

# Easper macOS Setup Script
# -------------------------
# This script prepares the Easper environment on macOS.
# 1. Installs Homebrew (if missing)
# 2. Installs uv and FFmpeg
# 3. Creates a virtual environment with uv (Python 3.12) and installs requirements.

set -e # Exit on error

echo "Starting Easper macOS Setup..."
echo "-------------------------------------------------------"

# 1. Check for Homebrew
if ! command -v brew &> /dev/null; then
    echo "Homebrew not found. Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Add brew to PATH for current session (Intel vs Apple Silicon)
    if [[ $(uname -m) == "arm64" ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    else
        eval "$(/usr/local/bin/brew shellenv)"
    fi
fi

# 2. Install uv
echo "Installing uv..."
brew install uv

# 3. Install Python 3.12 with Tk support (customtkinter requires _tkinter)
echo "Installing Python 3.12 and Tk bindings..."
brew install python@3.12 python-tk@3.12

# 4. Install FFmpeg (Standard brew install is version 7.x)
echo "Installing FFmpeg..."
brew install ffmpeg

# 5. Create Virtual Environment with uv, using the brew Python so Tk is available
echo "Setting up virtual environment with uv..."
PYTHON_EXE="$(brew --prefix python@3.12)/bin/python3.12"
uv venv --python "$PYTHON_EXE" venv
source venv/bin/activate

# 5. Install requirements
if [ -f "requirements.txt" ]; then
    echo "Installing requirements from requirements.txt..."
    uv pip install -r requirements.txt
elif [ -f "../requirements.txt" ]; then
    echo "Installing requirements from ../requirements.txt..."
    uv pip install -r ../requirements.txt
else
    echo "requirements.txt not found. Please install manually using 'uv pip install -r requirements.txt'"
fi

echo "-------------------------------------------------------"
echo "✅ Setup complete!"