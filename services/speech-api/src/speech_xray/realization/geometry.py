"""Identity from exported phones; geometry from observed intervals only."""
from decimal import Decimal
from speech_xray.alignment.models import exact_subtract


def selection(phones, hypotheses):
    if phones is None:
        return {'selected': 'ALIGNMENT_FAILED', 'identity_status': 'ALIGNMENT_FAILED'}
    sequence = tuple(phones)
    matches = []
    if sequence == hypotheses.canonical: matches.append('CANONICAL_SELECTED')
    if hypotheses.reduced is not None and sequence == hypotheses.reduced: matches.append('REDUCED_SELECTED')
    if len(matches) != 1 or hypotheses.reduced is None:
        return {'selected': 'AMBIGUOUS_OR_UNRESOLVED', 'identity_status': 'AMBIGUOUS_VARIANT_IDENTITY'}
    return {'selected': matches[0], 'identity_status': 'UNIQUE_EXPORTED_PHONE_SEQUENCE'}


def observe(alignment, hypotheses):
    """Word index refers to non-empty lexical intervals, as in accepted mora models.

    Silence intervals are retained as immediate acoustic neighbors. A phone
    straddling a lexical boundary is unresolved, never assigned heuristically.
    """
    bounds = (alignment.start_ms, alignment.end_ms)
    if any(not isinstance(x, Decimal) or not x.is_finite() for x in bounds) or bounds[0] < 0 or bounds[1] <= bounds[0]:
        raise ValueError('INVALID_EXPERIMENT_INPUT: alignment domain')
    for tier in (alignment.words, alignment.phones):
        previous = bounds[0]
        for item in tier:
            if (not all(isinstance(x, Decimal) and x.is_finite() for x in (item.start_ms, item.end_ms))
                    or item.start_ms < previous or item.end_ms <= item.start_ms or item.end_ms > bounds[1]):
                raise ValueError('INVALID_EXPERIMENT_INPUT: interval order/domain')
            previous = item.end_ms
    words = [w for w in alignment.words if w.label]
    index = hypotheses.target.word_index
    if index >= len(words) or words[index].label != hypotheses.target.surface:
        raise ValueError('AMBIGUOUS_VARIANT_IDENTITY: target word changed')
    word = words[index]
    overlap = [(i, p) for i, p in enumerate(alignment.phones)
               if p.end_ms > word.start_ms and p.start_ms < word.end_ms]
    if not overlap or any(p.start_ms < word.start_ms or p.end_ms > word.end_ms or not p.label for _, p in overlap):
        raise ValueError('AMBIGUOUS_VARIANT_IDENTITY: phone/word containment')
    sequence = tuple(p.label for _, p in overlap)
    ident = selection(sequence, hypotheses)
    if ident['selected'] not in ('CANONICAL_SELECTED', 'REDUCED_SELECTED'):
        raise ValueError('AMBIGUOUS_VARIANT_IDENTITY: unexpected exported sequence')
    phone_index, phone = overlap[hypotheses.phone_index]
    previous = alignment.phones[phone_index - 1] if phone_index else None
    following = alignment.phones[phone_index + 1] if phone_index + 1 < len(alignment.phones) else None
    return {'source': alignment.source, 'word_label': word.label,
        'phone_sequence': list(sequence), **ident,
        'word_start_ms': word.start_ms, 'word_end_ms': word.end_ms,
        'word_phones': [p.to_dict() for _, p in overlap],
        'target_phone': phone.to_dict(), 'phone_start_ms': phone.start_ms,
        'phone_end_ms': phone.end_ms, 'phone_duration_ms': phone.duration_ms,
        'previous_phone': previous.to_dict() if previous else None,
        'next_phone': following.to_dict() if following else None,
        'previous_phone_end_ms': previous.end_ms if previous else None,
        'next_phone_start_ms': following.start_ms if following else None,
        'previous_word_end_ms': words[index-1].end_ms if index else None,
        'next_word_start_ms': words[index+1].start_ms if index+1 < len(words) else None}


BOUNDARIES = ('word_start_ms', 'word_end_ms', 'phone_start_ms', 'phone_end_ms',
              'previous_phone_end_ms', 'next_phone_start_ms', 'previous_word_end_ms', 'next_word_start_ms')


def paired_displacements(canonical, reduced):
    if canonical is None or reduced is None:
        return None
    if canonical['word_label'] != reduced['word_label']:
        raise ValueError('INVALID_EXPERIMENT_INPUT: paired lexical identity')
    shifts = {key: exact_subtract(reduced[key], canonical[key]) if canonical[key] is not None and reduced[key] is not None else None for key in BOUNDARIES}
    shifts['target_duration_difference_ms'] = exact_subtract(reduced['phone_duration_ms'], canonical['phone_duration_ms'])
    for side in ('previous_phone', 'next_phone'):
        a, b = canonical[side], reduced[side]
        shifts[side + '_identity_preserved'] = a['label'] == b['label'] if a and b else None
        for field in ('start_ms', 'end_ms', 'duration_ms'):
            shifts[side + '_' + field + '_shift'] = exact_subtract(b[field], a[field]) if a and b and a['label'] == b['label'] else None
    return {'sign_convention': 'REDUCED_MINUS_CANONICAL', 'shifts': shifts}
