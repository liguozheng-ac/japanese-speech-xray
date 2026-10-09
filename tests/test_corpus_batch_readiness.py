from dataclasses import replace
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import unittest

from corpus_test_support import ROOT,authored_aligner,corpus,digest,pipeline_configuration,read,workspace,write
from speech_xray.corpus.batch_plan import batch_plan_report,object_hash,output_paths,plan_batch
from speech_xray.corpus.intake import validate_corpus
from speech_xray.corpus.models import BatchOutcome,RecordingStatus as Status,SourceType
from speech_xray.corpus.pipeline import run_batch
from speech_xray.corpus.prompt_manifest import validate_prompt_pack
from speech_xray.corpus.readiness import build_readiness,dataset_level,target_gate
from speech_xray.corpus.external import inspect_external_sets
from speech_xray.reference.models import ReferencePolicy
from speech_xray.acoustics.models import evidence_json


class CorpusBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=pipeline_configuration()

    def setUp(self):
        self.directory=workspace(self)
        self.path,self.manifest,self.pack=corpus(self.directory,3)
        self.outcomes=validate_corpus(self.manifest,self.pack)

    def run_jobs(self,fail_key=None):
        return run_batch(self.manifest,self.pack,self.outcomes,self.config,aligner=authored_aligner(self.pack,fail_key))

    def test_plan_deterministic_dry_run_no_derived_writes(self):
        before=sorted(p.relative_to(self.directory).as_posix() for p in self.directory.rglob("*"))
        jobs=plan_batch(self.manifest,self.pack,self.outcomes,self.config)
        first=evidence_json(batch_plan_report(self.manifest,self.pack,jobs,self.config))
        second=evidence_json(batch_plan_report(self.manifest,self.pack,plan_batch(self.manifest,self.pack,self.outcomes,self.config),self.config))
        self.assertEqual(first,second)
        self.assertTrue(all(j.status==Status.PLANNED for j in jobs))
        self.assertEqual(before,sorted(p.relative_to(self.directory).as_posix() for p in self.directory.rglob("*")))

    def test_signature_changes_with_audio_config_pack_or_metadata(self):
        intake=self.outcomes[0]
        original=output_paths(self.manifest,self.pack,intake,self.config)[0]
        variants=[output_paths(self.manifest,self.pack,replace(intake,audio_sha256="0"*64),self.config)[0],
                  output_paths(self.manifest,self.pack,intake,{**self.config,"run_label":"retry"})[0],
                  output_paths(self.manifest,replace(self.pack,sha256="0"*64),intake,self.config)[0],
                  output_paths(replace(self.manifest,metadata_sources=(("changed","0"*64),)),self.pack,intake,self.config)[0]]
        self.assertTrue(all(v!=original for v in variants))

    def test_filename_existence_never_proves_reuse(self):
        _,paths=output_paths(self.manifest,self.pack,self.outcomes[0],self.config)
        path=Path(paths["alignment"]);path.parent.mkdir(parents=True);path.write_text("not evidence",encoding="utf-8")
        job=plan_batch(self.manifest,self.pack,self.outcomes,self.config)[0]
        self.assertEqual(job.status,Status.PLANNED)
        Path(paths["receipt"]).write_text("{}",encoding="utf-8")
        self.assertEqual(plan_batch(self.manifest,self.pack,self.outcomes,self.config)[0].status,Status.REBUILD_REQUIRED)

    def test_one_alignment_failure_isolated_between_successes(self):
        before={i.recording.audio_path:digest(i.recording.audio_path) for i in self.outcomes}
        jobs=self.run_jobs(self.outcomes[1].recording.key)
        self.assertEqual([j.status for j in jobs],[Status.REFERENCE_READY,Status.ALIGNMENT_FAILED,Status.REFERENCE_READY])
        self.assertEqual(before,{path:digest(path) for path in before})
        self.assertTrue((Path(dict(jobs[1].outputs)["run_directory"])/"failure-report.json").exists())

    def test_verified_complete_artifacts_reuse_without_aligner(self):
        first=self.run_jobs()
        self.assertTrue(all(j.status==Status.REFERENCE_READY for j in first),[j.to_dict() for j in first])
        paths=[Path(path) for j in first for name,path in j.outputs if Path(path).is_file()]
        before={str(p):digest(p) for p in paths}
        def forbidden(*args):raise AssertionError("verified artifacts should be reused")
        second=run_batch(self.manifest,self.pack,self.outcomes,self.config,aligner=forbidden)
        self.assertEqual([j.to_dict() for j in first],[j.to_dict() for j in second])
        self.assertEqual(before,{str(p):digest(p) for p in paths})

    def test_tampered_artifact_and_receipt_hash_require_rebuild(self):
        jobs=self.run_jobs()
        first=jobs[0];paths=dict(first.outputs)
        Path(paths["mora_analysis"]).write_text("{}",encoding="utf-8")
        self.assertEqual(plan_batch(self.manifest,self.pack,self.outcomes,self.config)[0].status,Status.REBUILD_REQUIRED)
        recording=replace(self.outcomes[2].recording,evidence_receipt=dict(jobs[2].outputs)["receipt"],evidence_receipt_sha256="0"*64)
        changed=(*self.outcomes[:2],replace(self.outcomes[2],recording=recording))
        self.assertEqual(plan_batch(self.manifest,self.pack,changed,self.config)[2].status,Status.REBUILD_REQUIRED)

    def test_failed_run_preserved_and_new_label_allows_retry(self):
        jobs=self.run_jobs(self.outcomes[0].recording.key)
        original=Path(dict(jobs[0].outputs)["run_directory"])/"failure-report.json"
        before=original.read_bytes()
        again=self.run_jobs()
        self.assertEqual(again[0].status,Status.ALIGNMENT_FAILED)
        self.assertEqual(original.read_bytes(),before)
        retry=run_batch(self.manifest,self.pack,self.outcomes,{**self.config,"run_label":"retry"},aligner=authored_aligner(self.pack))
        self.assertTrue(all(j.status==Status.REFERENCE_READY for j in retry))

    def test_fixture_ready_artifacts_cannot_make_real_readiness(self):
        jobs=self.run_jobs();qa=validate_prompt_pack(self.pack)
        report,profiles=build_readiness(self.manifest,self.pack,self.outcomes,jobs,qa)
        self.assertEqual((report["eligible_real_reference_speaker_count"],report["ready_target_count"],report["insufficient_target_count"]),(0,0,27))
        self.assertFalse(report["real_reference_data_ready"])

        self.assertFalse(profiles)
        self.assertEqual(len(report["coverage_matrix"]["rows"]),24)
        self.assertEqual(len(report["linguistic_coverage"]),8)

    def test_readiness_repeats_source_firewall_even_corrupt_cached_boolean(self):
        outcomes=tuple(replace(i,eligible_real_reference=True) for i in self.outcomes)
        jobs=plan_batch(self.manifest,self.pack,outcomes,self.config)
        report,_=build_readiness(self.manifest,self.pack,outcomes,jobs,validate_prompt_pack(self.pack))
        self.assertEqual(report["eligible_real_reference_speaker_count"],0)
        self.assertFalse(report["real_reference_data_ready"])

    def test_multiple_takes_count_one_and_five_independent_ids_gate(self):
        self.assertEqual(target_gate(["one"]*5,5)["independent_speaker_count"],1)
        self.assertEqual(target_gate(["one"]*5,5)["reference_profile_status"],"INSUFFICIENT_SPEAKERS")
        self.assertEqual(target_gate([f"abstract-{i}" for i in range(5)],5)["reference_profile_status"],"READY_FOR_EXPERIMENT")
        self.assertEqual(target_gate([f"abstract-{i}" for i in range(4)],5)["reference_profile_status"],"INSUFFICIENT_SPEAKERS")

    def test_six_five_three_targets_and_global_partial_gate(self):
        gates=[target_gate([f"abstract-{i}" for i in range(n)],5) for n in (6,5,3)]
        self.assertEqual([g["reference_profile_status"] for g in gates],["READY_FOR_EXPERIMENT","READY_FOR_EXPERIMENT","INSUFFICIENT_SPEAKERS"])
        self.assertEqual(dataset_level(True,2,3,6),"REFERENCE_TARGETS_PARTIALLY_READY")
        self.assertEqual(dataset_level(True,3,3,6),"REFERENCE_DATA_READY")
        self.assertEqual(dataset_level(True,0,3,0),"TOOLING_READY_NO_REAL_DATA")
        self.assertEqual(dataset_level(True,0,3,3),"REAL_DATA_PRESENT_INSUFFICIENT")
        self.assertEqual(dataset_level(False,3,3,6),"TOOLING_NOT_READY")

    def test_configurable_positive_policy_and_serialization_finite(self):
        self.assertEqual(target_gate(["a","b"],3)["reference_profile_status"],"INSUFFICIENT_SPEAKERS")
        with self.assertRaises(ValueError):ReferencePolicy(0)
        report,_=build_readiness(self.manifest,self.pack,self.outcomes,plan_batch(self.manifest,self.pack,self.outcomes,self.config),validate_prompt_pack(self.pack),ReferencePolicy(8))
        self.assertEqual(report["minimum_independent_speakers"],8)
        value=evidence_json(report)
        json.loads(value,parse_constant=lambda value:(_ for _ in ()).throw(AssertionError(value)))
        with self.assertRaises(ValueError):object_hash({"value":float("nan")})

    def test_abstract_profile_aggregation_revalidates_upstream_bundles(self):
        # Abstract metadata contract assertions in memory only: no native WAV,
        # participant manifest or claimed real-data readiness report is saved.
        from reference_test_support import make_manifest,TEXT
        from speech_xray.reference.manifest import load_manifest
        from speech_xray.corpus.models import Prompt,PromptTarget,PromptPack,TargetOutcome
        from speech_xray.corpus.readiness import export_profiles
        from speech_xray.reference.profile_builder import build_reference_profile
        path=make_manifest(self.directory/"abstract-contract")
        reference=load_manifest(path)
        target=PromptTarget(reference.target.target_id,TEXT,TEXT,(0,1),"コー","PROLONGED_MARK","PROLONGED_MARK","O")
        pack=PromptPack("abstract-contract-pack",1,(Prompt(reference.prompt_id,TEXT,TEXT,20,(target,)),),str(path),digest(path))
        outcomes=[];jobs=[];speakers=[]
        for index,entry in enumerate(reference.entries):
            intake=replace(self.outcomes[0],recording=replace(self.outcomes[0].recording,speaker_id=entry.speaker_id,prompt_id=reference.prompt_id,
                          take_id=entry.take_id,source_type=SourceType.REAL_REFERENCE_RECORDING),eligible_real_reference=True)
            outcomes.append(intake)
            speakers.append(replace(self.manifest.speakers[0],speaker_id=entry.speaker_id,source_type=SourceType.REAL_REFERENCE_RECORDING))
            jobs.append(BatchOutcome(intake,Status.REFERENCE_READY,"ABSTRACT_METADATA_POLICY_CONTRACT",(),
                        (TargetOutcome(target.target_id,Status.REFERENCE_READY,"ABSTRACT_CONTRACT",entry,reference.target),)))
        manifest=replace(self.manifest,speakers=tuple(speakers))
        report,profiles=build_readiness(manifest,pack,tuple(outcomes),tuple(jobs),{"status":"PASS"})
        row=report["per_target"][0]
        self.assertEqual((row["independent_speaker_count"],row["valid_observation_count"],row["reference_profile_status"]),(5,5,"READY_FOR_EXPERIMENT"))
        self.assertEqual(profiles[0].manifest.sha256,hashlib.sha256(evidence_json(report["generated_reference_inputs"][0]).encode()).hexdigest())
        self.assertEqual(len(report["coverage_matrix"]["rows"][0]["speakers"]),5)
        # Export uses the original, clearly STRUCTURED_REFERENCE_FIXTURE profile.
        structured=build_reference_profile(reference)
        export_profiles((structured,),self.directory/"structured-exports")
        exported=self.directory/"structured-exports"/reference.target.target_id/"reference-profile.json"
        before=exported.read_bytes();export_profiles((structured,),self.directory/"structured-exports")
        self.assertEqual(exported.read_bytes(),before)
        # Changed source remains rejected even with five asserted speaker IDs.
        audio=Path(dict(reference.entries[0].sources)["audio"].path);audio.write_text("STRUCTURED_TAMPER_TEST",encoding="utf-8")
        rejected,_=build_readiness(manifest,pack,tuple(outcomes),tuple(jobs),{"status":"PASS"})
        self.assertEqual(rejected["per_target"][0]["independent_speaker_count"],4)
        self.assertEqual(rejected["per_target"][0]["reference_profile_status"],"INTEGRITY_FAILURE")
        self.assertFalse(rejected["real_reference_data_ready"])


