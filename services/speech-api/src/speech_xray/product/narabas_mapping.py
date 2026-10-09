"""Frozen official whole-sentence phones -> original-domain native target envelope."""
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path

from speech_xray.alignment.models import AlignmentResult, PhoneInterval, WordInterval
from speech_xray.japanese.models import (LongVowelCandidate, LongVowelSpan, MappingBasis, MoraAnalysisResult,
                                        MoraKind, MoraToken, ReadingResult, VowelClass, WordAnalysis)
from .native_boundary import validate_native_segments
from .narabas_runtime import sha256

PHONE_SEQUENCE_SHA256 = "5100b6f9b515fa1c72109100c64cf82d1bea3acf86090283ab5eaa22ab09444d"
PHONE_SEQUENCE_VERSION = "narabas-ja-1.0.0"


class NarabasPhoneRegistry:
    def __init__(self, path):
        if sha256(path) != PHONE_SEQUENCE_SHA256:
            raise ValueError("NARABAS_PHONE_SEQUENCE_CHANGED")
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload["phone_sequence_version"] != PHONE_SEQUENCE_VERSION:
            raise ValueError("NARABAS_PHONE_SEQUENCE_VERSION_MISMATCH")
        self.rows = {row["id"]:row for row in payload["entries"]}

    def resolve(self, identifier, text):
        row = self.rows[identifier]
        if row["text"] != text:
            raise ValueError("NARABAS_FROZEN_TRANSCRIPT_MISMATCH")
        return row


def map_native(row, segments, duration_ms, source):
    word_index = row["target_word_index"]
    indices = row["target_phone_indices"]
    native = validate_native_segments(segments,row["phone_sequence"],duration_ms,indices,
                                       row["words"][word_index]["phone_indices"])
    words, mapped_words = [], []
    for index, word in enumerate(row["words"]):
        first, last = native[word["phone_indices"][0]][0], native[word["phone_indices"][-1]][1]
        words.append(WordInterval(word["surface"],first,last))
        mapped_words.append(WordAnalysis(index,index,word["surface"],
            ReadingResult(word["surface"],word["reading"],source="FROZEN_OFFICIAL_PYOPENJTALK_0_3_0"),
            first,last,tuple(word["mora_indices"]),tuple(word["phone_indices"]),"MAPPED",()))
    alignment = AlignmentResult(source,Decimal(0),duration_ms,tuple(words),
                                tuple(PhoneInterval(label,start,end) for start,end,label in native))
    morae = [MoraToken(m["index"],m["word_index"],m["word_mora_index"],m["text"],m["reading"],
                      MoraKind(m["kind"]),VowelClass(m["vowel_class"]) if m["vowel_class"] else None)
             for m in row["morae"]]
    pair = tuple(row["target_mora_indices"])
    span_id, candidate_id = "native-target-envelope-01", "native-target-candidate-01"
    for index in pair:
        morae[index] = replace(morae[index],long_vowel_span_ids=(span_id,))
    vowel = VowelClass(row["vowel"].upper())
    span = LongVowelSpan(span_id,candidate_id,word_index,indices[0],row["vowel"]+"ː",
                        native[indices[0]][0],native[indices[1]][1],pair,vowel,MappingBasis.PROLONGED_MARK,
                        tuple(indices),tuple(native[i][2] for i in indices))
    candidate = LongVowelCandidate(candidate_id,word_index,pair,vowel,MappingBasis.PROLONGED_MARK,span_id)
    mora = MoraAnalysisResult(source,tuple(mapped_words),tuple(morae),(candidate,),(span,),(),"NARABAS_JA_1_0_0")
    return alignment,mora
