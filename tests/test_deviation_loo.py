from dataclasses import replace
from pathlib import Path
import unittest

from deviation_test_support import workspace,reference
from speech_xray.reference.profile_builder import build_reference_profile
from speech_xray.deviation.snapshot import VerifiedReferenceSnapshot
from speech_xray.deviation.engine import compare_duration
from speech_xray.deviation.serialization import save_canonical
from speech_xray.deviation.models import EvidenceStatus
from speech_xray.deviation.models import ReferenceObservation
from reference_test_support import make_manifest
from speech_xray.reference.manifest import load_manifest


class LeaveOneSpeakerOutTests(unittest.TestCase):
    def setUp(self):self.root=workspace(self)

    def test_authored_source_N100_produces_N99_and_no_self_leakage(self):
        ref=reference(self.root/'source',raw=[100+(i%11)*10 for i in range(100)],count=100)
        snapshot=VerifiedReferenceSnapshot(ref.profile.manifest.source,ref.profile_artifact,ref.version)
        original_validator=build_reference_profile.__globals__['validate_entry']
        self.assertIs(snapshot.builder.__code__,build_reference_profile.__code__)
        self.assertIs(build_reference_profile.__globals__['validate_entry'],original_validator)
        for heldout in (ref.profile.speakers[0].speaker_id,ref.profile.speakers[-1].speaker_id):
            loo=snapshot.build_excluding(heldout,self.root/heldout)
            self.assertEqual(len(loo.profile.speakers),99)
            self.assertNotIn(heldout,{s.speaker_id for s in loo.profile.speakers})
            original=build_reference_profile(loo.profile.manifest)
            self.assertEqual(original.to_json(),loo.profile.to_json())
            result=compare_duration(snapshot.candidate(heldout),loo)
            self.assertEqual(result.status,EvidenceStatus.OK)
            self.assertNotIn(heldout,result.reference['speaker_ids'])
            self.assertEqual(result.reference['n'],99)
        snapshot.verify_hashes()
        self.assertEqual(len(snapshot._inputs),100)

    def test_self_leakage_assertion_fails_loudly(self):
        ref=reference(self.root/'source')
        with self.assertRaisesRegex(ValueError,'LOO_CANDIDATE_INCLUDED_IN_REFERENCE'):
            VerifiedReferenceSnapshot.assert_exclusion(ref.profile.speakers[0].speaker_id,ref.profile)

    def test_missing_holdout_speaker_fails_loudly(self):
        ref=reference(self.root/'source');snapshot=VerifiedReferenceSnapshot(ref.profile.manifest.source,ref.profile_artifact,ref.version)
        with self.assertRaisesRegex(ValueError,'LOO_CANDIDATE_SPEAKER_MISSING'):
            snapshot.build_excluding('not-present',self.root/'invalid')

    def test_snapshot_mutation_fails_before_reusing_validated_input(self):
        ref=reference(self.root/'source');snapshot=VerifiedReferenceSnapshot(ref.profile.manifest.source,ref.profile_artifact,ref.version)
        entry=snapshot.manifest.entries[0];Path(dict(entry.sources)['audio'].path).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'SNAPSHOT_ARTIFACT_CHANGED'):
            snapshot.build_excluding(snapshot.profile.speakers[-1].speaker_id,self.root/'invalid')

    def test_changed_validation_context_is_not_cached(self):
        ref=reference(self.root/'source');snapshot=VerifiedReferenceSnapshot(ref.profile.manifest.source,ref.profile_artifact,ref.version)
        context=replace(snapshot.manifest,target=replace(snapshot.manifest.target,target_id='other'))
        with self.assertRaisesRegex(ValueError,'SNAPSHOT_VALIDATION_CONTEXT_MISMATCH'):
            snapshot.builder(context)

    def test_repeat_reconstruction_and_serialization_are_identical(self):
        ref=reference(self.root/'source',count=6);snapshot=VerifiedReferenceSnapshot(ref.profile.manifest.source,ref.profile_artifact,ref.version)
        heldout=snapshot.profile.speakers[0].speaker_id
        first=snapshot.build_excluding(heldout,self.root/'case')
        before=Path(first.profile_artifact.path).read_bytes()
        second=snapshot.build_excluding(heldout,self.root/'case')
        self.assertEqual(first.profile_artifact,second.profile_artifact)
        self.assertEqual(before,Path(second.profile_artifact.path).read_bytes())
        self.assertEqual(compare_duration(snapshot.candidate(heldout),first).to_json(),compare_duration(snapshot.candidate(heldout),second).to_json())

    def test_canonical_output_cannot_overwrite_other_evidence(self):
        p=self.root/'immutable.json';save_canonical(p,{'authored':1});before=p.read_bytes()
        with self.assertRaises(ValueError):save_canonical(p,{'authored':2})
        self.assertEqual(before,p.read_bytes())

    def test_output_must_remain_private(self):
        with self.assertRaisesRegex(ValueError,'DEVIATION_ARTIFACT_MUST_REMAIN_PRIVATE'):
            save_canonical(self.root.parents[2]/'forbidden-public.json',{'authored':True})

    def test_entire_heldout_speaker_is_excluded_including_multiple_takes(self):
        source=self.root/'multi';source.mkdir()
        specs=[(f'AUTHORED-{i}','first',str(100+20*i),'2000') for i in range(6)]
        specs.append(('AUTHORED-0','second','180','2000'))
        manifest=load_manifest(make_manifest(source,specs))
        profile=build_reference_profile(manifest)
        artifact=save_canonical(source/'profile.json',profile.to_dict())
        snapshot=VerifiedReferenceSnapshot(manifest.source,artifact,'AUTHORED_REFERENCE_V1')
        loo=snapshot.build_excluding('AUTHORED-0',self.root/'case')
        self.assertEqual(len(loo.profile.speakers),5)
        self.assertEqual(len(loo.profile.manifest.entries),5)
        self.assertNotIn('AUTHORED-0',{e.speaker_id for e in loo.profile.manifest.entries})
        self.assertEqual(loo.profile.to_json(),build_reference_profile(loo.profile.manifest).to_json())

    def test_reference_layer_has_no_reverse_dependency(self):
        source=Path(build_reference_profile.__code__.co_filename).parent
        for path in source.glob('*.py'):
            self.assertNotIn('speech_xray.deviation',path.read_text(encoding='utf-8'))

    def test_experiment_rejects_overlapping_accepted_input_root(self):
        from speech_xray.deviation.loo import run_experiment
        for output in (self.root,self.root/'nested',self.root.parent):
            with self.assertRaisesRegex(ValueError,'EXPERIMENT_REQUIRES_SEPARATE_PRIVATE_ROOT'):
                run_experiment(self.root,output)
