"""Conservative word-local, ordered vowel-nucleus mapping; no invented boundaries."""

from dataclasses import replace

from speech_xray.alignment.models import AlignmentResult
from .alignment_input import validate_alignment
from .models import (LongVowelCandidate, LongVowelSpan, MappingBasis, MoraAnalysisResult,
                     MoraKind, UnresolvedItem, UnresolvedReason as Reason, VowelClass,
                     WordAnalysis)
from .mora_tokenizer import tokenize_mora
from .reading import JapaneseReadingProvider
from .vowel import (SILENCE_PHONES, SUPPORTED_SPEECH_PHONES,
                    is_long_vowel_phone, phone_vowel_class)

KANA_LONG_ENDINGS = {
    VowelClass.A: frozenset({"ア"}), VowelClass.I: frozenset({"イ"}),
    VowelClass.U: frozenset({"ウ"}), VowelClass.E: frozenset({"エ", "イ"}),
    VowelClass.O: frozenset({"オ", "ウ"}),
}


def long_vowel_candidates(morae) -> tuple[LongVowelCandidate, ...]:
    candidates = []
    for first, second in zip(morae, morae[1:]):
        if (first.word_index != second.word_index or second.index != first.index + 1
                or first.kind != MoraKind.NORMAL or first.vowel_class is None):
            continue
        if second.kind == MoraKind.LONG_VOWEL_EXTENSION:
            basis = MappingBasis.PROLONGED_MARK
        elif (second.kind == MoraKind.NORMAL
              and second.text in KANA_LONG_ENDINGS[first.vowel_class]):
            basis = MappingBasis.KANA_SEQUENCE
        else:
            continue
        indices = (first.index, second.index)
        candidates.append(LongVowelCandidate(
            f"candidate_w{first.word_index}_m{first.index}_{second.index}",
            first.word_index, indices, first.vowel_class, basis))
    return tuple(candidates)


def _ordered_pairs(morae, candidates, vowel_phones):
    """Require full word vowel coverage, with no deletions/reordering or class guessing.

    Short vowels consume one vowel-bearing mora; a long vowel consumes exactly an
    adjacent, explicitly established two-mora candidate. N/ッ have no vowel and
    are excluded from this skeleton, but cannot be crossed by a candidate. This
    does not align consonants, nasals or geminates or verify pronunciation.
    """
    nuclei = [mora for mora in morae if mora.vowel_class is not None]
    pairs = {candidate.mora_indices: candidate for candidate in candidates}
    cursor = 0
    mappings = []
    for phone_index, phone in vowel_phones:
        vowel = phone_vowel_class(phone.label)
        if cursor >= len(nuclei):
            return (), Reason.VOWEL_SEQUENCE_MISMATCH, "Extra aligned vowel nucleus"
        if is_long_vowel_phone(phone.label):
            indices = tuple(mora.index for mora in nuclei[cursor:cursor + 2])
            candidate = pairs.get(indices)
            if candidate is None:
                return (), Reason.NO_LONG_VOWEL_CANDIDATE, "Long phone has no adjacent candidate at its ordered position"
            if candidate.vowel_class != vowel:
                return (), Reason.VOWEL_CLASS_MISMATCH, f"Candidate {candidate.vowel_class} differs from phone {vowel} at p{phone_index}"
            mappings.append((candidate, phone_index, phone))
            cursor += 2
        else:
            if nuclei[cursor].vowel_class != vowel:
                return (), Reason.VOWEL_SEQUENCE_MISMATCH, f"Short vowel order/class differs at p{phone_index}"
            cursor += 1
    if cursor != len(nuclei):
        return (), Reason.VOWEL_SEQUENCE_MISMATCH, "Reading has uncovered vowel-bearing morae"
    return tuple(mappings), None, ""


