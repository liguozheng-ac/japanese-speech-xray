"""Deterministic, isolated target overrides; preserve all other lines byte-for-byte."""
from decimal import Decimal
import unicodedata
from .models import token

CONDITIONS = ('CANONICAL_ONLY', 'REDUCED_ONLY', 'COMPETITION_EQUAL_PRIOR')


def normalized_word(word):
    return unicodedata.normalize('NFKC', word).lower()


def override_lexicon(original, hypotheses, condition, silence_fields=()):
    """Explicit 1.0 weights give identical zero pronunciation costs in locked MFA.

    Shared silence fields are retained from the accepted canonical entry. The
    caller must audit the installed compiler's semantics; these are lexicon
    weights, never calibrated realization probabilities.
    """
    if condition not in CONDITIONS or hypotheses.reduced is None:
        raise ValueError('INVALID_EXPERIMENT_INPUT: unsupported lexicon condition')
    if len(silence_fields) not in (0, 3):
        raise ValueError('INVALID_EXPERIMENT_INPUT: silence fields')
    if silence_fields:
        values = [Decimal(x) for x in silence_fields]
        if (not all(v.is_finite() and v > 0 for v in values) or values[0] >= 1
                or not all(token(x) for x in silence_fields)):
            raise ValueError('INVALID_EXPERIMENT_INPUT: silence metadata')
    word = hypotheses.target.surface
    kept, removed = [], []
    for raw in original.splitlines(keepends=True):
        text = raw.decode('utf-8-sig').strip()
        if text and normalized_word(text.split()[0]) == normalized_word(word):
            removed.append(text)
        else:
            kept.append(raw)
    if not removed:
        raise ValueError('INVALID_EXPERIMENT_INPUT: lexical item absent from original')
    prefix = b''.join(kept)
    if prefix and not prefix.endswith((b'\n', b'\r')):
        raise ValueError('INVALID_EXPERIMENT_INPUT: missing final line separator')
    variants = (hypotheses.canonical,) if condition == CONDITIONS[0] else (hypotheses.reduced,) if condition == CONDITIONS[1] else (hypotheses.canonical, hypotheses.reduced)
    metadata = '\t'.join(('1.0', *silence_fields))
    entries = [f'{word}\t{metadata}\t{" ".join(phones)}\n' for phones in variants]
    return prefix + ''.join(entries).encode('utf-8'), {
        'override_kind': 'EXPERIMENTAL_LEXICON_OVERRIDE', 'condition': condition,
        'removed_original_entries': removed, 'experimental_entries': entries,
        'pronunciation_weights': ['1.0'] * len(variants),
        'equal_cost_basis': 'ABS_LOG_1_EQUALS_ZERO',
        'non_target_bytes_preserved': True, 'shared_silence_fields': list(silence_fields)}
