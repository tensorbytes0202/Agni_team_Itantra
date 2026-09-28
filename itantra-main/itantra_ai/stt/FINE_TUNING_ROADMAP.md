# STT Fine-Tuning Roadmap (Phase 3 — after Round 2)

## Why this is NOT in the Round-2 build
Fine-tuning needs 3 things this sandbox genuinely can't provide:
1. A GPU (this environment is CPU-only, no internet to Colab/cloud)
2. A labeled dataset — audio recordings + exact transcriptions of YOUR
   tactical vocabulary (doesn't exist yet, nobody has recorded it)
3. Days of train → evaluate → retrain cycles to know if it actually helped

Instead, Round 2 ships **grammar-constrained decoding** (see stt_engine.py,
`build_grammar_from_vocabulary()`), which gets most of the accuracy benefit
for a closed, ~60-word tactical vocabulary with ZERO training required —
it restricts Vosk's decoder to only choose among your known commands
instead of guessing across the full language.

## When fine-tuning becomes worth it
Grammar-constraining stops being enough once you want to handle:
- Open-ended phrasing outside your fixed keyword list
- Heavy accents / background noise specific to your deployment environment
- New languages beyond what the base model already covers well

## Realistic plan (do this on a laptop with a GPU, or Google Colab free tier)

### Step 1 — Collect data (the actual bottleneck, budget the most time here)
- Record 15-20 people (more speakers = more robust) each saying ~30-50
  tactical phrases from your vocabulary, in Hindi/English/Hinglish mixed
  naturally, in a few different noise conditions (quiet room, some
  background noise).
- Target: 300-1000 short audio clips minimum for a noticeable improvement.
  Use your phone voice recorder - 16kHz mono WAV, but any format works,
  convert with ffmpeg later.
- Write down the exact transcription for each clip. This pairing (audio,
  transcript) is your training dataset.

### Step 2 — Pick what to fine-tune
Recommend **Whisper (via HuggingFace)** over Vosk/Kaldi for fine-tuning -
HuggingFace's `Trainer` API is far better documented and more accessible
than Kaldi's training pipeline, even though Vosk is what you deploy for
inference. A common pattern: fine-tune Whisper for accuracy validation /
offline batch use, keep Vosk (grammar-constrained) for the actual
real-time, low-resource edge deployment.

### Step 3 — Fine-tune (Colab notebook outline)
```python
# pip install transformers datasets accelerate torch soundfile jiwer

from transformers import WhisperProcessor, WhisperForConditionalGeneration
from transformers import Seq2SeqTrainer, Seq2SeqTrainingArguments
from datasets import Dataset, Audio

# 1. Load your collected (audio_path, transcript) pairs into a HF Dataset
data = Dataset.from_dict({
    "audio": [...list of wav file paths...],
    "text": [...matching transcripts...],
})
data = data.cast_column("audio", Audio(sampling_rate=16000))

# 2. Load a small pretrained Whisper checkpoint to fine-tune from
processor = WhisperProcessor.from_pretrained("openai/whisper-small")
model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-small")

# 3. Preprocess: audio -> input features, text -> labels
def prepare(batch):
    audio = batch["audio"]
    batch["input_features"] = processor.feature_extractor(
        audio["array"], sampling_rate=16000).input_features[0]
    batch["labels"] = processor.tokenizer(batch["text"]).input_ids
    return batch

data = data.map(prepare)

# 4. Train
args = Seq2SeqTrainingArguments(
    output_dir="./itantra-whisper-finetuned",
    per_device_train_batch_size=8,
    num_train_epochs=10,       # small dataset -> more epochs is fine
    learning_rate=1e-5,
    fp16=True,                 # needs a GPU
    save_strategy="epoch",
)
trainer = Seq2SeqTrainer(model=model, args=args, train_dataset=data)
trainer.train()
```

### Step 4 — Evaluate
Compute Word Error Rate (WER) on a held-out set of clips NOT used in
training, before vs after fine-tuning, on YOUR vocabulary specifically.
This is the number to put on a future slide - "fine-tuned WER: X% vs
base model WER: Y% on our tactical vocabulary test set."

### Step 5 — Deploy
Export/quantize the fine-tuned model (e.g. to ONNX + int8) before trying
to run it on a phone - an un-quantized fine-tuned Whisper-small is still
too heavy for low-end Android hardware without this step.

## Bottom line for Round 2 Q&A
"Fine-tuning needs a labeled dataset and GPU time we don't have in this
sprint, so we're using grammar-constrained decoding for now - it gets
most of the accuracy benefit for our closed tactical vocabulary with zero
training. Fine-tuning on real recorded field data is our concrete Phase 3
plan, and we already know exactly what pipeline we'd run - it's a data
collection problem at that point, not an unsolved technical one."
