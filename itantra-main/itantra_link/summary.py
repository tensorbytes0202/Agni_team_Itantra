"""
Critical summary + alert detection.

On the low-bitrate link we first send ONLY the critical meaning of a message
(urgency + action + alert flag) in 1 byte, protected by Hamming(7,4) FEC
(-> 14 bits, sent as 2 bytes). The full text follows afterwards.

Detection = existing SemanticExtractor (English keywords) + a small list of
alert words in the 10 PS languages, because STT output for Indic languages
is in native script. This is keyword-based: if no known keyword is present,
there is no summary and only the compressed full text is sent.
"""
from typing import Optional, Tuple

from itantra_ai.semantic.semantic_extractor import SemanticExtractor
from itantra_ai.reliability.hamming import encode_bits, decode_bits
from .location import encode_compact, decode_compact

URGENCY_CODES = ["NONE", "LOW", "HIGH", "CRITICAL"]                 # 2 bits
ACTION_CODES = ["NONE", "SEND", "EVACUATE", "DEPLOY", "HALT",
                "SECURE", "REPORT", "HELP"]                           # 3 bits

# Alert words in the PS languages (native script + common romanized forms).
# Deliberately small and high-precision; extend as testing reveals gaps.
ALERT_WORDS = {
    "CRITICAL": [
        "emergency", "sos", "fire", "flood", "bachao", "aag", "khatra",
        "इमरजेंसी", "बचाओ", "आग", "खतरा", "बाढ़",          # hi / mr
        "આગ", "બચાવો",                                       # gu
        "தீ", "காப்பாற்று", "அவசரம்",                        # ta
        "തീ", "രക്ഷിക്കൂ", "അടിയന്തരം",                      # ml
        "ಬೆಂಕಿ", "ಕಾಪಾಡಿ", "ತುರ್ತು",                          # kn
        "మంటలు", "కాపాడండి", "అత్యవసరం",                     # te
        "আগুন", "বাঁচাও", "জরুরি",                             # bn
        "ନିଆଁ", "ବଞ୍ଚାଅ",                                     # or
    ],
    "HELP": [
        "help", "madad", "मदद", "सहायता", "મદદ", "உதவி",
        "സഹായം", "ಸಹಾಯ", "సహాయం", "সাহায্য", "ସାହାଯ୍ୟ",
    ],
}

_extractor = SemanticExtractor()


def analyze(text: str) -> Tuple[str, str]:
    """Return (urgency, action) using English extractor + multilingual alert words."""
    low = text.lower()
    sem = {}
    try:
        sem = _extractor.extract(text)
    except Exception:
        pass
    urgency = sem.get("URGENCY", "NONE")
    action = sem.get("ACTION", "NONE")

    if any(w in low for w in ALERT_WORDS["CRITICAL"]):
        urgency = "CRITICAL"
    has_help = any(w in low for w in ALERT_WORDS["HELP"])
    if has_help:
        if action in ("NONE", "SEND"):
            action = "HELP"
        if urgency in ("NONE", "LOW"):
            urgency = "HIGH"

    if urgency not in URGENCY_CODES:
        urgency = "HIGH" if urgency == "MEDIUM" else "NONE"
    if action not in ACTION_CODES:
        action = "NONE"
    return urgency, action


def is_alert(urgency: str) -> bool:
    return urgency in ("HIGH", "CRITICAL")


def build_summary(text: str, loc=None) -> Optional[bytes]:
    """
    Without location: 1 data byte  -> Hamming -> 14 bits -> 2 bytes.
    With location:    6 data bytes -> Hamming -> 84 bits -> 11 bytes
                      (1 byte urgency/action/alert + 5 byte compact lat/lon).
    Returns None if nothing critical was found.
    """
    urgency, action = analyze(text)
    if urgency == "NONE" and action == "NONE":
        return None
    alert = 1 if is_alert(urgency) else 0
    bits = (format(URGENCY_CODES.index(urgency), "02b")
            + format(ACTION_CODES.index(action), "03b")
            + str(alert) + "00")                      # 8 bits
    if loc is not None:
        bits += "".join(format(b, "08b") for b in encode_compact(loc))   # +40 bits
    protected = encode_bits(bits)
    nbytes = (len(protected) + 7) // 8
    return int(protected.ljust(nbytes * 8, "0"), 2).to_bytes(nbytes, "big")


def parse_summary(payload: bytes) -> Tuple[str, str, bool, int, Optional[tuple]]:
    """Return (urgency, action, alert, bits_corrected, location or None)."""
    has_loc = len(payload) > 2
    data_len = 48 if has_loc else 8
    prot_len = data_len // 4 * 7
    bits = format(int.from_bytes(payload, "big"), f"0{len(payload)*8}b")[:prot_len]
    data, corrections = decode_bits(bits, data_len)
    urgency = URGENCY_CODES[int(data[0:2], 2)]
    action = ACTION_CODES[int(data[2:5], 2)]
    loc = None
    if has_loc:
        loc = decode_compact(int(data[8:48], 2).to_bytes(5, "big"))
    return urgency, action, data[5] == "1", corrections, loc


def summary_to_text(urgency: str, action: str) -> str:
    phrase = {
        "HELP": "SEND HELP", "SEND": "SEND SUPPORT", "EVACUATE": "EVACUATE",
        "DEPLOY": "DEPLOY TEAM", "HALT": "STOP / HALT", "SECURE": "SECURE AREA",
        "REPORT": "REPORT STATUS", "NONE": "",
    }[action]
    head = {"CRITICAL": "EMERGENCY", "HIGH": "URGENT", "LOW": "INFO", "NONE": ""}[urgency]
    return " - ".join(p for p in (head, phrase) if p) or "MESSAGE"
