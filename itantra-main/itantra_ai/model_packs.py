"""
Language packs: every STT / TTS model is stored as a compressed zip and is
unzipped only when that language is selected. Keeps the prototype small on
disk (the same idea as the Android "language packs").

    language_packs/stt-<lang>.zip   -> unzipped into itantra_ai/stt/models/
    language_packs/tts-<lang>.zip   -> unzipped into itantra_ai/tts/models/

Zips use LZMA (measured: IndicConformer INT8 140 MB -> ~76 MB, unzip ~5 s).

    python -m itantra_ai.model_packs status             # what is zipped / unzipped
    python -m itantra_ai.model_packs build [langs]      # zip the unzipped models (safe, keeps them)
    python -m itantra_ai.model_packs prune [keep langs] # delete unzipped models that have a zip
    python -m itantra_ai.model_packs extract ta         # unzip one language by hand

Safety rule: an unzipped model is deleted ONLY if its zip exists and passes
the CRC check, so a model can never be lost.
"""
import os
import shutil
import sys
import threading
import zipfile
from typing import Callable, Dict, Iterable, Optional

ROOT = os.path.dirname(os.path.abspath(__file__))
PACKS_DIR = os.path.join(os.path.dirname(ROOT), "language_packs")
MODELS_DIRS = {"stt": os.path.join(ROOT, "stt", "models"),
               "tts": os.path.join(ROOT, "tts", "models")}
LANGS = ["en", "hi", "gu", "mr", "kn", "ml", "ta", "te", "or", "bn"]
NAMES = {"en": "English", "hi": "Hindi", "gu": "Gujarati", "mr": "Marathi", "kn": "Kannada",
         "ml": "Malayalam", "ta": "Tamil", "te": "Telugu", "or": "Odia", "bn": "Bengali"}

_lock = threading.Lock()          # one unzip at a time inside this process
_verified = set()                 # zips already CRC-checked in this process


def model_folder(part: str, lang: str) -> str:
    """Folder (relative to that part's models dir) holding the model for `lang`."""
    if part == "stt":
        from itantra_ai.stt.stt_engine import LANGUAGE_ROUTING
        backend, model_id = LANGUAGE_ROUTING[lang]
        return model_id if backend == "vosk" else f"indicconformer/{model_id}"
    from itantra_ai.tts.tts_engine import VOICES
    return VOICES[lang][1]


def _key_file(part: str, lang: str) -> str:
    """A file that exists only when the model is fully unzipped."""
    folder = model_folder(part, lang)
    if part == "tts":
        from itantra_ai.tts.tts_engine import VOICES
        return os.path.join(folder, VOICES[lang][2])
    if folder.startswith("indicconformer/"):
        return os.path.join(folder, "model.int8.onnx")
    return os.path.join(folder, "conf", "model.conf")          # every Vosk model has this


def zip_path(part: str, lang: str) -> str:
    return os.path.join(PACKS_DIR, f"{part}-{lang}.zip")


def is_extracted(part: str, lang: str) -> bool:
    return os.path.isfile(os.path.join(MODELS_DIRS[part], _key_file(part, lang)))


def has_zip(part: str, lang: str) -> bool:
    return os.path.isfile(zip_path(part, lang))


def available(part: str, lang: str) -> bool:
    """True if the model can be used (already unzipped, or a zip exists)."""
    return is_extracted(part, lang) or has_zip(part, lang)


def state(part: str, lang: str) -> str:
    if is_extracted(part, lang):
        return "ready"
    return "zipped" if has_zip(part, lang) else "missing"


def _size(path: str) -> int:
    if os.path.isfile(path):
        return os.path.getsize(path)
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(path) for f in fs)


# --------------------------------------------------------------------- unzip
def ensure(part: str, lang: str, progress: Optional[Callable[[str], None]] = None) -> bool:
    """Make sure the model is unzipped. Returns True if it is ready afterwards."""
    if is_extracted(part, lang):
        return True
    if not has_zip(part, lang):
        return False
    say = progress or (lambda s: None)
    with _lock:
        if is_extracted(part, lang):
            return True
        models = MODELS_DIRS[part]
        folder = model_folder(part, lang)
        target = os.path.join(models, folder)
        tmp = os.path.join(models, f".unzipping-{part}-{lang}-{os.getpid()}")
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            with zipfile.ZipFile(zip_path(part, lang)) as z:
                items = z.infolist()
                total = sum(i.file_size for i in items) or 1
                done = 0
                say(f"unzipping {part}-{lang}.zip ({total / 1e6:.0f} MB)...")
                for i in items:
                    z.extract(i, tmp)
                    done += i.file_size
                    if i.file_size > 5_000_000:
                        say(f"unzipping {part}-{lang}: {100 * done // total}%")
            # move into place only when complete, so a half-unzipped model is never used
            src = os.path.join(tmp, folder)
            if not os.path.isdir(src):
                raise RuntimeError(f"{zip_path(part, lang)} does not contain '{folder}/'")
            if os.path.isdir(target):                     # stale partial copy
                shutil.rmtree(target, ignore_errors=True)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try:
                os.replace(src, target)
            except OSError:
                if not is_extracted(part, lang):          # another process won the race -> fine
                    raise
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    say(f"{part}-{lang} ready")
    return is_extracted(part, lang)


