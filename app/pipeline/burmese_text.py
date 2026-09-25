"""Myanmar text normalization used by translation, TTS, and subtitles."""
from __future__ import annotations

import re
import unicodedata
import os
from typing import List

_BURMESE_DIGITS = str.maketrans("0123456789", "၀၁၂၃၄၅၆၇၈၉")
_DIGIT_VALUES = str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789")
_NUMBER_WORDS = ("သုည", "တစ်", "နှစ်", "သုံး", "လေး", "ငါး", "ခြောက်", "ခုနစ်", "ရှစ်", "ကိုး")

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


def normalize_burmese_digits(text: str) -> str:
    """Use Myanmar digits for standalone numbers, preserving English phrases."""
    value = str(text or "")

    # Keep identifiers and English phrases such as COVID-19, H1N1, MP4 and
    # 5G intact. Only standalone numeric tokens are converted to Myanmar
    # digits; the TTS layer must not spell them out as Burmese number words.
    protected_pattern = re.compile(
        r"[A-Za-z][A-Za-z0-9._/-]*\d[A-Za-z0-9._/-]*"
        r"|\d+[A-Za-z][A-Za-z0-9._/-]*"
    )
    protected = []

    def hold(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        # Encode the index as a private-use character so digit normalization
        # cannot alter the marker itself.
        return f"\uE000{chr(0xE100 + len(protected) - 1)}\uE001"

    value = protected_pattern.sub(hold, value)
    # Remove thousands separators from numeric tokens so 1,000 becomes
    # ၁၀၀၀ rather than ၁,၀၀၀. Commas used as normal sentence punctuation
    # remain untouched.
    value = re.sub(
        r"(?<![A-Za-z0-9])\d[\d,]*(?:\.\d+)?(?![A-Za-z0-9])",
        lambda match: match.group(0).replace(",", ""),
        value,
    )
    value = value.translate(_BURMESE_DIGITS)
    for index, original in enumerate(protected):
        value = value.replace(f"\uE000{chr(0xE100 + index)}\uE001", original)
    return value


def _under_thousand_to_burmese(number: int) -> str:
    parts = []
    hundreds, remainder = divmod(number, 100)
    if hundreds:
        parts.append(_NUMBER_WORDS[hundreds] + "ရာ")
        if remainder:
            parts[-1] += "့"
    if remainder:
        tens, ones = divmod(remainder, 10)
        if tens:
            parts.append("ဆယ်" if tens == 1 else _NUMBER_WORDS[tens] + "ဆယ်")
            if ones:
                parts[-1] += "့"
        if ones:
            parts.append(_NUMBER_WORDS[ones])
    return "".join(parts) or _NUMBER_WORDS[0]


def burmese_number_to_words(number: int) -> str:
    """Spell an integer in natural Burmese words for speech synthesis."""
    number = int(number)
    if number == 0:
        return _NUMBER_WORDS[0]
    if number < 0:
        return "အနုတ်" + burmese_number_to_words(-number)
    parts = []
    for divisor, label in ((1_000_000_000, "ဘီလီယံ"), (1_000_000, "သန်း"), (1_000, "ထောင်"), (1, "")):
        amount, number = divmod(number, divisor)
        if amount:
            if divisor == 1:
                parts.append(_under_thousand_to_burmese(amount))
            else:
                parts.append(_under_thousand_to_burmese(amount) + label)
                if number:
                    parts[-1] += "့"
    return "".join(parts)


def prepare_burmese_tts_text(text: str) -> str:
    """Replace numeric tokens with Burmese words before Edge TTS/VoxCPM input."""
    value = normalize_myanmar_text(text)
    value = value.translate(_DIGIT_VALUES)

    def replace(match):
        token = match.group(0).replace(",", "")
        if "." in token:
            whole, fraction = token.split(".", 1)
            return burmese_number_to_words(int(whole or 0)) + " ဒသမ " + " ".join(_NUMBER_WORDS[int(d)] for d in fraction)
        return burmese_number_to_words(int(token))

    return re.sub(r"(?<![A-Za-z])\d+(?:\.\d+)?", replace, value)


def grapheme_clusters(text: str) -> List[str]:
    """Split text without separating Myanmar combining marks from their base."""
    clusters: List[str] = []
    for char in normalize_myanmar_text(text):
        if clusters and (unicodedata.category(char).startswith("M") or char in _MYANMAR_MARKS):
            clusters[-1] += char
        else:
            clusters.append(char)
    return clusters


__all__ = ["normalize_myanmar_text", "normalize_burmese_digits", "burmese_number_to_words", "prepare_burmese_tts_text", "grapheme_clusters"]
