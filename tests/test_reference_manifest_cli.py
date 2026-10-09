from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from reference_test_support import ROOT, change_source, digest, make_manifest, read, write_json
from speech_xray.reference.manifest import load_manifest
from speech_xray.reference.profile_builder import build_reference_profile


class ReferenceManifestCliTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tools/tmp").mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=ROOT / ".tools/tmp")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.manifest = make_manifest(self.path)

    def cli(self, output, *extra):
        return subprocess.run([sys.executable, str(ROOT / "scripts/build_reference_profile.py"),
                               "--manifest", str(self.manifest), "--output", str(output), *extra],
                               cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def test_valid_cli_stable_json_preserves_all_sources(self):
        manifest = load_manifest(self.manifest)
        before = {ref.path: digest(Path(ref.path)) for entry in manifest.entries for _, ref in entry.sources}
        first, second = self.path / "profile-a.json", self.path / "profile-b.json"
        self.assertEqual(self.cli(first).returncode, 0)
        self.assertEqual(self.cli(second).returncode, 0)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        value = read(first)
        self.assertEqual((value["speaker_count"], value["take_count"], value["profile_status"]),
                         (5, 5, "READY_FOR_EXPERIMENT"))
        self.assertEqual(before, {path: digest(Path(path)) for path in before})
        self.assertEqual(value["source_provenance"]["manifest"]["sha256"], digest(self.manifest))

    def test_manifest_canonical_entry_order_and_builder_sorting(self):
        manifest = load_manifest(self.manifest)
        reversed_manifest = replace(manifest, entries=tuple(reversed(manifest.entries)))
        self.assertEqual(build_reference_profile(manifest).to_json(), build_reference_profile(reversed_manifest).to_json())
        # Reordering manifest bytes changes its recorded hash, deliberately.
        value = read(self.manifest)
        value["entries"].reverse()
        write_json(self.manifest, value)
        other = load_manifest(self.manifest)
        self.assertEqual([entry.speaker_id for entry in manifest.entries], [entry.speaker_id for entry in other.entries])
        self.assertNotEqual(manifest.sha256, other.sha256)

    def test_manifest_schema_duplicate_ids_hashes_and_fields_rejected(self):
        original = read(self.manifest)
        import copy
        mutations = [lambda v: v.update(schema_version="9"),
                     lambda v: v.update(transcript_sha256="invalid"),
                     lambda v: v["entries"].append(v["entries"][0]),
                     lambda v: v["target"].update(word_mora_indices=[0, 2]),
                     lambda v: v["entries"][0]["sources"].update(unexpected={}),
                     lambda v: v["dataset"].update(local_only="false")]
        for mutate in mutations:
            value = copy.deepcopy(original)
            mutate(value)
            write_json(self.manifest, value)
            with self.assertRaises(ValueError):
                load_manifest(self.manifest)

    def test_duplicate_json_nonfinite_and_boolean_indices_rejected(self):
        original = self.manifest.read_text(encoding="utf-8")
        variants = [original.replace('"schema_version":', '"schema_version": "duplicate", "schema_version":', 1),
                    original.replace('"word_index": 0', '"word_index": NaN', 1),
                    original.replace('"word_index": 0', '"word_index": 1e999999', 1),
                    original.replace('"word_index": 0', '"word_index": true', 1)]
        for value in variants:
            self.manifest.write_text(value, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_manifest(self.manifest)

    def test_artifact_and_output_paths_must_remain_in_project(self):
        value = read(self.manifest)
        # Computed path is never read or written; only containment is tested.
        value["entries"][0]["sources"]["audio"]["path"] = str(ROOT.parent / "outside-unread.ref")
        write_json(self.manifest, value)
        with self.assertRaises(ValueError):
            load_manifest(self.manifest)
        output = self.path / "none.json"
        self.assertNotEqual(self.cli(output).returncode, 0)
        self.assertFalse(output.exists())

    def test_cli_never_overwrites_manifest_or_any_artifact(self):
        manifest = load_manifest(self.manifest)
        targets = [self.manifest] + [Path(ref.path) for _, ref in manifest.entries[0].sources]
        for target in targets:
            before = target.read_bytes()
            self.assertNotEqual(self.cli(target).returncode, 0)
            self.assertEqual(target.read_bytes(), before)

    def test_integrity_failure_cli_writes_structured_result_nonzero(self):
        change_source(self.manifest, "acoustic_evidence",
                      lambda v: v["span_evidence"][0].update(alignment_end_ms=Decimal(999)))
        output = self.path / "failed.json"
        process = self.cli(output)
        self.assertNotEqual(process.returncode, 0)
        value = read(output)
        self.assertEqual(value["profile_status"], "INTEGRITY_FAILURE")
        self.assertEqual(value["speaker_count"], 4)
        self.assertEqual(value["rejected_take_count"], 1)
        self.assertNotIn("NaN", output.read_text(encoding="utf-8"))

    def test_insufficient_speakers_is_honest_successful_cli_result(self):
        output = self.path / "insufficient.json"
        process = self.cli(output, "--minimum-independent-speakers", "6")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(read(output)["profile_status"], "INSUFFICIENT_SPEAKERS")

    def test_invalid_policy_or_manifest_writes_no_output(self):
        output = self.path / "none.json"
        self.assertNotEqual(self.cli(output, "--minimum-independent-speakers", "0").returncode, 0)
        self.assertFalse(output.exists())
        value = read(self.manifest)
        del value["prompt_id"]
        write_json(self.manifest, value)
        self.assertNotEqual(self.cli(output).returncode, 0)
        self.assertFalse(output.exists())

    def test_relative_source_paths_are_manifest_relative(self):
        value = read(self.manifest)
        for entry in value["entries"]:
            for ref in entry["sources"].values():
                ref["path"] = Path(ref["path"]).relative_to(self.path).as_posix()
        write_json(self.manifest, value)
        profile = build_reference_profile(load_manifest(self.manifest))
        self.assertFalse(profile.rejected)
        self.assertEqual(profile.profile_status, "READY_FOR_EXPERIMENT")
