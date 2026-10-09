"""Synthetic integration of frozen algorithms, independent of MFA/private references."""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from reference_test_support import ROOT
from test_product_api import wav
from speech_xray.alignment.models import AlignmentResult,WordInterval,PhoneInterval
from speech_xray.reference.models import RobustStatistics
from speech_xray.realization import Target,derive_hypotheses
from speech_xray.product.config import Settings,Resource
from speech_xray.product.prompts import PromptRegistry
from speech_xray.product.pipeline import ProductPipeline
from speech_xray.product.orchestrator import SpeechAnalysisRequest
from speech_xray.product.serialization import project


class StructuralRuntime:
    def __init__(self,alignment_mode='available',competition_mode='available'):
        self.calls=[];self.alignment_mode=alignment_mode;self.competition_mode=competition_mode
    def hypotheses(self,binding,index):
        return derive_hypotheses(Target(binding.target_id,binding.surface,binding.reading,index,binding.local_mora_indices,
            binding.vowel_class,binding.mapping_basis),binding.canonical,binding.phone_index,(*binding.canonical,'a'),(('aː','a'),))
    def align(self,path,binding,folder,hypotheses=None):
        self.calls.append('COMPETITION_EQUAL_PRIOR' if hypotheses else 'PRIMARY_ANALYSIS_ALIGNMENT')
        if self.alignment_mode=='missing':return None
        end=900 if self.alignment_mode=='outside' else 820
        start=3000 if self.alignment_mode=='outside' else 100
        sequence=list(binding.canonical)
        if hypotheses is not None and self.competition_mode=='reduced':sequence=list(hypotheses.reduced)
        if hypotheses is not None and self.competition_mode=='ambiguous':sequence[-1]='a'
        if self.alignment_mode=='mapping':sequence[binding.phone_index]='a'
        return AlignmentResult('AUTHORED_STRUCTURAL.TextGrid',D(0),D(4000 if start==3000 else 1000),
            (WordInterval(binding.surface,D(start),D(start+720)),),
            tuple(PhoneInterval(p,D(start+i*80),D(start+(i+1)*80)) for i,p in enumerate(sequence)))


class StructuralReferences:
    def __init__(self,binding,compatible=True):
        self.compatible=compatible
        resource=SimpleNamespace(profile=SimpleNamespace(sha256='c'*64))
        self.resources={binding.reference_target_id:resource}
        self.resource=resource
    def resolve(self,binding):
        if not self.compatible:return None
        return ({'speaker_count':100,'profile_status':'READY_FOR_EXPERIMENT','speaker_observations':[]},self.resource)
    def statistics(self,profile):
        return RobustStatistics(100,D(2),D(0),D('1.8'),D('2.2'),D('.4'),D(1),D(3),'ZERO_MAD')


class PipelineTests(unittest.TestCase):
    def run_case(self,alignment_mode='available',competition_mode='available',compatible=True):
        with TemporaryDirectory() as folder:
            path=Path(folder);audio=path/'input.wav';audio.write_bytes(wav())
            s=Settings(alignment_engine='mfa', runtime_identity_sha256='0'*64)
            s=s.model_copy(update={k:Resource(path=path/'unused',sha256='d'*64) for k in ('acoustic_model','dictionary','g2p_model')})
            binding=PromptRegistry(s.prompt_registry,s.binding_registry).resolve('learner-v1-001')
            # Explicitly synthetic word-only prompt, not pretending this is the authored full sentence.
            binding=replace(binding,prompt=binding.prompt.model_copy(update={'display_text':binding.surface}))
            runtime=StructuralRuntime(alignment_mode,competition_mode)
            internal=ProductPipeline(s,StructuralReferences(binding,compatible),runtime).analyse(
                SpeechAnalysisRequest(audio,path,binding,'structural',s.policy_version))
            return project(internal),internal,runtime
    def test_real_frozen_extraction_partial_f0(self):
        result,internal,runtime=self.run_case()
        self.assertEqual(result.status,'PARTIAL_EVIDENCE')
        self.assertIsNotNone(result.targets[0].duration)
        self.assertIsNone(result.targets[0].acoustics.raw_f0_median_hz)
        self.assertEqual(runtime.calls,['PRIMARY_ANALYSIS_ALIGNMENT','COMPETITION_EQUAL_PRIOR'])
        self.assertIn('NORMALIZED',[e['stage'] for e in internal.stage_trace])
    def test_reduced_probe_keeps_primary_span(self):
        result,_,_=self.run_case(competition_mode='reduced')
        self.assertEqual(result.targets[0].realization.selected_variant,'REDUCED_SELECTED')
        self.assertEqual(result.targets[0].time_span.start_ms,D(340))
        self.assertEqual(result.targets[0].duration.raw_duration_ms,D(80))
    def test_ambiguous_abstains_retains_duration(self):
        result,_,_=self.run_case(competition_mode='ambiguous')
        self.assertEqual(result.status,'ABSTAINED');self.assertIsNotNone(result.targets[0].duration)
        self.assertEqual(result.targets[0].reasons[0].reason_code,'AMBIGUOUS_VARIANT_IDENTITY')
    def test_exact_domain_abstention(self):
        result,_,runtime=self.run_case(alignment_mode='outside')
        self.assertEqual(result.status,'ABSTAINED');self.assertEqual(len(runtime.calls),1)
        self.assertEqual(result.targets[0].reasons[0].reason_code,'CORE_WORD_OUTSIDE_AUDIO_DOMAIN')
    def test_missing_alignment_retains_target(self):
        result,_,_=self.run_case(alignment_mode='missing')
        self.assertEqual(result.status,'ABSTAINED');self.assertEqual(len(result.targets),1)
    def test_missing_target_never_guessed_from_short_phone(self):
        result,_,_=self.run_case(alignment_mode='mapping')
        self.assertEqual(result.targets[0].reasons[0].reason_code,'TARGET_NOT_MAPPED')
    def test_no_compatible_reference_abstains(self):
        result,_,runtime=self.run_case(compatible=False)
        self.assertEqual(result.status,'ABSTAINED');self.assertEqual(len(runtime.calls),1)
        self.assertIsNone(result.targets[0].reference)
    def test_zero_mad_uses_frozen_null_policy(self):
        result,_,_=self.run_case()
        self.assertIsNone(result.targets[0].deviation.mad_distance)
        self.assertEqual(result.targets[0].deviation.warnings,['ZERO_MAD'])
