# 🎙️ Easper

**A Portable ASR Workflow for Field Linguists**

Easper is a specialized tool designed to streamline the Automatic Speech Recognition (ASR) workflow for linguistic fieldwork. It provides a bridge between raw audio recordings and structured ELAN annotations, enabling researchers to quickly transcribe and prepare datasets for language modeling.

---

## ✨ Features

- **🚀 Automated Transcription**: Convert audio recordings directly into ELAN (.eaf) format.
- **👥 Speaker Diarization**: Integrated support for SpeechBrain and Pyannote to distinguish between speakers automatically.
- **📊 Dataset Generation**: Seamlessly create ASR training datasets from existing ELAN annotations.
- **🖥️ Dual Interface**: Use the intuitive GUI for ease of use or the powerful CLI for automation.
- **📦 Portable Design**: Designed to be easy to deploy and use in field conditions.

---

## 📥 Installation

### Option 1: Using the Installer (Windows Only) - Recommended
1. Navigate to the [Easper Releases](https://github.com/Aso-UniMelb/Easper/releases).
2. Download the latest `Easper_Setup.exe`.
3. Run the installer and follow the on-screen instructions.

### Option 2: Manual Installation (Development)
1. **Install FFmpeg**: Ensure [FFmpeg 7.1.1+](https://ffmpeg.org/download.html) is installed and added to your system `PATH`.
2. **Install Python**: Python 3.11 or higher is required.
3. **Clone the Repository**:
   ```bash
   git clone https://github.com/Aso-UniMelb/Easper.git
   cd Easper
   ```
4. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🛠️ Usage

### 🖥️ GUI Mode
Simply run the main script without arguments to launch the graphical interface:
```bash
python src/main.py
```

### ⌨️ Command Line Interface

**Transcribe audio to ELAN:**
```bash
python src/main.py transcribe -i audio.wav -m user_models/whisper-small -s 2
```

**Build dataset from ELAN files:**
```bash
python src/main.py dataset -i file.eaf -o ./output -t "Speaker_00,Speaker_01"
```

**Get Help:**
```bash
python src/main.py --help
python src/main.py transcribe --help
python src/main.py dataset --help
```

---

## 📜 License

This project is licensed under the MIT License.