# --------------------------------------------------------------------- zip
def build(part: str, lang: str, log: Callable[[str], None] = print) -> bool:
    """Zip an unzipped model into language_packs/. Never deletes anything."""
    if not is_extracted(part, lang):
        return False
    if has_zip(part, lang):
        log(f"  {part}-{lang}: zip already exists, skipped")
        return True
    models = MODELS_DIRS[part]
    folder = model_folder(part, lang)
    os.makedirs(PACKS_DIR, exist_ok=True)
    out = zip_path(part, lang)
    tmp = out + ".partial"
    log(f"  {part}-{lang}: zipping {folder} ({_size(os.path.join(models, folder)) / 1e6:.0f} MB)...")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_LZMA) as z:
        for d, _, files in os.walk(os.path.join(models, folder)):
            for f in files:
                full = os.path.join(d, f)
                z.write(full, os.path.relpath(full, models).replace(os.sep, "/"))
    os.replace(tmp, out)
    log(f"  {part}-{lang}: {os.path.getsize(out) / 1e6:.0f} MB zip")
    return True


def _zip_ok(part: str, lang: str) -> bool:
    p = zip_path(part, lang)
    if p in _verified:
        return True
    try:
        with zipfile.ZipFile(p) as z:
            names = set(z.namelist())
            ok = z.testzip() is None and _key_file(part, lang).replace(os.sep, "/") in names
    except Exception:                  # BadZipFile, OSError, LZMAError, EOFError ... = damaged
        ok = False
    if ok:
        _verified.add(p)
    return ok


# --------------------------------------------------------------------- free space
def prune(keep: Dict[str, Iterable[str]], log: Callable[[str], None] = print) -> int:
    """
    Delete unzipped models not in `keep` (e.g. {"stt": ["ta"], "tts": ["ta", "en"]}),
    but only when a verified zip exists. Returns bytes freed.
    Files still open by another program (Windows) are skipped, not an error.
    """
    freed = 0
    for part in ("stt", "tts"):
        wanted = set(keep.get(part, ()))
        for lang in LANGS:
            if lang in wanted or not is_extracted(part, lang) or not has_zip(part, lang):
                continue
            if not _zip_ok(part, lang):
                log(f"[packs] {part}-{lang}.zip failed its check, keeping the unzipped model")
                continue
            path = os.path.join(MODELS_DIRS[part], model_folder(part, lang))
            size = _size(path)
            shutil.rmtree(path, ignore_errors=True)
            if not os.path.exists(path):
                freed += size
            else:
                log(f"[packs] {part}-{lang} is in use, will remove later")
    return freed


def status_table() -> str:
    rows = [f"{'lang':<14}{'STT':<9}{'TTS':<9}"]
    for lang in LANGS:
        rows.append(f"{lang} {NAMES[lang]:<11}{state('stt', lang):<9}{state('tts', lang):<9}")
    zipped = sum(os.path.getsize(os.path.join(PACKS_DIR, f)) for f in os.listdir(PACKS_DIR)
                 if f.endswith(".zip")) if os.path.isdir(PACKS_DIR) else 0
    unzipped = sum(_size(os.path.join(MODELS_DIRS[p], model_folder(p, l)))
                   for p in ("stt", "tts") for l in LANGS if is_extracted(p, l))
    rows.append(f"zips: {zipped / 1e6:.0f} MB   unzipped models: {unzipped / 1e6:.0f} MB")
    return "\n".join(rows)


if __name__ == "__main__":
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else "status"), sys.argv[2:]
    if cmd == "build":
        for lang in args or LANGS:
            for part in ("stt", "tts"):
                build(part, lang)
        print(status_table())
    elif cmd == "prune":
        freed = prune({"stt": args, "tts": args})
        print(f"freed {freed / 1e6:.0f} MB")
        print(status_table())
    elif cmd == "extract":
        for lang in args:
            for part in ("stt", "tts"):
                print(f"{part}-{lang}: {'ready' if ensure(part, lang, print) else 'no zip'}")
    else:
        print(status_table())
