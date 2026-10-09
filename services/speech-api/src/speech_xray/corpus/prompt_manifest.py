"""Authoring QA reuses TASK-003 readings/tokenization/candidates without timing."""

from collections import Counter
from pathlib import Path

from speech_xray.japanese.models import MappingBasis, VowelClass
from speech_xray.japanese.reading import SudachiReadingProvider
from speech_xray.japanese.mora_tokenizer import tokenize_mora
from speech_xray.japanese.long_vowel_mapper import long_vowel_candidates
from .models import Prompt, PromptPack, PromptTarget
from .validation import PROJECT_ROOT, identifier, integer, keys, read_json, text

PUNCTUATION = frozenset({"。", "、"})
PATTERNS = ("PROLONGED_MARK", "O_U", "O_O", "E_I", "E_E", "A_A", "I_I", "U_U")


def load_prompt_pack(path) -> PromptPack:
    path = Path(path).resolve()
    if not path.is_relative_to(PROJECT_ROOT):
        raise ValueError("PROMPT_PATH_ESCAPE")
    value, digest = read_json(path)
    keys(value, ("schema_version", "prompt_pack_id", "prompt_pack_version", "authorship", "reading_policy", "prompts"))
    if (value["schema_version"] != "0.1" or value["authorship"] != "SELF_AUTHORED_FOR_THIS_PROJECT"
            or value["reading_policy"] != "SUDACHI_CORE_SPLIT_B_WORD_LOCAL_EXCLUDING_SENTENCE_PUNCTUATION"):
        raise ValueError("INVALID_PROMPT_PACK_SCHEMA_OR_AUTHORSHIP")
    version = integer(value["prompt_pack_version"], "pack version")
    if version < 1 or not isinstance(value["prompts"], list):
        raise ValueError("INVALID_PACK_VERSION_OR_PROMPT_ARRAY")
    prompts, ids, target_ids, texts = [], set(), set(), set()
    for item in value["prompts"]:
        keys(item, ("prompt_id", "text", "expected_reading", "expected_mora_count", "targets"))
        prompt_id = identifier(item["prompt_id"])
        content = text(item["text"], "self-authored text")
        if prompt_id in ids or content in texts or not isinstance(item["targets"], list) or not item["targets"]:
            raise ValueError("DUPLICATE_PROMPT_ID_OR_TEXT_OR_MISSING_TARGETS")
        targets = []
        for target in item["targets"]:
            keys(target, ("target_id", "surface_hint", "expected_word_reading", "word_mora_indices",
                 "expected_reading_region", "expected_candidate_type", "orthographic_pattern", "expected_vowel_class", "expected_mora_span"))
            target_id = identifier(target["target_id"])
            if target_id in target_ids or not target_id.startswith(prompt_id + "-target-"):
                raise ValueError("DUPLICATE_OR_UNBOUND_TARGET_ID")
            indices = tuple(integer(i, "word mora index") for i in target["word_mora_indices"])
            if len(indices) != 2 or indices[1] != indices[0] + 1 or integer(target["expected_mora_span"], "mora span") != 2:
                raise ValueError("UNSUPPORTED_TARGET_MORA_SPAN")
            basis = MappingBasis(target["expected_candidate_type"]).value
            pattern = target["orthographic_pattern"]
            if pattern not in PATTERNS or (pattern == "PROLONGED_MARK") != (basis == "PROLONGED_MARK"):
                raise ValueError("UNSUPPORTED_OR_CONFLICTING_PATTERN")
            targets.append(PromptTarget(target_id, text(target["surface_hint"], "surface hint"),
                           text(target["expected_word_reading"], "word reading"), indices,
                           text(target["expected_reading_region"], "reading region"), basis, pattern,
                           VowelClass(target["expected_vowel_class"]).value))
            target_ids.add(target_id)
        count = integer(item["expected_mora_count"], "expected mora count")
        if count < 1:
            raise ValueError("EMPTY_EXPECTED_MORA_COUNT")
        prompts.append(Prompt(prompt_id, content, text(item["expected_reading"], "expected reading"), count, tuple(targets)))
        ids.add(prompt_id)
        texts.add(content)
    return PromptPack(identifier(value["prompt_pack_id"]), version, tuple(sorted(prompts, key=lambda p: p.prompt_id)), str(path), digest)