class CorpusCliTests(unittest.TestCase):
    def setUp(self):
        self.directory=workspace(self)
        self.path,self.manifest,self.pack=corpus(self.directory)

    def cli(self,script,output,*extra):
        return subprocess.run([sys.executable,str(ROOT/"scripts"/script),"--corpus-manifest",str(self.path),"--output",str(output),*extra],cwd=ROOT,capture_output=True,text=True,encoding="utf-8")

    def test_plan_cli_is_deterministic_and_writes_only_explicit_reports(self):
        first=self.directory/"a.json";second=self.directory/"b.json"
        self.assertEqual(self.cli("plan_reference_batch.py",first,"--dry-run").returncode,0)
        self.assertEqual(self.cli("plan_reference_batch.py",second,"--dry-run").returncode,0)
        self.assertEqual(first.read_bytes(),second.read_bytes())
        self.assertFalse((self.directory/"derived").exists())

    def test_run_default_is_dry_and_never_executes_alignment(self):
        output=self.directory/"report.json"
        result=self.cli("run_reference_pipeline.py",output)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(read(output)["execution_requested"])
        self.assertFalse(read(output)["real_reference_data_ready"])
        self.assertFalse((self.directory/"derived").exists())

    def test_outputs_private_and_never_overwrite_sources(self):
        before=self.path.read_bytes()
        self.assertNotEqual(self.cli("validate_reference_corpus.py",self.path).returncode,0)
        self.assertEqual(before,self.path.read_bytes())
        outside=ROOT/".tools/task006-uncreated-public-report.json"
        self.assertNotEqual(self.cli("validate_reference_corpus.py",outside).returncode,0)
        self.assertFalse(outside.exists())

    def test_invalid_audio_retained_in_cli_report_nonzero(self):
        Path(self.manifest.recordings[0].audio_path).write_bytes(b"invalid")
        output=self.directory/"rejected.json"
        process=self.cli("validate_reference_corpus.py",output)
        self.assertNotEqual(process.returncode,0)
        result=read(output)
        self.assertEqual(result["outcomes"][0]["status"],"REJECTED_INTAKE")
        self.assertEqual(result["validated_recording_count"],0)

    def test_empty_collection_reports_zero_not_manufactured_people(self):
        value=read(self.path);value.update(speaker_manifests=[],session_manifests=[],recordings=[]);write(self.path,value)
        output=self.directory/"empty.json"
        process=self.cli("build_reference_readiness.py",output)
        self.assertEqual(process.returncode,0,process.stderr)
        report=read(output)
        self.assertEqual((report["submitted_speaker_count"],report["ready_target_count"],report["insufficient_target_count"]),(0,0,27))
        self.assertFalse(report["real_reference_data_ready"])
        value["prompt_pack"]["prompt_pack_version"]=2;write(self.path,value)
        rejected=self.directory/"empty-wrong-pack.json"
        self.assertNotEqual(self.cli("build_reference_readiness.py",rejected).returncode,0)
        self.assertFalse(rejected.exists())

    def test_mutually_exclusive_execution_flags_and_invalid_policy(self):
        output=self.directory/"none.json"
        self.assertNotEqual(self.cli("run_reference_pipeline.py",output,"--execute","--dry-run").returncode,0)
        self.assertNotEqual(self.cli("build_reference_readiness.py",output,"--minimum-independent-speakers","0").returncode,0)
        self.assertFalse(output.exists())


