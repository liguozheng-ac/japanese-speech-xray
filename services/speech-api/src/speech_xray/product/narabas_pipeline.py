"""Native narabas measurement and matched reference; no realization competition."""
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path
from time import perf_counter

from speech_xray.acoustics.models import evidence_json
from speech_xray.acoustics.mora_input import load_mora_analysis
from speech_xray.acoustics.pipeline import extract_acoustic_evidence
from speech_xray.reference.models import ArtifactReference, ReferenceManifest, ReferenceEntry, TargetIdentity
from speech_xray.reference.integrity import IntegrityError, validate_entry
from speech_xray.reference.speech_rate import measure_utterance_rate
from speech_xray.reference.normalization import normalize_duration
from speech_xray.deviation.duration import describe_duration
from .audio import validate_audio
from .errors import ProductError
from .serialization import InternalAnalysisResult, identity
from .orchestrator import report_stage
from .narabas_audio import alignment_copy
from .narabas_mapping import NarabasPhoneRegistry, map_native
from .native_boundary import BoundaryUnusable
from .narabas_runtime import sha256, COMMIT

REALIZATION_UNAVAILABLE = 'REALIZATION_PROBE_NOT_AVAILABLE_WITH_NARABAS_V1'


class NarabasPipeline:
    persistent_execution = True
    stage_labels = ('音频准备','音素对齐','目标结构检查','声学证据与参考计算','结果整理')

    def __init__(self, settings, references, runtime):
        self.settings,self.references,self.runtime = settings,references,runtime
        self.phones = NarabasPhoneRegistry(settings.narabas.phone_sequence.path)

    def diagnostic(self, request, stage, row, error):
        root = self.settings.workspace_root.parent / 'narabas-failures'
        root.mkdir(parents=True,exist_ok=True)
        value = {'request_id':request.request_id,'stage':stage,'runtime_state':self.runtime.state,
                 'model_identity':self.references.measurement['alignment_provenance'],
                 'phone_sequence':row['phone_sequence'],'error_class':type(error).__name__,
                 'error_message':str(error)[:2048],'worker_exit_state':self.runtime.process.poll() if self.runtime.process else None}
        (root / (request.workspace.name+'.json')).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
        for path in sorted(root.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[20:]:
            path.unlink()

    def analyse(self, request):
        settings,binding = self.settings,request.binding
        trace,timings = [],{}
        started = perf_counter()
        def mark(stage,code='OK'):
            trace.append({'stage':stage,'reason_code':code})
        def write(name,value):
            path = request.workspace/name
            path.write_text(evidence_json(value),encoding='utf-8')
            return ArtifactReference(str(path),sha256(path))
        def finish():
            t=perf_counter()
            report_stage(request,5)
            mark('RESPONSE_ASSEMBLED')
            timings['finalization_ms']=(perf_counter()-t)*1000
            timings['total_ms']=(perf_counter()-started)*1000
            return InternalAnalysisResult(output,trace,timings,{'workspace':str(request.workspace),
                'native_alignment_sha256':sha256(request.workspace/'native-segments.json') if (request.workspace/'native-segments.json').exists() else None,
                'worker_pid':self.runtime.process.pid if self.runtime.process else None,'worker_restarts':self.runtime.restarts,
                'alignment_copy':conversion})
        def abstain(stage,code):
            target['reasons'].append({'stage':stage,'reason_code':code,'message':'Declared target evidence is unavailable.'})
            mark(stage,code)
            return finish()
        t=perf_counter()
        audio = validate_audio(request.audio_path,settings)
        row = self.phones.resolve(binding.prompt.prompt_id,binding.prompt.display_text)
        declared_word = row['words'][row['target_word_index']]
        if (declared_word['surface'],declared_word['reading'],tuple(row['target_word_mora_indices']),row['vowel'].upper()) != (
                binding.surface,binding.reading,binding.local_mora_indices,binding.vowel_class):
            raise ProductError('INTERNAL_PIPELINE_ERROR','TARGET_MAPPED','FROZEN_TARGET_IDENTITY_MISMATCH')
        derived = request.workspace/'alignment-16000.wav'
        conversion = alignment_copy(request.audio_path,derived)
        timings['audio_preparation_ms']=(perf_counter()-t)*1000
        mark('INPUT_VALIDATED');mark('PROMPT_RESOLVED')
        method = self.references.measurement['alignment_provenance']
        target = {'target_id':binding.target_id,'surface':binding.surface,'reading':binding.reading,
                  'word_index':None,'mora_indices':[],'mora_span':2,'vowel_class':binding.vowel_class,
                  'mapping_basis':binding.mapping_basis,'time_span':None,'duration':None,'reference':None,
                  'deviation':None,'realization':None,'acoustics':None,
                  'availability':{k:False for k in ('duration','reference','deviation','realization','raw_f0','rms')},
                  'evidence_status':'ABSTAINED','reasons':[]}
        provenance = {'pipeline_version':'product-m1-1.1.0','analysis_policy_version':settings.policy_version,
            'prompt_binding_version':binding.binding_version,'prompt_binding_sha256':binding.binding_sha256,
            'prompt_pack_sha256':binding.pack_sha256,'reference_version':settings.reference_version,
            'alignment_engine':'NARABAS_CPU_WORKER','alignment_engine_version':COMMIT,
            'acoustic_model_sha256':method['model_sha256'],'dictionary_sha256':None,'g2p_model_sha256':None,
            'runtime_identity_sha256':method['runtime_lock_sha256'],'alignment_provenance':method,
            'candidate_audio_in_reference':False,'comparison_role':'DESCRIPTIVE_ONLY'}
        resource = self.references.resources[binding.reference_target_id]
        output = {'schema_version':'1.1.0','analysis_id':request.request_id,
            'analysis_fingerprint':identity({'audio':audio.sha256,'binding':binding.binding_sha256,
                'reference_profile':resource.profile.sha256,'alignment_provenance':method,'pipeline_version':'product-m1-1.1.0'}),
            'status':'ABSTAINED','prompt':binding.prompt.model_dump(),'audio':{'sha256':audio.sha256,
                'duration_ms':audio.duration_ms,'sample_rate_hz':audio.sample_rate_hz,'channels':audio.channels,
                'sample_count':audio.frame_count,'decoded_format':'WAV'},'timeline':None,'targets':[target],
            'warnings':[],'provenance':provenance}
        report_stage(request,2)
        t=perf_counter()
        try:
            raw = self.runtime.align(derived,row['phone_sequence'])
        except (ValueError, RuntimeError, OSError, TimeoutError) as error:
            self.diagnostic(request,'ALIGNED',row,error)
            raise ProductError('ALIGNMENT_RUNTIME_UNAVAILABLE','ALIGNED','NARABAS_WORKER_FAILURE') from error
        timings['alignment_ms']=(perf_counter()-t)*1000
        write('native-segments.json',raw)
        mark('ALIGNED')
        report_stage(request,3)
        t=perf_counter()
        try:
            alignment,mora = map_native(row,raw['segments'],audio.duration_ms,str(request.workspace/'native-segments.json'))
        except BoundaryUnusable as error:
            self.diagnostic(request,'TARGET_MAPPED',row,error)
            return abstain('TARGET_MAPPED','ALIGNMENT_UNUSABLE')
        timings['boundary_mapping_ms']=(perf_counter()-t)*1000
        span = mora.long_vowel_spans[0]
        mark('TARGET_MAPPED')
        target.update(word_index=span.word_index,mora_indices=list(span.mora_indices),
                      time_span={'start_ms':span.start_ms,'end_ms':span.end_ms})
        output['timeline']={'start_ms':Decimal(0),'end_ms':audio.duration_ms,'basis':'PRIMARY_ANALYSIS_ALIGNMENT',
            'words':[{'index':w.index,'surface':w.surface,'reading':w.reading_result.reading,'start_ms':w.start_ms,'end_ms':w.end_ms} for w in mora.words],
            'phones':[{'index':i,'symbol':p.label,'start_ms':p.start_ms,'end_ms':p.end_ms,
                       'word_index':next((w.index for w in mora.words if i in w.phone_indices),None)} for i,p in enumerate(alignment.phones)],
            'morae':[{'index':m.index,'word_index':m.word_index,'word_mora_index':m.word_mora_index,
                     'representation':m.reading,'kind':m.kind,
                     'shared_span':target['time_span'] if m.index in span.mora_indices else None,
                     'timing_basis':'SHARED_NATIVE_PHONE_ENVELOPE' if m.index in span.mora_indices else 'NO_INDIVIDUAL_ACOUSTIC_BOUNDARY'} for m in mora.morae]}
        alignment_ref = write('alignment.json',alignment.to_dict())
        mora_ref = write('mora.json',mora.to_dict())
        transcript = request.workspace/'prompt.lab'
        transcript.write_text(binding.prompt.display_text+'\n',encoding='utf-8')
        report_stage(request,4)
        t=perf_counter()
        acoustic = extract_acoustic_evidence(request.audio_path,load_mora_analysis(mora_ref.path))
        timings['acoustics_ms']=(perf_counter()-t)*1000
        acoustic_ref = write('acoustics.json',acoustic.to_dict())
        sources = (('audio',ArtifactReference(str(request.audio_path),audio.sha256)),('transcript',ArtifactReference(str(transcript),sha256(transcript))),
                   ('alignment',alignment_ref),('mora_analysis',mora_ref),('acoustic_evidence',acoustic_ref))
        entry = ReferenceEntry(binding.prompt.prompt_id,binding.target_id,'ephemeral-request',request.request_id,
                               request.request_id,span.id,sources)
        context = ReferenceManifest('ephemeral-product-validation',binding.prompt.prompt_id,sha256(transcript),
            TargetIdentity(binding.target_id,span.word_index,binding.local_mora_indices,span.phone_label,span.vowel_class,2,span.mapping_basis),
            (('material_kind','PRODUCT_EPHEMERAL_UPLOAD'),),'Never a native population',(entry,),'','')
        try:
            validated = validate_entry(context,entry)
        except IntegrityError as error:
            self.diagnostic(request,'TIMING_DOMAIN',row,error)
            return abstain('TIMING_DOMAIN','TARGET_EVIDENCE_INTEGRITY_FAILURE')
        duration = normalize_duration(validated.span,measure_utterance_rate(validated.alignment,validated.mora_count))
        target['duration']=asdict(duration)
        target['availability']['duration']=True
        selected = acoustic.spans[0]
        target['acoustics']={'selected_frame_count':selected.frame_count,'voiced_frame_count':selected.voiced_frame_count,
            'raw_f0_median_hz':selected.raw_f0_hz.median,'rms_median':selected.rms.median,'extraction_status':selected.extraction_status}
        target['availability'].update(raw_f0=selected.raw_f0_hz.median is not None,rms=selected.rms.median is not None)
        t=perf_counter()
        reference = self.references.resolve(binding)
        timings['reference_ms']=(perf_counter()-t)*1000
        if reference is None: return abstain('REFERENCE_RESOLVED','NO_COMPATIBLE_REFERENCE')
        profile,resource = reference
        stats = self.references.statistics(profile)
        target['reference']={'target_id':binding.reference_target_id,'version':settings.reference_version,
            'profile_sha256':resource.profile.sha256,'independent_speaker_count':int(profile['speaker_count']),
            'readiness':profile['profile_status'],**{k:getattr(stats,k) for k in ('median','mad','q25','q75','iqr','minimum','maximum')}}
        described = describe_duration(duration.rate_normalized_duration,stats)
        target['deviation']={k:described[k] for k in ('signed_delta','ratio_to_median','mad_distance','direction','inside_iqr','inside_observed_min_max')}
        target['deviation']['warnings']=[] if described['mad_distance'] is not None else ['ZERO_MAD']
        target['availability'].update(reference=True,deviation=True)
        mark('DEVIATION_COMPUTED')
        overlap = audio.sha256 in {take['audio_sha256'] for speaker in profile['speaker_observations'] for take in speaker['takes']}
        provenance['candidate_audio_in_reference']=overlap
        if overlap: provenance['comparison_role']='IN_POPULATION_NATIVE_INTEGRATION_SMOKE'
        target['reasons'].append({'stage':'REALIZATION_COMPUTED','reason_code':REALIZATION_UNAVAILABLE,
                                 'message':'This version does not provide realization candidate comparison.'})
        target['evidence_status']='PARTIAL'
        output['status']='PARTIAL_EVIDENCE'
        for channel in ('raw_f0','rms'):
            if not target['availability'][channel]:
                target['reasons'].append({'stage':'EVIDENCE_RECONCILED','reason_code':channel.upper()+'_UNAVAILABLE',
                                         'message':'This acoustic channel is unavailable; duration evidence remains available.'})
        output['warnings']=[{'stage':'REFERENCE_RESOLVED','reason_code':'CROSS_SENTENCE_CONTEXT_NOT_VALIDATED',
            'message':'Exact lexical compatibility does not establish sentence-context distribution equivalence.'}]
        mark('EVIDENCE_RECONCILED')
        return finish()
