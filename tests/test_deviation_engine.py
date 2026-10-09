from dataclasses import replace
from decimal import Decimal,localcontext
from pathlib import Path
import unittest

from deviation_test_support import workspace,reference,candidate,rewritten_reference
from reference_test_support import read,write_json
from speech_xray.reference.manifest import load_manifest
from speech_xray.reference.models import NormalizedDuration
from speech_xray.deviation.inputs import candidate_from_bundle
from speech_xray.deviation.engine import compare_duration
from speech_xray.deviation.duration import describe_duration
from speech_xray.deviation.models import EvidenceStatus as S


class DeviationEngineTests(unittest.TestCase):
    def setUp(self):
        self.root=workspace(self);self.ref=reference(self.root/'reference')

    def compare(self,raw='140'):
        return compare_duration(candidate(self.root/('candidate-'+raw),raw),self.ref)

    def test_below_equal_above_are_only_mathematical_directions(self):
        for raw,direction,delta in [('120','BELOW_REFERENCE_MEDIAN','-.2'),('140','AT_REFERENCE_MEDIAN','0'),('160','ABOVE_REFERENCE_MEDIAN','.2')]:
            with self.subTest(raw=raw):
                r=self.compare(raw);self.assertEqual(r.status,S.OK)
                value=r.evidence['features']['rate_normalized_duration']
                self.assertEqual((value['direction'],value['signed_delta']),(direction,Decimal(delta)))

    def test_ratio_signed_delta_and_MAD_distance(self):
        value=self.compare('210').evidence['features']['rate_normalized_duration']
        self.assertEqual(value['signed_delta'],Decimal('.7'))
        self.assertEqual(value['ratio_to_median'],Decimal('1.5'))
        self.assertEqual(value['mad_distance'],Decimal('3.5'))
        self.assertEqual(value['mad_distance_status'],'DEFINED')

    def test_absolute_MAD_distance_increases_monotonically(self):
        below=[abs(self.compare(raw).evidence['features']['rate_normalized_duration']['mad_distance']) for raw in ('120','100','80')]
        above=[abs(self.compare(raw).evidence['features']['rate_normalized_duration']['mad_distance']) for raw in ('160','180','200')]
        self.assertEqual(below,sorted(below));self.assertEqual(above,sorted(above))
        self.assertTrue(all(a<b for a,b in zip(below,below[1:])))

    def test_zero_MAD_returns_null_without_epsilon(self):
        ref=reference(self.root/'zero',[140]*5)
        r=compare_duration(candidate(self.root/'outside-zero','200'),ref)
        self.assertEqual(r.status,S.OK)
        value=r.evidence['features']['rate_normalized_duration']
        self.assertIsNone(value['mad_distance']);self.assertEqual(value['mad_distance_status'],'ZERO_MAD')
        self.assertEqual(value['signed_delta'],Decimal('.6'))

    def test_zero_MAD_equal_candidate_keeps_other_evidence(self):
        ref=reference(self.root/'zero',[140]*5)
        value=compare_duration(candidate(self.root/'equal-zero'),ref).evidence['features']['rate_normalized_duration']
        self.assertEqual((value['signed_delta'],value['ratio_to_median']),(0,1))
        self.assertIsNone(value['mad_distance'])

    def test_observed_ranges_are_descriptive_and_inclusive(self):
        edge=self.compare('120').evidence['features']['rate_normalized_duration']
        self.assertTrue(edge['inside_iqr']);self.assertTrue(edge['inside_observed_min_max'])
        outside=self.compare('200')
        self.assertEqual(outside.status,S.OK)
        self.assertFalse(outside.evidence['features']['rate_normalized_duration']['inside_iqr'])
        self.assertFalse(outside.evidence['features']['rate_normalized_duration']['inside_observed_min_max'])

    def test_all_supporting_duration_features_retained(self):
        r=self.compare('140')
        self.assertEqual(set(r.evidence['features']),{'raw_duration_ms','rate_normalized_duration','rate_normalized_duration_per_mora'})
        self.assertEqual(r.candidate['raw_duration_ms'],140)
        self.assertEqual(r.candidate['rate_normalized_duration_per_mora'],Decimal('.7'))

    def test_nonfinite_negative_and_zero_candidate_abstain(self):
        base=candidate(self.root/'candidate')
        for value in map(Decimal,('NaN','Infinity','-Infinity','0','-1')):
            r=compare_duration(replace(base,duration=replace(base.duration,raw_duration_ms=value)),self.ref)
            self.assertEqual(r.status,S.ABSTAIN_INVALID_CANDIDATE)
            self.assertIsNone(r.evidence);self.assertNotIn('NaN',r.to_json())

    def test_missing_normalized_duration_is_structured(self):
        c=candidate(self.root/'candidate')
        r=compare_duration(replace(c,duration=NormalizedDuration(c.duration.raw_duration_ms,None,None)),self.ref)
        self.assertEqual(r.status,S.ABSTAIN_MISSING_NORMALIZED_DURATION)

    def test_missing_candidate_and_reference_types_abstain(self):
        self.assertEqual(compare_duration(None,self.ref).status,S.ABSTAIN_INVALID_CANDIDATE)
        self.assertEqual(compare_duration(candidate(self.root/'candidate'),None).status,S.ABSTAIN_INVALID_REFERENCE)

    def test_normalization_tampering_cannot_be_compared(self):
        c=candidate(self.root/'candidate')
        r=compare_duration(replace(c,duration=replace(c.duration,rate_normalized_duration=Decimal(2))),self.ref)
        self.assertEqual(r.status,S.ABSTAIN_INVALID_CANDIDATE)
        self.assertEqual(r.reason_codes,('CANDIDATE_NORMALIZATION_MISMATCH',))

    def test_invalid_core_rate_abstains(self):
        c=candidate(self.root/'candidate')
        for rate in [replace(c.rate,mora_count=0),replace(c.rate,core_speech_duration_ms=Decimal(0))]:
            self.assertEqual(compare_duration(replace(c,rate=rate),self.ref).status,S.ABSTAIN_INVALID_CANDIDATE)

    def test_legitimate_other_target_is_mismatch(self):
        c=candidate(self.root/'candidate');path=Path(c.manifest.source);v=read(path)
        v['target']['target_id']='authored-other-target'
        v['entries'][0]['target_id']='authored-other-target';write_json(path,v)
        m=load_manifest(path);other=candidate_from_bundle(m,m.entries[0])
        self.assertEqual(compare_duration(other,self.ref).status,S.ABSTAIN_TARGET_MISMATCH)

    def test_mora_span_mismatch_abstains(self):
        c=candidate(self.root/'candidate')
        changed=replace(c,manifest=replace(c.manifest,target=replace(c.manifest.target,mora_span=3)))
        self.assertEqual(compare_duration(changed,self.ref).status,S.ABSTAIN_TARGET_MISMATCH)

    def test_reference_not_ready_abstains(self):
        ref=reference(self.root/'small',count=4)
        self.assertEqual(compare_duration(candidate(self.root/'candidate'),ref).status,S.ABSTAIN_REFERENCE_NOT_READY)

    def test_invalid_reference_statistical_ordering_abstains(self):
        p=self.ref.profile
        stats=tuple((k,replace(v,q25=v.maximum+1) if k=='rate_normalized_duration' else v) for k,v in p.statistics)
        ref=rewritten_reference(self.ref,replace(p,statistics=stats),self.root/'invalid')
        self.assertEqual(compare_duration(candidate(self.root/'candidate'),ref).status,S.ABSTAIN_INVALID_REFERENCE)

    def test_inconsistent_reference_N_abstains(self):
        p=self.ref.profile;stats=tuple((k,replace(v,count=99)) for k,v in p.statistics)
        ref=rewritten_reference(self.ref,replace(p,statistics=stats),self.root/'invalid')
        self.assertEqual(compare_duration(candidate(self.root/'candidate'),ref).status,S.ABSTAIN_INVALID_REFERENCE)

    def test_nonfinite_reference_is_rejected_without_serializing_input(self):
        p=self.ref.profile;stats=tuple((k,replace(v,mad=Decimal('NaN'))) for k,v in p.statistics)
        r=compare_duration(candidate(self.root/'candidate'),replace(self.ref,profile=replace(p,statistics=stats)))
        self.assertEqual(r.status,S.ABSTAIN_INVALID_REFERENCE);self.assertIsNone(r.evidence)

    def test_changed_candidate_source_identity_abstains(self):
        c=candidate(self.root/'candidate');Path(dict(c.entry.sources)['audio'].path).write_bytes(b'changed')
        self.assertEqual(compare_duration(c,self.ref).status,S.ABSTAIN_INVALID_CANDIDATE)

    def test_changed_reference_artifact_abstains(self):
        Path(self.ref.profile_artifact.path).write_bytes(b'changed')
        self.assertEqual(self.compare().status,S.ABSTAIN_INVALID_REFERENCE)

    def test_reference_origin_identity_mismatch_abstains(self):
        self.assertEqual(compare_duration(candidate(self.root/'candidate'),replace(self.ref,origin_reference_set_id='other')).status,S.ABSTAIN_INVALID_REFERENCE)

    def test_candidate_speaker_in_reference_is_abstention(self):
        ref=self.ref.profile;take=ref.speakers[0].takes[0]
        c=candidate_from_bundle(ref.manifest,take.entry)
        self.assertEqual(compare_duration(c,self.ref).status,S.ABSTAIN_REFERENCE_LEAKAGE)

    def test_low_decimal_context_does_not_change_serialization(self):
        c=candidate(self.root/'candidate','210');before=compare_duration(c,self.ref).to_json()
        with localcontext() as ctx:
            ctx.prec=5
            after=compare_duration(c,self.ref).to_json()
        self.assertEqual(before,after)

    def test_deterministic_result_is_byte_identical(self):
        c=candidate(self.root/'candidate')
        self.assertEqual(compare_duration(c,self.ref).to_json().encode(),compare_duration(c,self.ref).to_json().encode())

    def test_no_diagnostic_fields_or_labels_in_success_output(self):
        value=self.compare('200').to_json()
        for word in ('CORRECT','INCORRECT','TOO_SHORT','TOO_LONG','GOOD','BAD','confidence','severity','score','pronunciation_error','f0_hz'):
            self.assertNotIn(word,value)
        self.assertIn('ABOVE_REFERENCE_MEDIAN',value)

    def test_abstention_retains_available_provenance_and_formulas_without_bad_numbers(self):
        c=candidate(self.root/'candidate')
        r=compare_duration(replace(c,duration=replace(c.duration,raw_duration_ms=Decimal('NaN'))),self.ref)
        value=r.to_dict()
        self.assertIsNone(value['evidence'])
        self.assertEqual(value['candidate']['speaker_id'],c.entry.speaker_id)
        self.assertEqual(value['candidate']['source_manifest']['sha256'],c.manifest.sha256)
        self.assertEqual(value['reference']['identity'],self.ref.profile.manifest.reference_set_id)
        self.assertEqual(value['reference']['version'],self.ref.version)
        self.assertEqual(value['candidate']['provenance_state'],'UNVERIFIED_ABSTENTION_CONTEXT')
        self.assertIn('formulas',value['comparison_implementation'])
        self.assertIn('normalization_definition',value['comparison_implementation'])
        self.assertNotIn('NaN',r.to_json())

    def test_real_reference_old_version_cannot_be_active(self):
        p=self.ref.profile
        dataset=tuple((k,'REAL_REFERENCE_AUDIO' if k=='material_kind' else v) for k,v in p.manifest.dataset)
        old=replace(self.ref,version='task008-v1',profile=replace(p,manifest=replace(p.manifest,dataset=dataset)))
        result=compare_duration(candidate(self.root/'candidate'),old)
        self.assertEqual(result.status,S.ABSTAIN_INVALID_REFERENCE)
        self.assertEqual(result.reason_codes,('REFERENCE_VERSION_NOT_ACTIVE',))

    def test_audio_identity_leakage_even_with_different_speaker_id(self):
        p=self.ref.profile
        path=self.root/'clone-manifest.json'
        value=read(Path(p.manifest.source))
        entry=value['entries'][0]
        entry['speaker_id']='AUTHORED-CLONE-ID'
        value['entries']=[entry]
        write_json(path,value)
        m=load_manifest(path)
        clone=candidate_from_bundle(m,m.entries[0])
        result=compare_duration(clone,self.ref)
        self.assertEqual(result.status,S.ABSTAIN_REFERENCE_LEAKAGE)
        self.assertEqual(result.reason_codes,('CANDIDATE_AUDIO_INCLUDED_IN_REFERENCE',))
