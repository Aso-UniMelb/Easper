from transformers import WhisperProcessor, WhisperForConditionalGeneration
import os

model_id = "openai/whisper-small"
processor = WhisperProcessor.from_pretrained(model_id)
model = WhisperForConditionalGeneration.from_pretrained(model_id)

save_dir = "user_models/whisper-small"
# make dir if not exist
os.makedirs(save_dir, exist_ok=True)
processor.save_pretrained(save_dir)
model.save_pretrained(save_dir)