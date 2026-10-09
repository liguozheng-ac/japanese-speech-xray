from decimal import Decimal, localcontext
import json
from pathlib import Path
import tempfile
import unittest

from reference_test_support import ROOT, change_source, digest, make_manifest, read, write_json
from speech_xray.reference.manifest import load_manifest
from speech_xray.reference.profile_builder import build_reference_profile


class ReferenceIntegrityTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tools/tmp").mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=ROOT / ".tools/tmp")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.manifest = make_manifest(self.path, [("A", "t1", "150", "4000")])

    def profile(self):
        return build_reference_profile(load_manifest(self.manifest))

    def test_valid_bundle_has_full_hash_and_span_provenance(self):
        profile = self.profile()
        self.assertFalse(profile.rejected)
        take = profile.speakers[0].takes[0]
        self.assertEqual((take.rate.mora_count, take.duration.raw_duration_ms), (20, 150))
        self.assertEqual(len(take.entry.sources), 5)
        self.assertEqual(profile.manifest.sha256, digest(self.manifest))
        self.assertEqual(take.to_dict()["original_span"]["mora_indices"], [0, 1])

    def test_prompt_id_mismatch_is_structured(self):
        value = read(self.manifest)
        value["entries"][0]["prompt_id"] = "different-prompt"
        write_json(self.manifest, value)
        profile = self.profile()
        self.assertEqual(profile.profile_status, "PROMPT_MISMATCH")
        self.assertEqual(profile.rejected[0].reason, "PROMPT_ID_MISMATCH")

    def test_target_id_mismatch_is_structured(self):
        value = read(self.manifest)
        value["entries"][0]["target_id"] = "different-target"
        write_json(self.manifest, value)
        self.assertEqual(self.profile().profile_status, "TARGET_MISMATCH")

    def test_transcript_hash_identity_prevents_other_prompt_pooling(self):
        value = read(self.manifest)
        value["transcript_sha256"] = "a" * 64
        write_json(self.manifest, value)
        self.assertEqual(self.profile().profile_status, "PROMPT_MISMATCH")

    def test_same_phone_other_word_local_target_rejected(self):
        value = read(self.manifest)
        value["target"]["word_mora_indices"] = [2, 3]
        write_json(self.manifest, value)
        profile = self.profile()
        self.assertEqual(profile.profile_status, "TARGET_MISMATCH")
        self.assertEqual(profile.rejected[0].reason, "TARGET_LINGUISTIC_IDENTITY_MISMATCH")

    def test_artifact_bytes_do_not_match_manifest_hash(self):
        value = read(self.manifest)
        source = Path(value["entries"][0]["sources"]["audio"]["path"])
        source.write_text("changed", encoding="utf-8")
        profile = self.profile()
        self.assertEqual(profile.profile_status, "INTEGRITY_FAILURE")
        self.assertEqual(profile.rejected[0].reason, "ARTIFACT_HASH_MISMATCH")

    def test_conflicting_acoustic_boundaries_do_not_move_source(self):
        change_source(self.manifest, "acoustic_evidence",
                      lambda value: value["span_evidence"][0].update(alignment_start_ms=Decimal(110)))
        profile = self.profile()
        self.assertEqual(profile.profile_status, "INTEGRITY_FAILURE")
        self.assertEqual(profile.rejected[0].reason, "ACOUSTIC_SPAN_PROVENANCE_MISMATCH")
        self.assertFalse(profile.speakers)

    def test_audio_mora_alignment_provenance_and_target_fields_validated(self):
        mutations = [lambda v: v["audio"].update(sha256="f" * 64),
                     lambda v: v["sources"].update(mora_analysis_sha256="f" * 64),
                     lambda v: v["sources"].update(alignment_source="different.TextGrid"),
                     lambda v: v["sources"].update(audio=str(self.path / "different.ref")),
                     lambda v: v["span_evidence"][0].update(phone_index=Decimal(2)),
                     lambda v: v["span_evidence"][0].update(mora_indices=[2, 3]),
                     lambda v: v["span_evidence"][0].update(mora_span=Decimal(3)),
                     lambda v: v["span_evidence"][0].update(vowel_class="A"),
                     lambda v: v["span_evidence"][0].update(mapping_basis="KANA_SEQUENCE")]
        original = read(Path(read(self.manifest)["entries"][0]["sources"]["acoustic_evidence"]["path"]))
        for mutate in mutations:
            def reset_and_mutate(value):
                value.clear()
                value.update(original)
                # Nested values are copied before mutation.
                from speech_xray.acoustics.models import evidence_json
                copied = json.loads(evidence_json(value), parse_int=Decimal, parse_float=Decimal)
                value.clear()
                value.update(copied)
                mutate(value)
            change_source(self.manifest, "acoustic_evidence", reset_and_mutate)
            self.assertEqual(self.profile().profile_status, "INTEGRITY_FAILURE")

    def test_phone_source_alignment_boundary_conflict(self):
        def mutate(value):
            value["phones"][1]["start_ms"] = Decimal(110)
            value["phones"][1]["duration_ms"] = Decimal(140)
        change_source(self.manifest, "alignment", mutate)
        self.assertEqual(self.profile().rejected[0].reason, "SOURCE_PHONE_SPAN_MISMATCH")

    def test_partial_linguistic_rate_coverage_rejected(self):
        def mutate(value):
            value["words"][0]["reading_status"] = "UNRESOLVED"
        change_source(self.manifest, "mora_analysis", mutate)
        manifest = read(self.manifest)
        new_hash = manifest["entries"][0]["sources"]["mora_analysis"]["sha256"]
        change_source(self.manifest, "acoustic_evidence",
                      lambda value: value["sources"].update(mora_analysis_sha256=new_hash))
        self.assertEqual(self.profile().profile_status, "INVALID_RATE_CONTEXT")

    def test_missing_source_rejected_without_crash(self):
        value = read(self.manifest)
        Path(value["entries"][0]["sources"]["alignment"]["path"]).unlink()
        profile = self.profile()
        self.assertEqual(profile.profile_status, "INTEGRITY_FAILURE")
        self.assertEqual(profile.rejected[0].reason, "INVALID_SOURCE_ARTIFACT:FileNotFoundError")

    def test_duplicate_audio_under_other_speaker_rejected(self):
        value = read(self.manifest)
        clone = {**value["entries"][0], "speaker_id": "invented-B", "take_id": "t2"}
        value["entries"].append(clone)
        write_json(self.manifest, value)
        profile = self.profile()
        self.assertEqual((len(profile.speakers), len(profile.rejected)), (0, 2))
        self.assertEqual(profile.profile_status, "INTEGRITY_FAILURE")

    def test_failure_not_silently_ready_with_enough_valid_speakers(self):
        directory = self.path / "multi"
        directory.mkdir()
        self.manifest = make_manifest(directory)
        value = read(self.manifest)
        invalid = {**value["entries"][0], "speaker_id": "extra", "take_id": "extra", "target_id": "other"}
        # Different declared audio hash avoids duplicating a valid speaker; the
        # target mismatch is rejected before any source admission.
        import copy
        invalid = copy.deepcopy(invalid)
        invalid["sources"]["audio"]["sha256"] = "f" * 64
        value["entries"].append(invalid)
        write_json(self.manifest, value)
        profile = self.profile()
        self.assertEqual(len(profile.speakers), 5)
        self.assertEqual(profile.profile_status, "TARGET_MISMATCH")
        self.assertEqual(profile.to_dict()["rejected_take_count"], 1)

    def test_overlapping_frames_are_not_independent_reference_samples(self):
        profile = self.profile()
        entry = profile.manifest.entries[0]
        acoustic = read(Path(dict(entry.sources)["acoustic_evidence"].path))
        self.assertGreater(acoustic["track"]["frame_count"], 20)
        self.assertEqual(profile.to_dict()["speaker_count"], 1)
        self.assertEqual(dict(profile.statistics)["raw_duration_ms"].count, 1)

    def test_decimal_source_boundaries_survive_low_context_json(self):
        directory = self.path / "precise"
        directory.mkdir()
        self.manifest = make_manifest(directory, [("A", "exact", "150", "4000", "100.123456789012345678901234567890123456789")])
        with localcontext() as context:
            context.prec = 8
            profile = self.profile()
            value = json.loads(profile.to_json(), parse_int=Decimal, parse_float=Decimal)
        span = value["speaker_observations"][0]["takes"][0]["original_span"]
        self.assertEqual(span["start_ms"], Decimal("100.123456789012345678901234567890123456789"))
        self.assertEqual(span["end_ms"], Decimal("250.123456789012345678901234567890123456789"))
        self.assertEqual(span["duration_ms"], 150)
        self.assertEqual(value["speaker_observations"][0]["takes"][0]["rate_normalized_duration"], Decimal("0.75"))

    def test_selected_frame_cross_reference_mismatch_rejected(self):
        change_source(self.manifest, "acoustic_evidence",
                      lambda value: value["span_evidence"][0].update(selected_frame_indices=[]))
        self.assertEqual(self.profile().rejected[0].reason, "SELECTED_FRAME_REFERENCE_MISMATCH")

    def test_boolean_zero_one_cannot_impersonate_numeric_references(self):
        import copy
        source = Path(read(self.manifest)["entries"][0]["sources"]["acoustic_evidence"]["path"])
        original = read(source)
        for field, replacement in (("word_index", False), ("mora_indices", [False, True])):
            def mutate(value):
                value.clear()
                value.update(copy.deepcopy(original))
                value["span_evidence"][0][field] = replacement
            change_source(self.manifest, "acoustic_evidence", mutate)
            self.assertEqual(self.profile().profile_status, "INTEGRITY_FAILURE")
