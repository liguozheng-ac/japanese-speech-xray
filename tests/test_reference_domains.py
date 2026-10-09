"""Authored domain regressions; no corpus-derived times or observations."""
from decimal import Decimal, localcontext
from pathlib import Path
import tempfile
import unittest
import wave

from reference_test_support import ROOT, make_manifest, change_source, read, write_json, digest
from speech_xray.reference.domains import interval_inside_audio
from speech_xray.reference.manifest import load_manifest
from speech_xray.reference.profile_builder import build_reference_profile
from speech_xray.jvs_reference.reconciliation import compare_profiles, ensure_separate_roots, verify_configuration, freeze_previous_build, INTEGRITY_PATH, DOMAIN_PATH
from speech_xray.jvs_reference.build import save_verified


class ExactAudioDomainTests(unittest.TestCase):
    def test_target_at_exact_wav_boundary(self):
        self.assertTrue(interval_inside_audio(Decimal('0'), Decimal('125'), 3, 24))

    def test_subsample_overrun_has_no_tolerance(self):
        with localcontext() as ctx:
            ctx.prec = 4
            self.assertFalse(interval_inside_audio(Decimal('0'), Decimal('125.000000000000000000000000000001'), 3, 24))

    def test_sample_duration_is_not_rounded_display_duration(self):
        self.assertTrue(interval_inside_audio(Decimal('0'), Decimal('0.333333333333333333333333333333333'), 1, 3000))
        self.assertFalse(interval_inside_audio(Decimal('0'), Decimal('0.333333333333333333333333333333334'), 1, 3000))

    def test_negative_zero_reversed_and_nonfinite_fail(self):
        for start, end in [('-.1','1'), ('1','1'), ('2','1'), ('NaN','1'), ('0','Infinity'), ('-Infinity','1')]:
            with self.subTest(start=start,end=end):
                self.assertFalse(interval_inside_audio(Decimal(start),Decimal(end),10,1000))

    def test_invalid_sample_domains_fail(self):
        for frames, rate in [(0,1000),(1,0),(-1,1000),(True,1000),(1,True)]:
            self.assertFalse(interval_inside_audio(Decimal(0),Decimal(1),frames,rate))


class ReferenceSemanticDomainTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'.tools/tmp').mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'.tools/tmp');self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        self.manifest=make_manifest(self.directory, [('A','one','150','4000')])

    def profile(self):return build_reference_profile(load_manifest(self.manifest))

    def enlarge_global(self, end):
        def mutate(v):
            v['end_ms']=end;v['duration_ms']=end-v['start_ms']
            v['words'][-1]['end_ms']=end
            v['phones'][-1]['end_ms']=end
            v['phones'][-1]['duration_ms']=end-v['phones'][-1]['start_ms']
        change_source(self.manifest,'alignment',mutate)

    def test_global_metadata_overrun_with_core_target_inside_is_admitted(self):
        before=self.profile()
        self.enlarge_global(Decimal('9000'))
        after=self.profile()
        self.assertFalse(after.rejected)
        self.assertEqual(before.statistics,after.statistics)
        self.assertEqual(before.speakers[0].takes[0].rate,after.speakers[0].takes[0].rate)

    def test_last_required_core_word_outside_fails_before_statistics(self):
        self.enlarge_global(Decimal('9000'))
        def mutate(v):
            v['words'][1]['end_ms']=Decimal('4201.00000000000000000000000000001')
            v['words'][2]['start_ms']=v['words'][1]['end_ms']
        change_source(self.manifest,'alignment',mutate)
        self.assertEqual(self.profile().rejected[0].reason,'CORE_WORD_OUTSIDE_AUDIO_DOMAIN')

    def test_target_at_boundary_is_admitted_by_whole_bundle_validator(self):
        directory=self.directory/'boundary';directory.mkdir()
        self.manifest=make_manifest(directory,[('A','edge','150','150')])
        def mutate(v):
            v['audio'].update(frame_count=250,duration_ms=Decimal(250))
            track=v['track'];track['audio_frame_count']=250
            track['frames']=[f for f in track['frames'] if f['center_sample']<=250]
            track['frame_count']=len(track['frames'])
            for frame in track['frames']:
                frame['observed_end_sample']=min(frame['window_end_sample'],250)
                frame['padding_right_samples']=max(0,frame['window_end_sample']-250)
        change_source(self.manifest,'acoustic_evidence',mutate)
        profile=self.profile()
        self.assertFalse(profile.rejected)
        self.assertEqual(profile.speakers[0].takes[0].original_span.end_ms,250)

    def test_outside_target_cannot_be_rescued_by_global_metadata(self):
        self.enlarge_global(Decimal(9000))
        # All mapped spans belong to their core word. A WAV that ends before
        # the target also truncates that required word and must fail closed.
        def mutate(v):
            v['audio'].update(frame_count=249,duration_ms=Decimal(249))
            v['track']['audio_frame_count']=249
        change_source(self.manifest,'acoustic_evidence',mutate)
        self.assertTrue(self.profile().rejected)
        self.assertFalse(self.profile().speakers)

    def test_zero_target_duration_fails(self):
        directory=self.directory/'zero-target';directory.mkdir()
        self.manifest=make_manifest(directory,[('A','zero','0','4000')])
        self.assertEqual(self.profile().rejected[0].reason,'NONPOSITIVE_TARGET_DURATION')

    def test_zero_core_word_fails(self):
        def mutate(v):v['words'][1]['end_ms']=v['words'][1]['start_ms']
        change_source(self.manifest,'alignment',mutate)
        self.assertEqual(self.profile().rejected[0].reason,'CORE_WORD_OUTSIDE_AUDIO_DOMAIN')

    def test_negative_and_reversed_phone_boundaries_fail(self):
        for start,end in [(Decimal(-1),Decimal(250)),(Decimal(250),Decimal(100))]:
            directory=self.directory/str(abs(start));directory.mkdir(exist_ok=True)
            self.manifest=make_manifest(directory,[('A','one','150','4000')])
            def mutate(v):
                v['phones'][1].update(start_ms=start,end_ms=end,duration_ms=end-start)
            change_source(self.manifest,'alignment',mutate)
            self.assertTrue(self.profile().rejected)

    def test_nonfinite_boundary_fails(self):
        v=read(self.manifest);p=Path(v['entries'][0]['sources']['alignment']['path'])
        p.write_text(p.read_text().replace('"start_ms": 0','"start_ms": NaN',1),encoding='utf-8')
        v['entries'][0]['sources']['alignment']['sha256']=digest(p);write_json(self.manifest,v)
        self.assertTrue(self.profile().rejected)

    def test_corrupt_real_audio_cannot_use_pinned_synthetic_metadata(self):
        v=read(self.manifest);entry=v['entries'][0];p=Path(entry['sources']['audio']['path'])
        p.write_bytes(b'CORRUPT_AUTHORED_WAV')
        sha=digest(p);entry['sources']['audio']['sha256']=sha
        v['dataset']['material_kind']='REAL_REFERENCE_AUDIO';write_json(self.manifest,v)
        def mutate(a):
            a['audio']['sha256']=sha
            for span in a['span_evidence']:span['audio_sha256']=sha
        change_source(self.manifest,'acoustic_evidence',mutate)
        self.assertTrue(self.profile().rejected)

    def test_decoded_wav_domain_must_match_saved_evidence(self):
        v=read(self.manifest);entry=v['entries'][0];p=Path(entry['sources']['audio']['path'])
        with wave.open(str(p),'wb') as audio:
            audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(2000)
            audio.writeframes(b'\0\0'*4201)
        sha=digest(p);entry['sources']['audio']['sha256']=sha
        v['dataset']['material_kind']='REAL_REFERENCE_AUDIO';write_json(self.manifest,v)
        def mutate(a):
            a['audio']['sha256']=sha
            for span in a['span_evidence']:span['audio_sha256']=sha
        change_source(self.manifest,'acoustic_evidence',mutate)
        self.assertEqual(self.profile().rejected[0].reason,'DECODED_AUDIO_DOMAIN_MISMATCH')

    def test_inconsistent_artifact_identity_still_fails(self):
        v=read(self.manifest);Path(v['entries'][0]['sources']['audio']['path']).write_bytes(b'changed')
        self.assertEqual(self.profile().rejected[0].reason,'ARTIFACT_HASH_MISMATCH')


