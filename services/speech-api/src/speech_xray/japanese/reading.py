"""The only Sudachi adapter; no MFA tokenizer imports or context guesses."""

import unicodedata
from typing import Protocol

from .models import ReadingPiece, ReadingResult, UnresolvedReason


def normalize_katakana(text: str) -> str:
    """Normalize width/combining marks and hiragana, without deleting unknown text."""
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(chr(ord(char) + 0x60) if "ぁ" <= char <= "ゖ" else char
                   for char in normalized)


class JapaneseReadingProvider(Protocol):
    def reading_for(self, surface: str) -> ReadingResult: ...


class SudachiReadingProvider:
    def __init__(self):
        from sudachipy import dictionary, tokenizer
        self._dictionary = dictionary.Dictionary(dict="core")
        self._tokenizer = self._dictionary.create()
        self._mode = tokenizer.Tokenizer.SplitMode.B

    def reading_for(self, surface: str) -> ReadingResult:
        if not surface.strip():
            return ReadingResult(surface, None, reason=UnresolvedReason.NO_READING,
                                 detail="Empty word surface")
        tokens = self._tokenizer.tokenize(surface, self._mode)
        pieces = tuple(ReadingPiece(token.surface(), normalize_katakana(token.reading_form()),
                                    token.is_oov()) for token in tokens)
        # No guessed fallback for OOVs (including numerals) or lost punctuation/space.
        if not pieces or "".join(piece.surface for piece in pieces) != surface:
            return ReadingResult(surface, None, pieces, UnresolvedReason.NO_READING,
                                 "Sudachi pieces do not exactly cover the MFA word surface")
        if any(piece.is_oov or not piece.reading for piece in pieces):
            return ReadingResult(surface, None, pieces, UnresolvedReason.NO_READING,
                                 "Sudachi returned an OOV or empty reading; no fallback generated")
        reading = "".join(piece.reading for piece in pieces)
        if any(not ("ァ" <= char <= "ヺ" or char == "ー") for char in reading):
            return ReadingResult(surface, None, pieces, UnresolvedReason.NO_READING,
                                 "Sudachi reading contains non-kana characters")
        return ReadingResult(surface, reading, pieces)
