"""
Language pack test: zip -> delete unzipped -> unzip on demand, using small
fake model files in a temporary folder (the real models are never touched).
    python -m itantra_ai.tests.test_model_packs
"""
import os
import tempfile

from itantra_ai import model_packs as MP


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def read(path):
    with open(path, "rb") as f:
        return f.read()


def main():
    tmp = tempfile.mkdtemp(prefix="itantra_packs_")
    MP.PACKS_DIR = os.path.join(tmp, "language_packs")
    MP.MODELS_DIRS = {"stt": os.path.join(tmp, "stt"), "tts": os.path.join(tmp, "tts")}
    MP._verified.clear()
    stt, tts = MP.MODELS_DIRS["stt"], MP.MODELS_DIRS["tts"]

    # fake models: Tamil (IndicConformer), Hindi (Vosk), Hindi voice (Piper), Telugu without a zip
    ta_model = os.urandom(3000) + b"\0" * 50000
    write(os.path.join(stt, "indicconformer/ta/model.int8.onnx"), ta_model)
    write(os.path.join(stt, "indicconformer/ta/tokens.txt"), "அ 0\n".encode())
    write(os.path.join(stt, "vosk-model-small-hi-0.22/conf/model.conf"), b"conf")
    write(os.path.join(stt, "vosk-model-small-hi-0.22/am/final.mdl"), b"am" * 1000)
    write(os.path.join(tts, "vits-piper-hi_IN-priyamvada-medium/hi_IN-priyamvada-medium.onnx"), b"v" * 999)
    write(os.path.join(tts, "vits-piper-hi_IN-priyamvada-medium/espeak-ng-data/hi_dict"), b"d" * 99)
    write(os.path.join(stt, "indicconformer/te/model.int8.onnx"), b"te")

    results = []

    def check(name, ok):
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    check("states before zipping", MP.state("stt", "ta") == "ready" and MP.state("stt", "gu") == "missing")

    for part, lang in (("stt", "ta"), ("stt", "hi"), ("tts", "hi")):
        MP.build(part, lang, log=lambda s: None)
    check("build makes zips and keeps unzipped models",
          all(MP.has_zip(p, l) for p, l in (("stt", "ta"), ("stt", "hi"), ("tts", "hi")))
          and MP.is_extracted("stt", "ta"))

    freed = MP.prune({"stt": ["hi"], "tts": ["hi"]}, log=lambda s: None)
    check("prune deletes Tamil STT, keeps selected Hindi",
          freed > 0 and MP.state("stt", "ta") == "zipped" and MP.is_extracted("stt", "hi")
          and MP.is_extracted("tts", "hi"))
    check("prune never deletes a model without a zip (Telugu)", MP.is_extracted("stt", "te"))

    check("unzip on demand", MP.ensure("stt", "ta") and MP.state("stt", "ta") == "ready")
    check("unzipped model is byte-identical",
          read(os.path.join(stt, "indicconformer/ta/model.int8.onnx")) == ta_model)
    check("no temporary folders left", not any(n.startswith(".unzipping") for n in os.listdir(stt)))
    check("ensure on a missing language returns False", MP.ensure("stt", "gu") is False)

    # a damaged zip must never cause the unzipped copy to be deleted
    with open(MP.zip_path("stt", "ta"), "r+b") as f:
        f.seek(200)
        f.write(b"\xff" * 64)
    MP._verified.clear()
    MP.prune({"stt": [], "tts": []}, log=lambda s: None)
    check("damaged zip -> unzipped model kept", MP.is_extracted("stt", "ta"))

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{sum(results)}/{len(results)} passed")
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