def authoring_words(prompt: Prompt, provider):
    pieces = provider.reading_for(prompt.text).pieces
    if not pieces or "".join(piece.surface for piece in pieces) != prompt.text:
        raise ValueError("READING_PIECES_DO_NOT_COVER_PROMPT")
    words = []
    for piece in pieces:
        if piece.surface in PUNCTUATION:
            continue
        result = provider.reading_for(piece.surface)
        if not result.resolved:
            raise ValueError("UNSUPPORTED_WORD_READING")
        tokens = tokenize_mora(result.reading)
        if tokens.issue:
            raise ValueError("UNSUPPORTED_MORA_TOKENIZATION")
        words.append((piece.surface, result.reading, tokens.morae, long_vowel_candidates(tokens.morae)))
    return words


def target_pattern(target, morae):
    if target.mapping_basis == MappingBasis.PROLONGED_MARK:
        return "PROLONGED_MARK"
    ending = morae[target.mora_indices[1]].reading
    return f"{target.vowel_class}_{ {'ア':'A','イ':'I','ウ':'U','エ':'E','オ':'O'}[ending]}"


def validate_prompt_pack(pack: PromptPack):
    provider = SudachiReadingProvider()
    failures, observations = [], []
    for prompt in pack.prompts:
        try:
            words = authoring_words(prompt, provider)
            reading = "".join(word[1] for word in words)
            count = sum(len(word[2]) for word in words)
            if reading != prompt.expected_reading or count != prompt.expected_mora_count:
                raise ValueError("EXPECTED_READING_OR_MORA_COUNT_MISMATCH")
            candidates = []
            for target in prompt.targets:
                matches = [(index, word, candidate) for index, word in enumerate(words)
                           for candidate in word[3] if word[0] == target.surface_hint and word[1] == target.expected_word_reading
                           and candidate.mora_indices == target.word_mora_indices]
                if len(matches) != 1:
                    raise ValueError("DECLARED_TARGET_MISSING_OR_AMBIGUOUS")
                index, word, candidate = matches[0]
                region = "".join(word[2][i].reading for i in candidate.mora_indices)
                if (region != target.expected_reading_region or candidate.vowel_class != target.expected_vowel_class
                        or candidate.mapping_basis != target.expected_candidate_type
                        or target_pattern(candidate, word[2]) != target.orthographic_pattern):
                    raise ValueError("DECLARED_TARGET_EXPECTATION_MISMATCH")
                candidates.append({"target_id": target.target_id, "authoring_word_index": index,
                                   "candidate_type": candidate.mapping_basis, "orthographic_pattern": target.orthographic_pattern,
                                   "vowel_class": candidate.vowel_class, "mora_span": 2})
            observations.append({"prompt_id": prompt.prompt_id, "derived_reading": reading,
                                 "derived_mora_count": count, "targets": candidates})
        except (ValueError, KeyError, IndexError) as error:
            failures.append({"prompt_id": prompt.prompt_id, "reason": str(error)})
    targets = [target for prompt in pack.prompts for target in prompt.targets]
    return {"schema_version": "0.1", "prompt_pack_id": pack.prompt_pack_id, "prompt_pack_version": pack.prompt_pack_version,
            "manifest_sha256": pack.sha256, "status": "PASS" if not failures else "FAIL",
            "prompt_count": len(pack.prompts), "target_count": len(targets),
            "candidate_type_coverage": dict(sorted(Counter(t.expected_candidate_type for t in targets).items())),
            "orthographic_pattern_coverage": dict(sorted(Counter(t.orthographic_pattern for t in targets).items())),
            "vowel_class_coverage": dict(sorted(Counter(t.expected_vowel_class for t in targets).items())),
            "mora_count_distribution": dict(sorted(Counter(str(p.expected_mora_count) for p in pack.prompts).items())),
            "authoring_failures": failures, "duplicate_prompt_ids": [], "duplicate_target_ids": [], "duplicate_texts": [],
            "observations": observations, "evidence_role": "LINGUISTIC_AUTHORING_EXPECTATIONS_ONLY_NO_ACOUSTIC_TIMING"}


def recording_sheet(pack):
    lines = ["# Reference Recording Sheet", "", f"Pack: `{pack.prompt_pack_id}` / version `{pack.prompt_pack_version}`",
             f"Manifest SHA-256: `{pack.sha256}`", "", "自然な声で、文をそのまま読んでください。",
             "読み間違えたら、新しい take 番号で録り直せます。", "", "Replace SPEAKER_ID with your assigned pseudonym.", "",
             "| Prompt ID | Japanese sentence | Filename |", "| --- | --- | --- |"]
    for prompt in pack.prompts:
        lines.append(f"| {prompt.prompt_id} | {prompt.text} | SPEAKER_ID__{prompt.prompt_id}__take-01.wav |")
    return "\n".join(lines) + "\n"
