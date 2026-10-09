from dataclasses import replace
from pathlib import Path
import copy
import json
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from jvs_test_support import ROOT,tree,workspace
from corpus_test_support import authored_aligner,load_prompt_pack,PACK_PATH
from speech_xray.corpus.models import Prompt
from speech_xray.corpus.batch_plan import digest
from speech_xray.external_jvs.inventory import inventory
from speech_xray.external_jvs.discovery import discover,recommend,review_recommendation
from speech_xray.external_jvs.smoke import aligned_word_identity,choose_smoke,run_smoke
from speech_xray.acoustics.models import evidence_json


class JvsDiscoveryTests(unittest.TestCase):
    def setUp(self):self.directory=workspace(self);tree(self.directory)
    def scan(self):return inventory(self.directory,source_type="TEST_FIXTURE")

    def test_target_identity_survives_only_earlier_word_merges(self):
        words=[{"surface":s} for s in ("テスト","を","コーヒー","と","コーヒー")]
        target={"word_index":4,"surface_hint":"コーヒー"}
        aligned=[SimpleNamespace(surface=s) for s in ("テストを","コーヒー","と","コーヒー")]
        self.assertEqual(aligned_word_identity(target,words,aligned),(3,None))
        merged=[SimpleNamespace(surface=s) for s in ("テストを","コーヒー","とコーヒー")]
        self.assertEqual(aligned_word_identity(target,words,merged),(None,"DECLARED_WORD_BOUNDARY_NOT_PRESERVED"))
        changed=[SimpleNamespace(surface=s) for s in ("テストを","コーヒー","コーヒー")]
        self.assertEqual(aligned_word_identity(target,words,changed),(None,"ALIGNED_TRANSCRIPT_CHARACTER_SEQUENCE_DIFFERS"))

    def test_existing_candidate_functions_reused(self):
        import speech_xray.external_jvs.discovery as adapter
        from speech_xray.japanese.long_vowel_mapper import long_vowel_candidates
        from speech_xray.japanese.mora_tokenizer import tokenize_mora
        self.assertIs(adapter.long_vowel_candidates,long_vowel_candidates)
        self.assertIs(adapter.tokenize_mora,tokenize_mora)

    def test_stable_external_ids_and_no_acoustic_timing(self):
        first=discover(self.scan());second=discover(self.scan())
        self.assertEqual(evidence_json(first),evidence_json(second))
        self.assertEqual(len({t["target_id"] for t in first["targets"]}),first["supported_target_count"])
        self.assertTrue(all(t["target_id"].startswith("jvs-parallel100-") for t in first["targets"]))
        for term in ("start_ms","end_ms","duration_ms","LongVowelSpan"):self.assertNotIn(term,evidence_json(first))

    def test_candidate_semantics_class_span_and_availability(self):
        report=discover(self.scan())
        self.assertEqual(report["supported_target_count"],4)
        self.assertEqual(report["candidate_type_counts"],{"KANA_SEQUENCE":2,"PROLONGED_MARK":2})
        self.assertEqual(report["orthographic_pattern_counts"],{"E_I":1,"PROLONGED_MARK":2,"U_U":1})
        self.assertEqual(report["vowel_class_counts"],{"E":1,"I":1,"O":1,"U":1})
        self.assertEqual(report["mora_span_counts"],{"2":4})
        self.assertTrue(all(t["available_speaker_count"]==3 for t in report["targets"]))

    def test_unsupported_reading_reported_without_conversion(self):
        report=self.scan();report["prompts"][0]["text"]="𠮷。"
        result=discover(report)
        row=result["targets_by_prompt"][0]
        self.assertTrue(row["unsupported"])
        self.assertEqual(row["target_count"],0)

    def test_conflicting_transcript_has_no_targets(self):
        report=self.scan();report["prompts"][0]["text"]=None
        row=discover(report)["targets_by_prompt"][0]
        self.assertEqual(row["unsupported"][0]["reason"],"MISSING_OR_CONFLICTING_TRANSCRIPT")
        self.assertEqual(row["target_count"],0)

    def test_selection_structural_and_does_not_lower_policy(self):
        result=discover(self.scan())
        self.assertEqual(recommend(result)["selected_target_count"],0)
        six=copy.deepcopy(result)
        for target in six["targets"]:target["available_speaker_count"]=6
        selected=recommend(six)
        self.assertEqual(selected["selected_target_count"],4)
        self.assertEqual(selected["minimum_speaker_availability"],5)
        self.assertEqual(evidence_json(selected),evidence_json(recommend(six)))
        self.assertIsNone(selected["self_collection_required_for_m1"])
        self.assertFalse(selected["external_jvs_reference_ready"])

    def test_review_defers_zero_usable_aligned_smoke_but_keeps_untested_provisional(self):
        discovery=discover(self.scan());selection=recommend(discovery,minimum_speakers=3)
        target=selection["selected_targets"][0]
        jobs=[{"target_id":t["target_id"],"mapping_status":"UNRESOLVED","acoustic_status":"NOT_RUN"}
              for t in discovery["targets"] if t["corpus_prompt_id"]==target["corpus_prompt_id"]]
        smoke={"source_type":selection["source_type"],"scope":selection["scope"],"outcomes":[
            {"speaker_id":s,"corpus_prompt_id":target["corpus_prompt_id"],"text_identity_sha256":target["text_identity_sha256"],
             "alignment_status":"PASS","targets":copy.deepcopy(jobs)} for s in target["available_speaker_ids"]]}
        before=copy.deepcopy(selection);reviewed=review_recommendation(selection,smoke)
        self.assertEqual(selection,before)
        self.assertGreater(reviewed["deferred_target_count"],0)
        self.assertTrue(all(t["smoke_review"]["status"]=="NOT_SMOKE_TESTED" for t in reviewed["selected_targets"]))
        self.assertFalse(reviewed["external_jvs_reference_ready"])
        smoke["outcomes"][0]["text_identity_sha256"]="0"*64
        with self.assertRaises(ValueError):review_recommendation(selection,smoke)

    def test_review_replacement_requires_same_pattern_class_and_three_usable_ids(self):
        discovery=discover(self.scan());selection=recommend(discovery,minimum_speakers=3,limit=1)
        original=selection["selected_targets"][0]
        replacement={**original,"target_id":"jvs-parallel100-test-authored-alternative"}
        discovery["targets"].append(replacement)
        rows=[{"speaker_id":s,"corpus_prompt_id":original["corpus_prompt_id"],"text_identity_sha256":original["text_identity_sha256"],
               "alignment_status":"PASS","targets":[
                   {"target_id":original["target_id"],"mapping_status":"UNRESOLVED","acoustic_status":"NOT_RUN"},
                   {"target_id":replacement["target_id"],"mapping_status":"MAPPED","acoustic_status":"OK"}]}
              for s in original["available_speaker_ids"]]
        smoke={"source_type":selection["source_type"],"scope":selection["scope"],"outcomes":rows}
        result=review_recommendation(selection,smoke,discovery)
        self.assertEqual((result["deferred_target_count"],result["replacement_target_count"],result["selected_target_count"]),(1,1,1))
        self.assertEqual(result["selected_targets"][0]["replaces_deferred_target_id"],original["target_id"])
        rows[0]["targets"][1]["acoustic_status"]="NOT_RUN"
        self.assertEqual(review_recommendation(selection,smoke,discovery)["replacement_target_count"],0)

    def test_self_authored_pack_hash_and_count_intact(self):
        pack=load_prompt_pack(PACK_PATH)
        self.assertEqual(pack.sha256,"d95f9f552df0a4cffa405c8cd7e9edf4f6f2d0f16070d88f8804f84f5f9dae7c")
        self.assertEqual((len(pack.prompts),sum(len(p.targets) for p in pack.prompts)),(24,27))

    def test_smoke_bound_and_read_only_selection(self):
        observed=self.scan();result=discover(observed)
        before=sorted(str(p) for p in self.directory.rglob("*"))
        records=choose_smoke(observed,result)
        self.assertEqual(len(records),9)
        self.assertEqual(before,sorted(str(p) for p in self.directory.rglob("*")))
        with self.assertRaises(ValueError):choose_smoke(observed,result,6,3)
        with self.assertRaises(ValueError):run_smoke(observed,result,records*3,self.directory/"outputs")

    def test_smoke_prefers_structural_target_selection(self):
        observed=self.scan();result=discover(observed)
        with patch("speech_xray.external_jvs.smoke.recommend",return_value={"selected_targets":[
                {"corpus_prompt_id":"VOICEACTRESS100_003"},
                {"corpus_prompt_id":"VOICEACTRESS100_001"}]}):
            records=choose_smoke(observed,result,1,2)
        self.assertEqual(len(records),2)
        self.assertEqual({r["prompt_id"] for r in records},{"VOICEACTRESS100_003"})
        self.assertEqual({r["speaker_id"] for r in records},{"jvs001","jvs002"})

    def test_runner_reuses_existing_layers_and_reports_isolated_failure(self):
        observed=self.scan();result=discover(observed);records=choose_smoke(observed,result,3,1)
        pack=load_prompt_pack(PACK_PATH)
        prompts=tuple(Prompt(p["corpus_prompt_id"],p["text"],"UNUSED_TEST_EXPECTATION",1,()) for p in observed["prompts"])
        fixture_pack=replace(pack,prompts=prompts)
        aligner=authored_aligner(fixture_pack)
        def structured(paths,record):
            if record["prompt_id"]=="VOICEACTRESS100_002":raise RuntimeError("TEST_ISOLATED_ALIGNMENT_FAILURE")
            class Recording:
                prompt_id=record["prompt_id"]
                key="TEST_FIXTURE_NOT_HUMAN_SPEECH"
            aligner(paths,Recording())
        before={r["audio_path"]:digest(r["audio_path"]) for r in records}
        report=run_smoke(observed,result,records,self.directory/"derived",aligner=structured)
        self.assertEqual([r["status"] for r in report["outcomes"]],["COMPATIBILITY_OBSERVED","ALIGNMENT_FAILED","COMPATIBILITY_OBSERVED"])
        self.assertEqual(report["outcomes"][1]["alignment_status"],"FAILED")
        self.assertFalse(report["counts_toward_controlled_readiness"])
        self.assertEqual(before,{p:digest(p) for p in before})
        for row in report["outcomes"]:
            official=next(p["text"] for p in observed["prompts"] if p["corpus_prompt_id"]==row["corpus_prompt_id"])
            self.assertEqual(Path(row["outputs"]["transcript"]).read_text(encoding="utf-8"),official+"\n")
            for target in row["targets"]:
                self.assertEqual(target["mora_span"],2)
                if target["long_vowel_span"]:self.assertEqual(target["raw_duration_ms"],target["long_vowel_span"]["duration_ms"])

    def test_cli_private_output_and_no_overwrite(self):
        def cli(output):
            return subprocess.run([sys.executable,str(ROOT/"scripts/audit_jvs_parallel100.py"),"--corpus-root",str(self.directory),"--output",str(output)],capture_output=True,text=True,cwd=ROOT)
        first=self.directory/"audit-a.json";second=self.directory/"audit-b.json"
        self.assertEqual(cli(first).returncode,0)
        self.assertEqual(cli(second).returncode,0)
        # Reports are outside the source subtree in actual usage; this fixture's
        # new reports appear only as root metadata, so compare the data sections.
        a=json.loads(first.read_text(encoding="utf-8"));b=json.loads(second.read_text(encoding="utf-8"))
        self.assertEqual(a["discovery"],b["discovery"])
        before=first.read_bytes();self.assertNotEqual(cli(first).returncode,0);self.assertEqual(first.read_bytes(),before)
        self.assertNotEqual(cli(ROOT/"tests/fixtures/never-written-jvs-audit.json").returncode,0)

    def test_smoke_output_cannot_use_public_fixture_paths(self):
        observed=self.scan();result=discover(observed)
        with self.assertRaises(ValueError):run_smoke(observed,result,(),ROOT/"tests/fixtures")


class JvsPrivateAuditTests(unittest.TestCase):
    def test_optional_actual_full_jvs_inventory(self):
        root=ROOT/"data/private/external/jvs/source/extracted/jvs_ver1"
        if not root.is_dir():self.skipTest("Official full JVS archive has not been supplied")
        report=inventory(root)
        self.assertEqual(report["source_type"],"EXTERNAL_RESEARCH_CORPUS")
        self.assertGreater(report["observed"]["parallel100_speaker_count"],0)
        self.assertEqual(evidence_json(report),evidence_json(inventory(root)))
