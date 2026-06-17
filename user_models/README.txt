========================================================================
Easper - User Models Directory
========================================================================

This directory contains the Whisper models used by Easper for speech transcription. 
If you have just cloned the repository, this directory is empty except for this readme file.

------------------------------------------------------------------------
1. How to get the default Whisper Small model
------------------------------------------------------------------------
To quickly download the standard multilingual "Whisper Small" model:
Run the script `download-whisper-small.py` located in the root folder of Easper:

    python download-whisper-small.py

This will download the model and save it to:
    user_models/whisper-small/

------------------------------------------------------------------------
2. How to use custom / fine-tuned models
------------------------------------------------------------------------
You can fine-tune your own ASR models by following the instructions in the main 
README.md of Easper (under the "Fine-Tuning the Model" section).

Once the Google Colab training completes:
1. Download the generated model `.zip` file from Google Drive.
2. Unzip the file into this folder (`user_models/`).
3. Make sure the files are extracted directly into a subfolder, for example:
   `user_models/my-custom-model/`

------------------------------------------------------------------------
3. Model Folder Structure
------------------------------------------------------------------------
For a model to work correctly with Easper, its subfolder must contain at least 
10 configuration and weight files. Here is a sample structure:

user_models/
└── whisper-small-bis/
    ├── added_tokens.json
    ├── config.json
    ├── generation_config.json
    ├── merges.txt
    ├── model.safetensors
    ├── normalizer.json
    ├── preprocessor_config.json
    ├── special_tokens_map.json
    ├── tokenizer_config.json
    ├── tokenizer.json
    └── vocab.json

------------------------------------------------------------------------
Note: After adding any model, restart Easper to see it in the list of available 
models for transcription.
========================================================================
