"""Explicit kana and Japanese MFA v3.0.0 inventory adapters."""

from .models import VowelClass

# The kana table is our linguistic rule; it is not an MFA phone inventory.
KANA_VOWELS = {
    kana: vowel for vowel, kana_row in (
        (VowelClass.A, "アカガサザタダナハバパマヤラワ"),
        (VowelClass.I, "イキギシジチヂニヒビピミリヰ"),
        (VowelClass.U, "ウクグスズツヅヌフブプムユルヴ"),
        (VowelClass.E, "エケゲセゼテデネヘベペメレヱ"),
        (VowelClass.O, "オコゴソゾトドノホボポモヨロヲ"),
    ) for kana in kana_row
}

# Verified against japanese_mfa/meta.json in the already installed acoustic ZIP.
SHORT_VOWELS = {
    "a": VowelClass.A, "i": VowelClass.I, "i̥": VowelClass.I,
    "e": VowelClass.E, "o": VowelClass.O,
    "ɨ": VowelClass.U, "ɨ̥": VowelClass.U,
    "ɯ": VowelClass.U, "ɯ̥": VowelClass.U,
}
LONG_VOWELS = {
    "aː": VowelClass.A, "iː": VowelClass.I, "eː": VowelClass.E,
    "oː": VowelClass.O, "ɨː": VowelClass.U, "ɯː": VowelClass.U,
}
CONSONANTS = frozenset("""
b bʲ bʲː bː c cː d dz dzː dʑ dʑː dʲ dʲː dː h hː j k kː
m mʲ mʲː mː n nː p pʲ pʲː pː s sː t ts tsː tɕ tɕː tʲ tʲː tː
v vʲ w wː z ç çː ŋ ɕ ɕː ɟ ɟː ɡ ɡː ɰ̃ ɲ ɲː ɴ ɴː
ɸ ɸʲ ɸʲː ɸː ɾ ɾʲ ɾʲː ɾː ʑ ʔ
""".split())
SILENCE_PHONES = frozenset({"", "sil", "sp"})
SUPPORTED_SPEECH_PHONES = frozenset(SHORT_VOWELS) | frozenset(LONG_VOWELS) | CONSONANTS


def phone_vowel_class(label: str) -> VowelClass | None:
    return SHORT_VOWELS.get(label) or LONG_VOWELS.get(label)


def is_long_vowel_phone(label: str) -> bool:
    return label in LONG_VOWELS
