# Easper
A Portable ASR Workflow for Field Linguists

## Features

- **Transcriber**: Transcribe audio files to ELAN format with automatic speaker diarization (SpeechBrain or Pyannote)
- **Dataset Generator**: Create ASR training datasets from ELAN annotated files
- **Dual Interface**: Use via GUI or command line

## Installation

### Option 1: Using the Installer (Windows Only)

1. Go to Easper Releases
2. Download `Easper_installer.exe`
3. Run the installer and follow the instructions

### Option 2: Manual Installation

1. Install FFmpeg 7.1.1 and added to system PATH
2. Install Python 3.11+
3. git clone repo
4. cd Easper
5. pip install -r requirements.txt

## Usage

### GUI

1. Run `python -m src/main.py`
2. Follow the instructions in the GUI

### Command Line

**Transcribe audio to ELAN:**
```bash
python -m src/main.py transcribe -i audio.wav -m user_models/whisper-small -s 2
```

**Build dataset from ELAN files:**
```bash
python -m src/main.py dataset -i file.eaf -o ./output -t "Speaker_00,Speaker_01"
```

**Show help:**
```bash
python -m src/main.py --help
python -m src/main.py transcribe --help
python -m src/main.py dataset --help
```



## License

MIT License