class CorpusPrivateJvsTests(unittest.TestCase):
    def test_optional_external_jvs_retains_classification_and_insufficient_target(self):
        reference=ROOT/"data/private/task005/jvs/reference-set.json"
        inventory=ROOT/"data/private/task005/jvs/inventory.json"
        if not reference.exists() or not inventory.exists():self.skipTest("Private JVS demo/reference sources absent")
        directory=workspace(self);_,manifest,pack=corpus(directory,0)
        hashes=(digest(reference),digest(inventory))
        manifest=replace(manifest,external_reference_sets=((str(reference),hashes[0],str(inventory),hashes[1]),))
        smoke=inspect_external_sets(manifest)[0]
        self.assertEqual((smoke["available_local_speaker_count"],smoke["available_local_utterance_count"],smoke["same_target_independent_speaker_count"]),(4,60,1))
        self.assertEqual(smoke["reference_profile_status"],"INSUFFICIENT_SPEAKERS")
        self.assertEqual(smoke["source_type"],"EXTERNAL_RESEARCH_CORPUS")
        self.assertFalse(smoke["counts_toward_controlled_readiness"])
        self.assertEqual(hashes,(digest(reference),digest(inventory)))
        broken=replace(manifest,external_reference_sets=((str(reference),"0"*64,str(inventory),hashes[1]),))
        self.assertEqual(inspect_external_sets(broken)[0]["status"],"EXTERNAL_SMOKE_INTEGRITY_FAILURE")
