#!/bin/bash

# Easper Run Script
# -----------------
# Activates the virtual environment and launches the application.

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "⚠️ Virtual environment 'venv' not found."
    echo "Please run the setup script first:"
    echo "  bash macos/setup.sh"
    exit 1
fi

# Activate and run
source venv/bin/activate
python src/main.py
