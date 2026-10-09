"""Inventory-gated, single-phone replacement without changing linguistic morae."""
from .models import Hypotheses

LONG_VOWELS = {'A': ('aː',), 'I': ('iː',), 'U': ('ɯː', 'ɨː'), 'E': ('eː',), 'O': ('oː',)}


def derive_hypotheses(target, canonical, phone_index, inventory, compatible_pairs):
    """Pairs must be established by the caller's actual locked phone-set audit."""
    canonical = tuple(canonical)
    # Validate structural inputs before indexing even for unsupported cases.
    Hypotheses(target, canonical, None, phone_index, 'UNSUPPORTED_REDUCED_HYPOTHESIS', ('PENDING',))
    inventory = frozenset(inventory)
    pairs = frozenset(tuple(p) for p in compatible_pairs)
    long = canonical[phone_index]
    short = long[:-1] if long.endswith('ː') else None
    reasons = []
    if not set(canonical) <= inventory: reasons.append('CANONICAL_PHONE_NOT_IN_INVENTORY')
    if long not in LONG_VOWELS[target.vowel_class]: reasons.append('TARGET_NOT_COMPATIBLE_LONG_VOWEL')
    if short is None or short not in inventory: reasons.append('SHORT_COUNTERPART_NOT_IN_INVENTORY')
    if short is None or (long, short) not in pairs: reasons.append('PHONE_SET_COMPATIBILITY_NOT_ESTABLISHED')
    if reasons:
        return Hypotheses(target, canonical, None, phone_index, 'UNSUPPORTED_REDUCED_HYPOTHESIS', tuple(reasons))
    reduced = canonical[:phone_index] + (short,) + canonical[phone_index + 1:]
    return Hypotheses(target, canonical, reduced, phone_index, 'EVIDENCE_AVAILABLE')