class ReconciliationContractTests(unittest.TestCase):
    def test_frozen_v1_detects_mutated_artifact(self):
        root=ROOT/'data/private/authored-reconciliation';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            previous=Path(directory)/'v1';previous.mkdir()
            output=Path(directory)/'v2';p=previous/'evidence.json';p.write_text('authored')
            records=freeze_previous_build(previous,output)
            self.assertEqual(records,freeze_previous_build(previous,output))
            p.write_text('mutated')
            with self.assertRaises(ValueError):freeze_previous_build(previous,output)

    def test_v1_destination_cannot_be_overwritten_or_nested(self):
        root=ROOT/'data/private/authored-reconciliation'
        for a,b in [(root,root),(root,root/'v2'),(root/'v1',root)]:
            with self.assertRaises(ValueError):ensure_separate_roots(a,b)

    def test_upstream_configuration_change_fails(self):
        old={'reading':{},'analysis_code_sha256':{INTEGRITY_PATH:'old','upstream.py':'same'}}
        new={'reading':{},'analysis_code_sha256':{INTEGRITY_PATH:'new','upstream.py':'same',DOMAIN_PATH:'added'}}
        self.assertTrue(verify_configuration(old,new)['upstream_identity_unchanged'])
        new['analysis_code_sha256']['upstream.py']='changed'
        with self.assertRaises(ValueError):verify_configuration(old,new)

    def test_deterministic_canonical_output_refuses_changed_bytes(self):
        root=ROOT/'data/private/authored-reconciliation';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            p=Path(directory)/'artifact.json';first=save_verified(p,{'N':5});raw=p.read_bytes()
            self.assertEqual(first,save_verified(p,{'N':5}));self.assertEqual(raw,p.read_bytes())
            with self.assertRaises(ValueError):save_verified(p,{'N':6})
            self.assertEqual(raw,p.read_bytes())

    def test_N_and_all_robust_statistics_comparison(self):
        names=('median','mad','q25','q75','iqr','minimum','maximum')
        old={'speaker_count':5,'feature_statistics':{'raw_duration_ms':{k:Decimal(10) for k in names}}}
        new={'speaker_count':7,'feature_statistics':{'raw_duration_ms':{k:Decimal(12) for k in names}}}
        result=compare_profiles(old,new)
        self.assertEqual((result['v1_N'],result['v2_N']),(5,7))
        for row in result['features']['raw_duration_ms'].values():
            self.assertEqual(row['absolute_change'],2);self.assertEqual(row['relative_change'],Decimal('.2'))

    def test_zero_baseline_relative_change_is_explicitly_unavailable(self):
        names=('median','mad','q25','q75','iqr','minimum','maximum')
        old={'speaker_count':5,'feature_statistics':{'feature':{k:Decimal(0) for k in names}}}
        new={'speaker_count':5,'feature_statistics':{'feature':{k:Decimal(1) for k in names}}}
        self.assertIsNone(compare_profiles(old,new)['features']['feature']['mad']['relative_change'])
