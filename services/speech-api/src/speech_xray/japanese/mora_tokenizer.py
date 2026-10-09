"""Deterministic kana morae; small kana combine only through explicit rules."""

from .models import (MoraKind, MoraToken, MoraTokenization, TokenizationIssue,
                     UnresolvedReason, VowelClass)
from .reading import normalize_katakana
from .vowel import KANA_VOWELS

YOON_COMBINATIONS = {
    base + small: vowel for base in "キギシジチヂニヒビピミリ"
    for small, vowel in (("ャ", VowelClass.A), ("ュ", VowelClass.U), ("ョ", VowelClass.O))
}
LOANWORD_COMBINATIONS = {
    combination: vowel for vowel, row in (
        (VowelClass.A, "クァ グァ ファ ヴァ クヮ グヮ ツァ"),
        (VowelClass.I, "ティ ディ フィ ヴィ ウィ クィ グィ ツィ"),
        (VowelClass.U, "テュ デュ フュ ヴュ トゥ ドゥ"),
        (VowelClass.E, "イェ ウェ クェ グェ シェ ジェ チェ ツェ フェ ヴェ"),
        (VowelClass.O, "ウォ クォ グォ ツォ フォ ヴォ"),
    ) for combination in row.split()
}
COMBINATIONS = YOON_COMBINATIONS | LOANWORD_COMBINATIONS


def tokenize_mora(reading: str, word_index: int = 0, start_index: int = 0) -> MoraTokenization:
    normalized = normalize_katakana(reading)
    morae = []
    offset = 0
    if not normalized:
        return MoraTokenization(normalized, (), TokenizationIssue(
            UnresolvedReason.NO_READING, 0, "", "Empty reading"))
    while offset < len(normalized):
        char = normalized[offset]
        pair = normalized[offset:offset + 2]
        kind = MoraKind.NORMAL
        vowel = None
        width = 1
        if pair in COMBINATIONS:
            text, vowel, width = pair, COMBINATIONS[pair], 2
        elif char in KANA_VOWELS:
            text, vowel = char, KANA_VOWELS[char]
        elif char in {"ン", "ッ"}:
            text = char
            kind = MoraKind.MORAIC_NASAL if char == "ン" else MoraKind.GEMINATE
        elif char == "ー":
            if not morae or morae[-1].vowel_class is None:
                return MoraTokenization(normalized, tuple(morae), TokenizationIssue(
                    UnresolvedReason.INVALID_PROLONGED_MARK, offset, char,
                    "Prolonged mark needs a preceding vowel-bearing mora"))
            text, vowel, kind = char, morae[-1].vowel_class, MoraKind.LONG_VOWEL_EXTENSION
        else:
            return MoraTokenization(normalized, tuple(morae), TokenizationIssue(
                UnresolvedReason.UNSUPPORTED_KANA, offset, char,
                "Unsupported character or incompatible small-kana combination"))
        morae.append(MoraToken(start_index + len(morae), word_index, len(morae),
                               text, text, kind, vowel))
        offset += width
    return MoraTokenization(normalized, tuple(morae))
