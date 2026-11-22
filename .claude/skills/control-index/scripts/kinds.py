"""Kind keyword table: the single source of truth for control/monument classification.

Edit KEYWORDS as conventions change. Tokens are matched whole-word, case-insensitive,
first against the feature code, then the description. Best (lowest-rank) kind wins.
"""
import re

KEYWORDS = {
    "control": ["CP", "BM", "OPUS", "NGS"],
    "monument": ["ALUMC", "AC", "ACR", "REBAR", "YPC", "RPC", "OPC", "YCR", "RCR", "OCR",
                 "FND", "MAG", "SPIKE", "PK", "MON", "IP"],
}
NGS_PID = re.compile(r"^[A-Z]{2}\d{4}$")  # e.g. RL0523
ORDER = ["control", "monument"]

CONDITIONS = {
    "bent": ["BENT"],
    "broken": ["BROKEN", "BRKN", "BRK"],
    "tipped": ["TIPPED", "LEANING", "TILTED"],
    "disturbed": ["DISTURBED", "DIST", "DISTURB"],
}


def _tokens(text):
    return re.findall(r"[A-Z0-9]+", (text or "").upper())


def _kind_of(tokens):
    for kind in ORDER:
        if any(t in KEYWORDS[kind] for t in tokens) or (kind == "control" and any(NGS_PID.match(t) for t in tokens)):
            return kind
    return None


def classify(feature_code, description):
    return _kind_of(_tokens(feature_code)) or _kind_of(_tokens(description)) or "other"


def condition_flags(recorded):
    toks = set(_tokens(recorded))
    return [flag for flag, words in CONDITIONS.items() if toks & set(words)]
