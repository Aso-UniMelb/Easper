#!/bin/bash

# Easper macOS Setup Script
# -------------------------
# This script prepares the Easper environment on macOS.
# 1. Installs Homebrew (if missing)
# 2. Installs Python 3.11 and FFmpeg
# 3. Creates a virtual environment and installs requirements.

set -e # Exit on error

echo "🎙️ Starting Easper macOS Setup..."

# 1. Check for Homebrew
if ! command -v brew &> /dev/null; then
    echo "🔍 Homebrew not found. Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
    # Add brew to PATH for current session (Intel vs Apple Silicon)
    if [[ $(uname -m) == "arm64" ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    else
        eval "$(/usr/local/bin/brew shellenv)"
    fi
fi

# 2. Install Python 3.11
echo "🐍 Installing Python 3.11..."
brew install python@3.11

# 3. Install FFmpeg (Standard brew install is version 7.x)
echo "🎞️ Installing FFmpeg..."
brew install ffmpeg

# 4. Create Virtual Environment
echo "📦 Setting up virtual environment..."
# Locate the brew-installed python3.11 executable
PYTHON_EXE=$(brew --prefix python@3.11)/bin/python3.11
$PYTHON_EXE -m venv venv
source venv/bin/activate

# 5. Install requirements
if [ -f "requirements.txt" ]; then
    echo "📥 Installing requirements from requirements.txt..."
    pip install --upgrade pip
    pip install -r requirements.txt
elif [ -f "../requirements.txt" ]; then
    echo "📥 Installing requirements from ../requirements.txt..."
    pip install --upgrade pip
    pip install -r ../requirements.txt
else
    echo "⚠️ requirements.txt not found. Please install manualy using 'pip install -r requirements.txt'"
fi

echo "✅ Setup complete!"
echo "-------------------------------------------------------"
echo "To start Easper:"
echo "1. Activate environment:  source venv/bin/activate"
echo "2. Run application:       python src/main.py"
echo "-------------------------------------------------------"