def analyze_mora(alignment: AlignmentResult, reading_provider: JapaneseReadingProvider) -> MoraAnalysisResult:
    validate_alignment(alignment)
    word_entries = [(index, word) for index, word in enumerate(alignment.words) if word.label]
    owned = [[] for _ in word_entries]
    boundary_issues = [[] for _ in word_entries]
    unresolved = []

    for phone_index, phone in enumerate(alignment.phones):
        owners = [index for index, (_, word) in enumerate(word_entries)
                  if word.start_ms <= phone.start_ms and phone.end_ms <= word.end_ms]
        speech = phone.label not in SILENCE_PHONES
        if len(owners) == 1:
            owned[owners[0]].append(phone_index)
        elif speech:
            involved = owners or [index for index, (_, word) in enumerate(word_entries)
                                  if phone.start_ms < word.end_ms and phone.end_ms > word.start_ms]
            reason = Reason.AMBIGUOUS_PHONE_MAPPING if len(owners) > 1 else Reason.WORD_PHONE_BOUNDARY_MISMATCH
            detail = "Phone has multiple containing words" if owners else "Speech phone is not contained by exactly one nonempty MFA word"
            if not involved:
                unresolved.append(UnresolvedItem(reason, None, detail, phone_indices=(phone_index,),
                                                  phone_labels=(phone.label,)))
            for word_index in involved:
                boundary_issues[word_index].append(UnresolvedItem(
                    reason, word_index, detail, phone_indices=(phone_index,), phone_labels=(phone.label,)))

    words, morae, candidates, spans = [], [], [], []
    for word_index, (alignment_word_index, word) in enumerate(word_entries):
        reading = reading_provider.reading_for(word.label)
        word_issues = list(boundary_issues[word_index])
        phone_indices = tuple(owned[word_index])
        phone_labels = tuple(alignment.phones[index].label for index in phone_indices)
        if not any(label not in SILENCE_PHONES for label in phone_labels):
            word_issues.append(UnresolvedItem(Reason.NO_PHONE_EVIDENCE, word_index,
                                              "Nonempty MFA word has no contained speech phones",
                                              phone_indices=phone_indices, phone_labels=phone_labels))
        word_morae = ()
        if not reading.resolved:
            word_issues.append(UnresolvedItem(reading.reason or Reason.NO_READING, word_index,
                                              reading.detail or "Reading provider returned no trustworthy reading",
                                              phone_indices=phone_indices, phone_labels=phone_labels))
        else:
            tokenization = tokenize_mora(reading.reading, word_index, len(morae))
            if tokenization.issue:
                issue = tokenization.issue
                word_issues.append(UnresolvedItem(issue.reason, word_index,
                                                  f"{issue.detail}: character {issue.character_index} {issue.text!r}",
                                                  phone_indices=phone_indices, phone_labels=phone_labels))
            else:
                word_morae = tokenization.morae
        word_candidates = long_vowel_candidates(word_morae)
        bad_indices = tuple(index for index in phone_indices
                            if alignment.phones[index].label not in SUPPORTED_SPEECH_PHONES | SILENCE_PHONES)
        if bad_indices:
            word_issues.append(UnresolvedItem(Reason.UNSUPPORTED_PHONE, word_index,
                                              "Unknown/OOV phone blocks mapping; no vowel inferred",
                                              phone_indices=bad_indices,
                                              phone_labels=tuple(alignment.phones[index].label for index in bad_indices)))
        internal_silence = tuple(index for index in phone_indices
                                 if alignment.phones[index].label in SILENCE_PHONES
                                 and alignment.phones[index].end_ms > alignment.phones[index].start_ms)
        if internal_silence:
            word_issues.append(UnresolvedItem(Reason.INTERNAL_SILENCE, word_index,
                                              "Positive-length silence inside a nonempty word blocks mapping",
                                              phone_indices=internal_silence,
                                              phone_labels=tuple(alignment.phones[index].label for index in internal_silence)))
        vowel_phones = tuple((index, alignment.phones[index]) for index in phone_indices
                             if phone_vowel_class(alignment.phones[index].label) is not None)
        long_phones = tuple((index, phone) for index, phone in vowel_phones if is_long_vowel_phone(phone.label))
        word_spans = []
        if not word_issues and (word_candidates or long_phones):
            mappings, failure, detail = _ordered_pairs(word_morae, word_candidates, vowel_phones)
            if failure:
                # Class-only local matches cannot rescue incomplete ordered coverage.
                # Multiple such choices are explicitly ambiguous, never picked greedily.
                multiple_choices = (
                    any(sum(candidate.vowel_class == phone_vowel_class(phone.label)
                            for candidate in word_candidates) > 1 for _, phone in long_phones)
                    or any(sum(candidate.vowel_class == phone_vowel_class(phone.label)
                               for _, phone in long_phones) > 1 for candidate in word_candidates))
                if multiple_choices:
                    failure = Reason.AMBIGUOUS_PHONE_MAPPING
                    detail += "; multiple class-compatible local choices lack complete ordered support"
                if long_phones:
                    word_issues.append(UnresolvedItem(failure, word_index, detail,
                                                      mora_indices=tuple(mora.index for mora in word_morae),
                                                      phone_indices=tuple(index for index, _ in vowel_phones),
                                                      phone_labels=tuple(phone.label for _, phone in vowel_phones)))
            else:
                for candidate, phone_index, phone in mappings:
                    word_spans.append(LongVowelSpan(
                        f"long_vowel_p{phone_index}", candidate.id, word_index, phone_index,
                        phone.label, phone.start_ms, phone.end_ms, candidate.mora_indices,
                        candidate.vowel_class, candidate.mapping_basis))
            mapped = {span.candidate_id for span in word_spans}
            for candidate in word_candidates:
                if candidate.id not in mapped:
                    word_issues.append(UnresolvedItem(
                        failure if failure and long_phones else Reason.NO_MATCHING_LONG_PHONE,
                        word_index, detail if failure and long_phones else "Candidate lacks an ordered compatible long-vowel interval",
                        candidate.id, candidate.mora_indices,
                        tuple(index for index, _ in long_phones), tuple(phone.label for _, phone in long_phones)))
        elif word_issues:
            for candidate in word_candidates:
                word_issues.append(UnresolvedItem(word_issues[0].reason, word_index,
                                                  "Word evidence is unresolved; candidate mapping withheld",
                                                  candidate.id, candidate.mora_indices, phone_indices, phone_labels))

        span_by_candidate = {span.candidate_id: span.id for span in word_spans}
        for mora in word_morae:
            references = tuple(span.id for span in word_spans if mora.index in span.mora_indices)
            morae.append(replace(mora, long_vowel_span_ids=references))
        candidates.extend(replace(candidate, span_id=span_by_candidate.get(candidate.id))
                          for candidate in word_candidates)
        spans.extend(word_spans)
        unresolved.extend(word_issues)
        words.append(WordAnalysis(
            word_index, alignment_word_index, word.label, reading, word.start_ms, word.end_ms,
            tuple(mora.index for mora in word_morae), phone_indices,
            "UNRESOLVED" if word_issues else "MAPPED" if word_spans else "NO_CANDIDATES",
            tuple(dict.fromkeys(issue.reason for issue in word_issues))))
    return MoraAnalysisResult(alignment.source, tuple(words), tuple(morae), tuple(candidates),
                              tuple(spans), tuple(unresolved))
