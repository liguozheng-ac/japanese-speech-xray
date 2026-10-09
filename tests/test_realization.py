"""Authored structural fixtures only: no corpus, audio, models, or MFA dependency."""
from dataclasses import replace
from decimal import Decimal as D
import json
import unittest
from reference_test_support import ROOT
from speech_xray.alignment.models import AlignmentResult, WordInterval, PhoneInterval
from speech_xray.realization import (Target, derive_hypotheses, override_lexicon, CONDITIONS,
    selection, observe, paired_displacements, compare_scores, RealizationEvidence)
from speech_xray.realization.models import Hypotheses


def hypothesis():
    target = Target('authored-target', 'コー', 'コー', 1, (0,1), 'O', 'PROLONGED_MARK')
    return derive_hypotheses(target, ('k','oː'), 1, ('k','o','oː'), (('oː','o'),))


def alignment(reduced=False, shift=0):
    def phone(label,a,b):return PhoneInterval(label,D(a),D(b))
    return AlignmentResult('AUTHORED_STRUCTURAL.TextGrid',D(0),D(400),
        (WordInterval('ア',D(0),D(100)),WordInterval('コー',D(100),D(300+shift)),WordInterval('ア',D(300+shift),D(400))),
        (phone('a',0,100),phone('k',100,150),phone('o' if reduced else 'oː',150,300+shift),phone('a',300+shift,400)))


def scores():
    row={'alignment_log_likelihood':D('-40.12'),'speech_log_likelihood':D('-41'),
         'audio_sha256':'a'*64,'model_sha256':'b'*64,'configuration_sha256':'c'*64,
         'mfa_version':'AUTHORED_STRUCTURAL','feature_sha256':'d'*64,'normalization':'PER_ALL_FRAMES',
         'frame_basis':'ALL_AUDIO_FRAMES','num_frames':40,'adaptation':'DISABLED',
         'condition_specific_transform':False,'score_semantics':'PATH_DEPENDENT_DESCRIPTION'}
    return {c:dict(row) for c in CONDITIONS}


class VariantTests(unittest.TestCase):
    def test_single_replacement(self):
        h=hypothesis();self.assertEqual(h.reduced,('k','o'));self.assertEqual(h.target.mora_span,2)
    def test_non_target_phones_preserved(self):
        h=hypothesis();self.assertEqual(h.canonical[0],h.reduced[0])
    def test_missing_inventory_counterpart(self):
        h=hypothesis();r=derive_hypotheses(h.target,h.canonical,1,('k','oː'),(('oː','o'),))
        self.assertIsNone(r.reduced);self.assertIn('SHORT_COUNTERPART_NOT_IN_INVENTORY',r.reasons)
    def test_unestablished_compatibility(self):
        h=hypothesis();r=derive_hypotheses(h.target,h.canonical,1,('k','o','oː'),())
        self.assertEqual(r.status,'UNSUPPORTED_REDUCED_HYPOTHESIS')
    def test_wrong_vowel_class(self):
        h=hypothesis();r=derive_hypotheses(replace(h.target,vowel_class='A'),h.canonical,1,('k','o','oː'),(('oː','o'),))
        self.assertIn('TARGET_NOT_COMPATIBLE_LONG_VOWEL',r.reasons)
    def test_canonical_inventory_missing(self):
        h=hypothesis();r=derive_hypotheses(h.target,h.canonical,1,('o','oː'),(('oː','o'),))
        self.assertIn('CANONICAL_PHONE_NOT_IN_INVENTORY',r.reasons)
    def test_invalid_phone_index(self):
        with self.assertRaises(ValueError):derive_hypotheses(hypothesis().target,('oː',),-1,('o','oː'),())
    def test_invalid_target_mora_span(self):
        with self.assertRaises(ValueError):replace(hypothesis().target,mora_span=1)
    def test_nonadjacent_mora_indices(self):
        with self.assertRaises(ValueError):replace(hypothesis().target,word_mora_indices=(0,2))
    def test_arbitrary_reduction_rejected(self):
        h=hypothesis()
        with self.assertRaises(ValueError):Hypotheses(h.target,('k','oː'),('t','o'),1,'EVIDENCE_AVAILABLE')


class LexiconTests(unittest.TestCase):
    original='ア\t1.0\ta\r\nコー\t0.9\tk oː\nコー\t0.1\tk o\n'.encode()
    def test_two_exact_equal_cost_variants(self):
        raw,spec=override_lexicon(self.original,hypothesis(),CONDITIONS[2])
        self.assertEqual(spec['pronunciation_weights'],['1.0','1.0'])
        self.assertEqual(raw.decode().splitlines()[-2:],['コー\t1.0\tk oː','コー\t1.0\tk o'])
    def test_all_original_variants_recorded(self):
        _,spec=override_lexicon(self.original,hypothesis(),CONDITIONS[2]);self.assertEqual(len(spec['removed_original_entries']),2)
    def test_non_target_bytes_preserved(self):
        raw,_=override_lexicon(self.original,hypothesis(),CONDITIONS[0]);self.assertTrue(raw.startswith('ア\t1.0\ta\r\n'.encode()))
    def test_canonical_only_exact(self):
        raw,spec=override_lexicon(self.original,hypothesis(),CONDITIONS[0]);self.assertEqual(len(spec['experimental_entries']),1);self.assertTrue(raw.endswith('k oː\n'.encode()))
    def test_reduced_only_exact(self):
        raw,spec=override_lexicon(self.original,hypothesis(),CONDITIONS[1]);self.assertEqual(len(spec['experimental_entries']),1);self.assertTrue(raw.endswith('k o\n'.encode()))
    def test_shared_silence_metadata(self):
        _,spec=override_lexicon(self.original,hypothesis(),CONDITIONS[2],('0.2','1.2','0.9'))
        self.assertTrue(all('\t1.0\t0.2\t1.2\t0.9\t' in e for e in spec['experimental_entries']))
    def test_deterministic_bytes(self):
        self.assertEqual(override_lexicon(self.original,hypothesis(),CONDITIONS[2]),override_lexicon(self.original,hypothesis(),CONDITIONS[2]))
    def test_unknown_condition(self):
        with self.assertRaises(ValueError):override_lexicon(self.original,hypothesis(),'UNKNOWN')
    def test_invalid_silence(self):
        with self.assertRaises(ValueError):override_lexicon(self.original,hypothesis(),CONDITIONS[0],('NaN','1','1'))
    def test_absent_lexical_item(self):
        with self.assertRaises(ValueError):override_lexicon(b'a\ta\n',hypothesis(),CONDITIONS[0])


