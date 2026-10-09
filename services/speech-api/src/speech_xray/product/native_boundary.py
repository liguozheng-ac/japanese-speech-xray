"""Keep native intervals intact; reject structurally unusable forced alignments."""
from decimal import Decimal, InvalidOperation


class BoundaryUnusable(ValueError):
    pass


def validate_native_segments(segments, sequence, duration_ms, target_indices, word_indices):
    if not isinstance(segments, (list, tuple)) or any(
            not isinstance(item, (list, tuple)) or len(item) != 3
            or not isinstance(item[2], str) for item in segments):
        raise BoundaryUnusable("MALFORMED_NATIVE_SEGMENT")
    if [item[2] for item in segments] != list(sequence):
        raise BoundaryUnusable("INCOMPLETE_PHONE_SEQUENCE")
    previous = Decimal(0)
    native = []
    for raw_start, raw_end, label in segments:
        try:
            start, end = Decimal(str(raw_start))*1000, Decimal(str(raw_end))*1000
        except InvalidOperation as error:
            raise BoundaryUnusable("MALFORMED_NATIVE_TIMESTAMP") from error
        if not start.is_finite() or not end.is_finite():
            raise BoundaryUnusable("NONFINITE_BOUNDARY")
        if start >= end:
            raise BoundaryUnusable("NONPOSITIVE_NATIVE_PHONE")
        if start < previous:
            raise BoundaryUnusable("NONMONOTONIC_NATIVE_PHONE")
        if start < 0 or end > duration_ms:
            raise BoundaryUnusable("NATIVE_PHONE_OUTSIDE_ORIGINAL_AUDIO")
        native.append((start, end, label))
        previous = end
    if (len(target_indices) != 2 or target_indices[1] != target_indices[0]+1
            or not word_indices or any(i < 0 or i >= len(native) for i in (*target_indices, *word_indices))
            or not set(target_indices) <= set(word_indices)):
        raise BoundaryUnusable("TARGET_OR_WORD_PHONE_INDICES_INVALID")
    first, second = (native[i] for i in target_indices)
    if first[2] != second[2] or first[2] not in "aiueo" or first[1] != second[0]:
        raise BoundaryUnusable("TARGET_NATIVE_VOWEL_PAIR_MISMATCH")
    return tuple(native)
