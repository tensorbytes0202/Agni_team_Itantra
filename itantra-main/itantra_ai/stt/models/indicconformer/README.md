# IndicConformer model packs (sherpa-onnx, INT8)

Each language folder needs exactly 2 files:
    <lang>/model.int8.onnx
    <lang>/tokens.txt

Languages: gu (Gujarati), mr (Marathi), kn (Kannada), ml (Malayalam),
ta (Tamil), te (Telugu), or (Odia), bn (Bengali)

Get them from HuggingFace - search "indicconformer sherpa-onnx".
Example source with 8 languages (gu pa bn mr ml te ta kn, ~140MB each):
    https://huggingface.co/mobilebytesensei/betterflow-indicconformer-ctc
Odia (or) needs a separate export - check the same search.

Test one language:
    python3 itantra_ai/stt/stt_engine.py sample.wav ta