class GeometryTests(unittest.TestCase):
    def test_canonical_identity_from_sequence(self):self.assertEqual(selection(('k','oː'),hypothesis())['selected'],'CANONICAL_SELECTED')
    def test_reduced_identity_from_sequence(self):self.assertEqual(selection(('k','o'),hypothesis())['selected'],'REDUCED_SELECTED')
    def test_unexpected_sequence_ambiguous(self):self.assertEqual(selection(('k','o','o'),hypothesis())['identity_status'],'AMBIGUOUS_VARIANT_IDENTITY')
    def test_missing_alignment(self):self.assertEqual(selection(None,hypothesis())['selected'],'ALIGNMENT_FAILED')
    def test_phone_word_geometry(self):
        row=observe(alignment(),hypothesis());self.assertEqual(row['phone_duration_ms'],D(150));self.assertEqual(row['previous_word_end_ms'],D(100))
    def test_paired_shifts_and_neighbors(self):
        pair=paired_displacements(observe(alignment(),hypothesis()),observe(alignment(True,-20),hypothesis()))
        self.assertEqual(pair['shifts']['phone_end_ms'],D(-20));self.assertEqual(pair['shifts']['next_phone_duration_ms_shift'],D(20))
    def test_missing_pair_is_abstention(self):self.assertIsNone(paired_displacements(None,observe(alignment(),hypothesis())))
    def test_no_invented_internal_boundary(self):self.assertEqual(len(observe(alignment(),hypothesis())['word_phones']),2)
    def test_word_identity_changed(self):
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):observe(alignment(),replace(hypothesis(),target=replace(hypothesis().target,surface='カ')))
    def test_nonfinite_domain(self):
        with self.assertRaises(ValueError):observe(replace(alignment(),end_ms=D('NaN')),hypothesis())
    def test_overlapping_phone_intervals(self):
        a=alignment();p=list(a.phones);p[1]=replace(p[1],start_ms=D(90))
        with self.assertRaises(ValueError):observe(replace(a,phones=tuple(p)),hypothesis())
    def test_straddling_word_boundary(self):
        a=alignment();w=list(a.words);w[1]=replace(w[1],start_ms=D(110))
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):observe(replace(a,words=tuple(w)),hypothesis())


class ScoreSerializationTests(unittest.TestCase):
    def test_identical_basis_comparable(self):self.assertIs(compare_scores(scores())['comparable'],True)
    def test_adaptation_not_comparable(self):
        s=scores();s[CONDITIONS[1]]['condition_specific_transform']=True;self.assertIs(compare_scores(s)['comparable'],False)
    def test_features_differ_not_comparable(self):
        s=scores();s[CONDITIONS[1]]['feature_sha256']='e'*64;self.assertIs(compare_scores(s)['comparable'],False)
    def test_missing_basis_inconclusive(self):
        s=scores();s[CONDITIONS[1]]['feature_sha256']=None;self.assertEqual(compare_scores(s)['comparable'],'inconclusive')
    def test_frames_differ_not_comparable(self):
        s=scores();s[CONDITIONS[1]]['num_frames']=41;self.assertIs(compare_scores(s)['comparable'],False)
    def test_unavailable_score(self):
        s=scores();s[CONDITIONS[1]]['alignment_log_likelihood']=None;self.assertEqual(compare_scores(s)['comparable'],'inconclusive')
    def test_nonfinite_score_rejected(self):
        s=scores();s[CONDITIONS[1]]['alignment_log_likelihood']='NaN'
        with self.assertRaises(ValueError):compare_scores(s)
    def test_complete_evidence_serialization(self):
        h=hypothesis();a=observe(alignment(),h);b=observe(alignment(True,-20),h)
        row=RealizationEvidence(h,a,b,b,'REDUCED_SELECTED','UNIQUE_EXPORTED_PHONE_SEQUENCE',paired_displacements(a,b),scores(),compare_scores(scores()),('EVIDENCE_AVAILABLE',),(),{'fixture_kind':'AUTHORED_STRUCTURAL'})
        self.assertEqual(row.to_json(),row.to_json());self.assertEqual(json.loads(row.to_json())['target_identity']['mora_span'],2)
    def test_invalid_evidence_state(self):
        with self.assertRaises(ValueError):RealizationEvidence(hypothesis(),None,None,None,'ALIGNMENT_FAILED','ALIGNMENT_FAILED',None,{}, {},('UNKNOWN',),(),{})
    def test_core_has_no_stress_or_private_imports(self):
        package=ROOT/'services/speech-api/src/speech_xray/realization'
        for p in package.glob('*.py'):
            text=p.read_text();self.assertNotIn('speech_xray.stress',text);self.assertNotIn('data/private',text);self.assertNotIn('jvs',text.lower())


if __name__=='__main__':unittest.main()
