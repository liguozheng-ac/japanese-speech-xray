"""Admit only hash-pinned, mutually consistent upstream evidence bundles."""

from dataclasses import dataclass
import hashlib
from pathlib import Path

from speech_xray.acoustics.mora_input import load_mora_analysis
from speech_xray.acoustics.audio import load_audio
from speech_xray.acoustics.timing import center_in_span, quantize_interval, sample_time_ms
from speech_xray.japanese.alignment_input import load_alignment
from speech_xray.japanese.models import MoraKind, VowelClass
from .json_input import read_json
from .manifest import PROJECT_ROOT
from .models import ProfileStatus as Status, ReferenceEntry, ReferenceManifest
from .numeric import finite_decimal, integer
from .domains import interval_inside_audio


class IntegrityError(ValueError):
    def __init__(self, reason, status=Status.INTEGRITY_FAILURE):
        super().__init__(reason)
        self.status = status


@dataclass(frozen=True)
class ValidatedInput:
    alignment: object
    span: object
    mora_count: int


def require(condition, reason, status=Status.INTEGRITY_FAILURE):
    if not condition:
        raise IntegrityError(reason, status)


def same_file(value, reference):
    if not isinstance(value, str) or not value:
        return False
    return (PROJECT_ROOT / value).resolve() == Path(reference.path)


