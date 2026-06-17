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

### Option 2: Using the Setup Script (macOS)
1. **Clone the Repository**:
   ```bash
   git clone https://github.com/Aso-UniMelb/Easper.git
   cd Easper
   ```
2. **Run the Setup Script**:
   ```bash
   bash macos/setup.sh
   ```

### Option 3: Manual Installation (Development)
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

**Shortcut (macOS/Linux):**
```bash
bash run-macos.sh
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

## 🔧 Fine-Tuning the Model

After building the zip speech dataset from ELAN files, you can build your own transcription model using Google Colab:

1. **Upload Dataset**: Go to your [Google Drive](https://drive.google.com) and upload the generated dataset `.zip` file into the folder named `Colab` located in the root directory.
2. **Open Colab Notebook**: Open the Google Colab notebook at **[Google Colab Notebook](https://colab.research.google.com/drive/1vRt5T4FHj_z3KHv0_Z4fReHYW8IMOxNv?usp=sharing)** and follow the instructions.
3. **Training & Output**: After 30 to 60 minutes (depending on the dataset length), the trained model will be saved as a `.zip` file in the root folder of your Google Drive.
4. **Deploy Model**:
   - Download the model `.zip` file from Google Drive.
   - Unzip it into the `user_models` folder in the Easper application directory.
5. **Restart Easper**: Restart Easper to see the new model in the list of available models for transcription.

---

## 📜 License

This project is licensed under the MIT License.
