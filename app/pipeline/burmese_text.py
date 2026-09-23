"""Myanmar text normalization used by translation, TTS, and subtitles."""
from __future__ import annotations

import re
import unicodedata
import os
from typing import List

try:
    from burmese_tools import tools as _burmese_tools
except Exception:  # Optional during lightweight local development.
    _burmese_tools = None

# Myanmar combining marks/medials must stay attached to the preceding base.
_MYANMAR_MARKS = set("\u102b\u102c\u102d\u102e\u102f\u1030\u1031\u1032\u1033\u1034\u1035\u1036\u1037\u1038\u1039\u103a\u103b\u103c\u103d\u103e\u1056\u1057\u1058\u1059\u105a\u105b\u105c\u105d\u105e\u105f\u1060\u1061\u1062\u1063\u1064\u1065\u1066\u1067\u1068\u1069\u106a\u106b\u106c\u106d\u106e\u106f\u1070\u1071\u1072\u1073\u1074\u1075\u1076\u1077\u1078\u1079\u107a\u107b\u107c\u107d\u107e\u107f\u1080\u1081\u1082\u1083\u1084\u1085\u1086\u1087\u1088\u1089\u108a\u108b\u108c\u108d\u108f\u1090\u1091\u1092\u1093\u1094\u1095\u1096\u1097\u1098\u1099\u109a\u109b\u109c\u109d\u109e\u109f")


def _looks_like_zawgyi(text: str) -> bool:
    """Only enable conversion when the user explicitly marks input as Zawgyi."""
    if not text or _burmese_tools is None:
        return False
    return os.getenv("RECAP_INPUT_ENCODING", "unicode").strip().lower() == "zawgyi"


def normalize_myanmar_text(text: str) -> str:
    """Return NFC Myanmar text; Zawgyi conversion is explicit, never guessed."""
    value = unicodedata.normalize("NFC", str(text or ""))
    if _looks_like_zawgyi(value):
        try:
            value = _burmese_tools.zaw2uni(value)
        except Exception:
            pass
    value = unicodedata.normalize("NFC", value)
    # Never leave whitespace between a Myanmar base and its combining mark.
    value = re.sub(r"(?<=[\u1000-\u109f])\s+(?=[\u102b-\u103e\u1056-\u109f])", "", value)
    value = re.sub(r"\s+([\u102b-\u103e\u1056-\u109f])", r"\1", value)
    return value


def grapheme_clusters(text: str) -> List[str]:
    """Split text without separating Myanmar combining marks from their base."""
    clusters: List[str] = []
    for char in normalize_myanmar_text(text):
        if clusters and (unicodedata.category(char).startswith("M") or char in _MYANMAR_MARKS):
            clusters[-1] += char
        else:
            clusters.append(char)
    return clusters


__all__ = ["normalize_myanmar_text", "grapheme_clusters"]