def validate_entry(manifest: ReferenceManifest, entry: ReferenceEntry) -> ValidatedInput:
    require(entry.prompt_id == manifest.prompt_id, "PROMPT_ID_MISMATCH", Status.PROMPT_MISMATCH)
    require(entry.target_id == manifest.target.target_id, "TARGET_ID_MISMATCH", Status.TARGET_MISMATCH)
    refs = dict(entry.sources)
    require(refs["transcript"].sha256 == manifest.transcript_sha256, "TRANSCRIPT_IDENTITY_MISMATCH", Status.PROMPT_MISMATCH)
    try:
        for ref in refs.values():
            require(hashlib.sha256(Path(ref.path).read_bytes()).hexdigest() == ref.sha256, "ARTIFACT_HASH_MISMATCH")
        alignment = load_alignment(refs["alignment"].path)
        mapped = load_mora_analysis(refs["mora_analysis"].path)
        mora, mora_hash = read_json(Path(refs["mora_analysis"].path))
        acoustic, acoustic_hash = read_json(Path(refs["acoustic_evidence"].path))
        require(mora_hash == mapped.sha256 == refs["mora_analysis"].sha256
                and acoustic_hash == refs["acoustic_evidence"].sha256, "ARTIFACT_CHANGED_DURING_READ")
        require(mapped.alignment_source == alignment.source, "MORA_ALIGNMENT_SOURCE_MISMATCH")
        require(acoustic["schema_version"] == "0.1" and acoustic["representation"] == "ACOUSTIC_EVIDENCE",
                "UNSUPPORTED_ACOUSTIC_SCHEMA")
        sources = acoustic["sources"]
        require(sources["alignment_source"] == alignment.source, "ACOUSTIC_ALIGNMENT_SOURCE_MISMATCH")
        require(sources["mora_analysis_sha256"] == refs["mora_analysis"].sha256
                and same_file(sources["mora_analysis"], refs["mora_analysis"]), "ACOUSTIC_MORA_PROVENANCE_MISMATCH")
        require(same_file(sources["audio"], refs["audio"]), "ACOUSTIC_AUDIO_SOURCE_MISMATCH")
        audio = acoustic["audio"]
        require(isinstance(audio, dict) and acoustic["extraction_status"] != "INVALID_AUDIO", "UNAVAILABLE_AUDIO_METADATA")
        require(audio["sha256"] == refs["audio"].sha256 and same_file(audio["source"], refs["audio"]),
                "AUDIO_HASH_OR_SOURCE_MISMATCH")
        rate, size = integer(audio["sample_rate_hz"], "sample rate"), integer(audio["frame_count"], "audio size")
        require(rate > 0 and size > 0 and integer(audio["channels"], "channels") > 0, "INVALID_AUDIO_DOMAIN")
        require(finite_decimal(audio["duration_ms"], "audio duration") == sample_time_ms(size, rate), "AUDIO_DURATION_MISMATCH")
        if dict(manifest.dataset)["material_kind"] == "REAL_REFERENCE_AUDIO":
            decoded = load_audio(refs["audio"].path).metadata
            require((decoded.sha256, decoded.sample_rate_hz, decoded.frame_count, decoded.channels)
                    == (refs["audio"].sha256, rate, size, integer(audio["channels"], "channels")),
                    "DECODED_AUDIO_DOMAIN_MISMATCH")

        # A complete word-local linguistic representation is required to avoid
        # under-counting morae when a reading/tokenization was only partial.
        nonempty = [(index, word) for index, word in enumerate(alignment.words) if word.label.strip()]
        # TextGrid's global end can describe rounded trailing silence. Rate
        # normalization uses every nonempty word, including internal pauses;
        # their boundaries must be contained in the exact sample domain.
        require(bool(nonempty), "EMPTY_LINGUISTIC_CORE", Status.INVALID_RATE_CONTEXT)
        require(all(interval_inside_audio(word.start_ms, word.end_ms, size, rate)
                    for _, word in nonempty), "CORE_WORD_OUTSIDE_AUDIO_DOMAIN", Status.INVALID_RATE_CONTEXT)
        words, tokens = mora["words"], mora["morae"]
        require(len(words) == len(nonempty), "MORA_WORD_COVERAGE_MISMATCH")
        require([integer(token["index"], "mora index") for token in tokens] == list(range(len(tokens))),
                "MORA_INDEX_COVERAGE_MISMATCH")
        for index, (word, (aligned_index, aligned_word)) in enumerate(zip(words, nonempty)):
            for name in ("start_ms", "end_ms"):
                finite_decimal(word[name], "word boundary")
            for name in ("mora_indices", "phone_indices"):
                for reference in word[name]:
                    integer(reference, name)
            require(integer(word["index"], "word index") == index
                    and integer(word["alignment_word_index"], "aligned word index") == aligned_index
                    and word["surface"] == aligned_word.label
                    and word["start_ms"] == aligned_word.start_ms and word["end_ms"] == aligned_word.end_ms,
                    "MORA_WORD_ALIGNMENT_MISMATCH")
            require(word["reading_status"] == "RESOLVED" and isinstance(word["reading"], str)
                    and bool(word["reading"]), "INCOMPLETE_LINGUISTIC_RATE_COVERAGE", Status.INVALID_RATE_CONTEXT)
            owned = [token for token in tokens if integer(token["word_index"], "mora word") == index]
            require(owned and [integer(token["index"], "mora index") for token in owned] == word["mora_indices"]
                    and [integer(token["word_mora_index"], "word mora index") for token in owned] == list(range(len(owned)))
                    and "".join(token["reading"] for token in owned) == word["reading"],
                    "INCOMPLETE_LINGUISTIC_RATE_COVERAGE", Status.INVALID_RATE_CONTEXT)
            for token in owned:
                MoraKind(token["kind"])
                if token["vowel_class"] is not None:
                    VowelClass(token["vowel_class"])
                require(isinstance(token["reading"], str) and bool(token["reading"])
                        and token["text"] == token["reading"], "INVALID_LINGUISTIC_MORA")
        require(sum(len(word["mora_indices"]) for word in words) == len(tokens), "UNOWNED_MORA_POSITIONS")
        matches = [span for span in mapped.long_vowel_spans if span.id == entry.span_id]
        require(len(matches) == 1, "TARGET_SPAN_MISSING_OR_DUPLICATE", Status.TARGET_MISMATCH)
        span = matches[0]
        target = manifest.target
        local_indices = tuple(integer(tokens[index]["word_mora_index"], "word mora index") for index in span.mora_indices)
        require((span.word_index, local_indices, span.phone_label, span.vowel_class, span.mora_span, span.mapping_basis)
                == (target.word_index, target.word_mora_indices, target.phone_label, target.vowel_class,
                    target.mora_span, target.mapping_basis), "TARGET_LINGUISTIC_IDENTITY_MISMATCH", Status.TARGET_MISMATCH)
        require(0 <= span.phone_index < len(alignment.phones), "PHONE_INDEX_OUT_OF_RANGE")
        phone = alignment.phones[span.phone_index]
        if span.native_phone_indices:
            require(span.native_phone_indices == (span.phone_index,span.phone_index+1)
                    and span.phone_index+1 < len(alignment.phones), "NATIVE_ENVELOPE_PHONE_INDEX_MISMATCH")
            second = alignment.phones[span.phone_index+1]
            require((phone.label,second.label) == span.native_phone_labels == (span.vowel_class.lower(),)*2
                    and phone.end_ms == second.start_ms and phone.start_ms < phone.end_ms < second.end_ms
                    and (phone.start_ms,second.end_ms) == (span.start_ms,span.end_ms),
                    "SOURCE_NATIVE_ENVELOPE_MISMATCH")
        else:
            require((phone.label, phone.start_ms, phone.end_ms, phone.duration_ms)
                    == (span.phone_label, span.start_ms, span.end_ms, span.duration_ms), "SOURCE_PHONE_SPAN_MISMATCH")
        require(span.duration_ms > 0, "NONPOSITIVE_TARGET_DURATION", Status.INVALID_RATE_CONTEXT)
        require(interval_inside_audio(span.start_ms, span.end_ms, size, rate), "TARGET_OUTSIDE_AUDIO_DOMAIN")
        matches = [item for item in acoustic["span_evidence"] if item["span_id"] == span.id]
        require(len(matches) == 1, "ACOUSTIC_SPAN_MISSING_OR_DUPLICATE")
        observed = matches[0]
        for name in ("word_index", "phone_index", "mora_span", "frame_count"):
            integer(observed[name], name)
        for index in observed["mora_indices"]:
            integer(index, "acoustic mora index")
        for name in ("alignment_start_ms", "alignment_end_ms", "alignment_duration_ms"):
            finite_decimal(observed[name], name)
        expected = {"span_id": span.id, "candidate_id": span.candidate_id, "word_index": span.word_index,
                    "phone_index": span.phone_index, "phone_label": span.phone_label,
                    "mora_indices": list(span.mora_indices), "mora_span": span.mora_span,
                    "vowel_class": span.vowel_class, "mapping_basis": span.mapping_basis,
                    "alignment_start_ms": span.start_ms, "alignment_end_ms": span.end_ms,
                    "alignment_duration_ms": span.duration_ms, "audio_sha256": refs["audio"].sha256}
        require(all(observed[key] == value for key, value in expected.items()), "ACOUSTIC_SPAN_PROVENANCE_MISMATCH")
        require(observed["extraction_status"] not in {"INVALID_SPAN", "SPAN_OUT_OF_AUDIO_RANGE", "INVALID_AUDIO"},
                "UNAVAILABLE_TARGET_SPAN")
        interval = observed["sample_interval"]
        if interval is not None:
            for name in ("sample_start", "sample_end"):
                integer(interval[name], name)
        require(interval is not None and (interval["sample_start"], interval["sample_end"])
                == quantize_interval(span.start_ms, span.end_ms, rate), "SAMPLE_REFERENCE_MISMATCH")
        track = acoustic["track"]
        require(isinstance(track, dict) and track["sample_rate_hz"] == rate and track["audio_frame_count"] == size,
                "ACOUSTIC_TRACK_AUDIO_MISMATCH")
        for name in ("sample_rate_hz", "audio_frame_count", "frame_count"):
            integer(track[name], name)
        frames = track["frames"]
        require(track["frame_count"] == len(frames)
                and [integer(frame["index"], "frame index") for frame in frames] == list(range(len(frames))),
                "FRAME_REFERENCE_MISMATCH")
        centers = [integer(frame["center_sample"], "frame center") for frame in frames]
        require(all(first < last for first, last in zip(centers, centers[1:])), "NONMONOTONIC_TRACK")
        selected = [index for index, center in enumerate(centers)
                    if center_in_span(center, rate, span.start_ms, span.end_ms)]
        for index in observed["selected_frame_indices"]:
            integer(index, "selected frame index")
        require(observed["selected_frame_indices"] == selected and observed["frame_count"] == len(selected),
                "SELECTED_FRAME_REFERENCE_MISMATCH")
        # No F0 values or frame counts enter the reference statistics.
        for ref in refs.values():
            require(hashlib.sha256(Path(ref.path).read_bytes()).hexdigest() == ref.sha256, "ARTIFACT_CHANGED_DURING_READ")
        return ValidatedInput(alignment, span, len(tokens))
    except IntegrityError:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
        raise IntegrityError(f"INVALID_SOURCE_ARTIFACT:{type(error).__name__}") from error
