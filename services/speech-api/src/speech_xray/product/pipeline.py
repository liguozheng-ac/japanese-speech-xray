"""One primary timeline plus one equal-prior realization probe; frozen science calls."""
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from time import perf_counter
import logging
from speech_xray.acoustics.models import evidence_json
from speech_xray.reference.domains import interval_inside_audio
from .audio import validate_audio
from .serialization import InternalAnalysisResult, identity
from .orchestrator import report_stage


class ProductPipeline:
    def __init__(self, settings, references, runtime):
        self.settings, self.references, self.runtime = settings, references, runtime

    def analyse(self, request):
        from speech_xray.japanese.long_vowel_mapper import analyze_mora
        from speech_xray.japanese.reading import SudachiReadingProvider
        from speech_xray.acoustics.mora_input import load_mora_analysis
        from speech_xray.acoustics.pipeline import extract_acoustic_evidence
        from speech_xray.reference.models import ReferenceManifest, ReferenceEntry, TargetIdentity, ArtifactReference
        from speech_xray.reference.integrity import validate_entry, IntegrityError
        from speech_xray.reference.speech_rate import measure_utterance_rate
        from speech_xray.reference.normalization import normalize_duration
        from speech_xray.deviation.duration import describe_duration
        from speech_xray.realization import observe
        settings, binding = self.settings, request.binding
        trace, timings = [], {}
        started = perf_counter()
        def mark(stage):
            trace.append({'stage': stage, 'reason_code': 'OK'})
            logging.getLogger('speech_xray.product').info('stage request_id=%s stage=%s reason_code=OK',request.request_id,stage)
        def write(name, value):
            path = request.workspace / name
            path.write_bytes(evidence_json(value).encode('utf-8'))
            return ArtifactReference(str(path), sha256(path.read_bytes()).hexdigest())
        t = perf_counter(); audio = validate_audio(request.audio_path, settings)
        timings['input_validation_ms'] = (perf_counter()-t)*1000
        mark('INPUT_VALIDATED'); mark('PROMPT_RESOLVED')
        public_audio = {'sha256': audio.sha256, 'duration_ms': audio.duration_ms, 'sample_rate_hz': audio.sample_rate_hz,
                        'channels': audio.channels, 'sample_count': audio.frame_count, 'decoded_format': 'WAV'}
        resource = self.references.resources.get(binding.reference_target_id)
        model_hashes = {name: getattr(settings, name).sha256 for name in ('acoustic_model', 'dictionary', 'g2p_model')}
        fingerprint = identity({'audio_sha256': audio.sha256, 'binding_sha256': binding.binding_sha256,
            'reference_profile_sha256': resource.profile.sha256 if resource else None,
            'policy_version': settings.policy_version, 'model_hashes': model_hashes,
            'runtime_identity': settings.runtime_identity_sha256, 'mfa_version': settings.mfa_version,
            'pipeline_version': 'product-m1-1.0.0', 'primary_alignment': 'OFFICIAL_CANONICAL_DICTIONARY',
            'competition': 'COMPETITION_EQUAL_PRIOR'})
        target = {'target_id': binding.target_id, 'surface': binding.surface, 'reading': binding.reading,
            'word_index': None, 'mora_indices': [], 'mora_span': 2, 'vowel_class': binding.vowel_class,
            'mapping_basis': binding.mapping_basis, 'time_span': None, 'duration': None, 'reference': None,
            'deviation': None, 'realization': None, 'acoustics': None,
            'availability': {k: False for k in ('duration','reference','deviation','realization','raw_f0','rms')},
            'evidence_status': 'ABSTAINED', 'reasons': []}
        provenance = {'analysis_policy_version': settings.policy_version, 'prompt_binding_version': binding.binding_version,
            'prompt_binding_sha256': binding.binding_sha256, 'prompt_pack_sha256': binding.pack_sha256,
            'alignment_engine_version': settings.mfa_version, 'acoustic_model_sha256': model_hashes['acoustic_model'],
            'dictionary_sha256': model_hashes['dictionary'], 'g2p_model_sha256': model_hashes['g2p_model'],
            'runtime_identity_sha256': settings.runtime_identity_sha256, 'candidate_audio_in_reference': False,
            'comparison_role': 'DESCRIPTIVE_ONLY'}
        output = {'schema_version':'1.0.0', 'analysis_id':request.request_id, 'analysis_fingerprint': fingerprint,
            'status':'ABSTAINED', 'prompt':binding.prompt.model_dump(), 'audio':public_audio,
            'timeline':None, 'targets':[target], 'warnings':[], 'provenance':provenance}
        def abstain(stage, code):
            target['reasons'].append({'stage':stage, 'reason_code':code, 'message':'Declared target evidence is unavailable.'})
            trace.append({'stage':stage, 'reason_code':code})
            return finish()
        def finish():
            report_stage(request, 5)
            mark('RESPONSE_ASSEMBLED'); timings['total_ms']=(perf_counter()-started)*1000
            audit = {'workspace':str(request.workspace), 'alignment_artifact_hashes':{
                p.relative_to(request.workspace).as_posix():sha256(p.read_bytes()).hexdigest()
                for name in ('primary','competition') for p in (request.workspace/name).rglob('*')
                if p.is_file() and p.suffix in ('.TextGrid','.log')}}
            return InternalAnalysisResult(output, trace, timings, audit)
        report_stage(request, 2)
        t=perf_counter(); alignment=self.runtime.align(request.audio_path,binding,request.workspace/'primary')
        timings['alignment_ms']=(perf_counter()-t)*1000
        if alignment is None: return abstain('ALIGNED','ALIGNMENT_UNUSABLE')
        mark('ALIGNED')
        if not all(interval_inside_audio(w.start_ms,w.end_ms,audio.frame_count,audio.sample_rate_hz)
                   for w in alignment.words if w.label.strip()):
            return abstain('TIMING_DOMAIN','CORE_WORD_OUTSIDE_AUDIO_DOMAIN')
        # TASK-009 permits rounded blank trailing silence. It is not an acoustic word/phone.
        labelled = [p for p in alignment.phones if p.label.strip()]
        if not all(interval_inside_audio(p.start_ms,p.end_ms,audio.frame_count,audio.sample_rate_hz) for p in labelled):
            return abstain('TIMING_DOMAIN','PHONE_OUTSIDE_AUDIO_DOMAIN')
        t=perf_counter(); mora=analyze_mora(alignment,SudachiReadingProvider())
        timings['linguistic_mapping_ms']=(perf_counter()-t)*1000
        spans=[s for s in mora.long_vowel_spans
            if mora.words[s.word_index].surface==binding.surface
            and mora.words[s.word_index].reading_result.reading==binding.reading
            and tuple(mora.morae[i].word_mora_index for i in s.mora_indices)==binding.local_mora_indices
            and (s.vowel_class,s.mapping_basis)==(binding.vowel_class,binding.mapping_basis)]
        span_by_mora={i:s for s in mora.long_vowel_spans for i in s.mora_indices}
        output['timeline']={'start_ms':Decimal(0),'end_ms':audio.duration_ms,'basis':'PRIMARY_ANALYSIS_ALIGNMENT',
            'words':[{'index':w.index,'surface':w.surface,'reading':w.reading_result.reading,
                      'start_ms':w.start_ms,'end_ms':w.end_ms} for w in mora.words],
            'phones':[{'index':i,'symbol':p.label,'start_ms':p.start_ms,'end_ms':p.end_ms,
                       'word_index':next((w.index for w in mora.words if i in w.phone_indices),None)}
                      for i,p in enumerate(alignment.phones) if p.label.strip()],
            'morae':[{'index':m.index,'word_index':m.word_index,'word_mora_index':m.word_mora_index,
                'representation':m.reading,'kind':m.kind,
                'shared_span':{'start_ms':span_by_mora[m.index].start_ms,'end_ms':span_by_mora[m.index].end_ms}
                    if m.index in span_by_mora else None,
                'timing_basis':'SHARED_ORIGINAL_LONG_PHONE' if m.index in span_by_mora else 'NO_INDIVIDUAL_ACOUSTIC_BOUNDARY'}
                for m in mora.morae]}
        if len(spans)!=1: return abstain('TARGET_MAPPED','TARGET_NOT_MAPPED')
        span=spans[0]; mark('TARGET_MAPPED')
        target.update(word_index=span.word_index,mora_indices=list(span.mora_indices),
                      time_span={'start_ms':span.start_ms,'end_ms':span.end_ms})
        alignment_ref=write('alignment.json',alignment.to_dict()); mora_ref=write('mora.json',mora.to_dict())
        transcript=request.workspace/'prompt.lab'; transcript.write_bytes((binding.prompt.display_text+'\n').encode('utf-8'))
        report_stage(request, 3)
        t=perf_counter(); acoustic=extract_acoustic_evidence(request.audio_path,load_mora_analysis(mora_ref.path))
        timings['acoustics_ms']=(perf_counter()-t)*1000; mark('ACOUSTICS_EXTRACTED')
        acoustic_ref=write('acoustics.json',acoustic.to_dict())
        sources=(('audio',ArtifactReference(str(request.audio_path),audio.sha256)),
            ('transcript',ArtifactReference(str(transcript),sha256(transcript.read_bytes()).hexdigest())),
            ('alignment',alignment_ref),('mora_analysis',mora_ref),('acoustic_evidence',acoustic_ref))
        target_identity=TargetIdentity(binding.target_id,span.word_index,binding.local_mora_indices,
                                       span.phone_label,span.vowel_class,2,span.mapping_basis)
        entry=ReferenceEntry(binding.prompt.prompt_id,binding.target_id,'ephemeral-request',request.request_id,
                             request.request_id,span.id,sources)
        context=ReferenceManifest('ephemeral-product-validation',binding.prompt.prompt_id,dict(sources)['transcript'].sha256,
            target_identity,(('material_kind','PRODUCT_EPHEMERAL_UPLOAD'),),'Never a native population',(entry,),'','')
        try: validated=validate_entry(context,entry)
        except IntegrityError: return abstain('TIMING_DOMAIN','TARGET_EVIDENCE_INTEGRITY_FAILURE')
        if acoustic.audio.sha256!=audio.sha256: return abstain('TIMING_DOMAIN','AUDIO_IDENTITY_MISMATCH')
        duration=normalize_duration(validated.span,measure_utterance_rate(validated.alignment,validated.mora_count))
        target['duration']=asdict(duration); target['availability']['duration']=True; mark('NORMALIZED')
        selected=next(s for s in acoustic.spans if s.original_span.id==span.id)
        target['acoustics']={'selected_frame_count':selected.frame_count,'voiced_frame_count':selected.voiced_frame_count,
            'raw_f0_median_hz':selected.raw_f0_hz.median,'rms_median':selected.rms.median,
            'extraction_status':selected.extraction_status}
        target['availability'].update(raw_f0=selected.raw_f0_hz.median is not None,rms=selected.rms.median is not None)
        t=perf_counter(); reference=self.references.resolve(binding); timings['reference_ms']=(perf_counter()-t)*1000
        if reference is None: return abstain('REFERENCE_RESOLVED','NO_COMPATIBLE_REFERENCE')
        profile,resource=reference; mark('REFERENCE_RESOLVED'); stats=self.references.statistics(profile)
        target['reference']={'target_id':binding.reference_target_id,'version':'task009-v2','profile_sha256':resource.profile.sha256,
            'independent_speaker_count':int(profile['speaker_count']),'readiness':profile['profile_status'],
            **{k:getattr(stats,k) for k in ('median','mad','q25','q75','iqr','minimum','maximum')}}
        described=describe_duration(duration.rate_normalized_duration,stats)
        target['deviation']={k:described[k] for k in ('signed_delta','ratio_to_median','mad_distance','direction','inside_iqr','inside_observed_min_max')}
        target['deviation']['warnings']=[] if described['mad_distance'] is not None else ['ZERO_MAD']
        target['availability'].update(reference=True,deviation=True); mark('DEVIATION_COMPUTED')
        overlap=audio.sha256 in {take['audio_sha256'] for speaker in profile['speaker_observations'] for take in speaker['takes']}
        provenance['candidate_audio_in_reference']=overlap
        if overlap: provenance['comparison_role']='IN_POPULATION_NATIVE_INTEGRATION_SMOKE'
        report_stage(request, 4)
        t=perf_counter(); hypotheses=self.runtime.hypotheses(binding,span.word_index)
        if hypotheses.reduced is None: return abstain('REALIZATION_COMPUTED','UNSUPPORTED_REDUCED_HYPOTHESIS')
        competition=self.runtime.align(request.audio_path,binding,request.workspace/'competition',hypotheses)
        realization={'canonical_pronunciation':list(hypotheses.canonical),'experimental_reduced_pronunciation':list(hypotheses.reduced),
            'selected_variant':'ALIGNMENT_FAILED','variant_identity_status':'ALIGNMENT_FAILED','evidence_status':'ABSTAINED'}
        if competition is not None:
            try:
                observation=observe(competition,hypotheses)
                if not interval_inside_audio(observation['phone_start_ms'],observation['phone_end_ms'],audio.frame_count,audio.sample_rate_hz):
                    raise ValueError('COMPETITION_TARGET_OUTSIDE_DOMAIN')
                realization.update(selected_variant=observation['selected'],variant_identity_status=observation['identity_status'],evidence_status='AVAILABLE')
            except ValueError:
                realization.update(selected_variant='AMBIGUOUS_OR_UNRESOLVED',variant_identity_status='AMBIGUOUS_VARIANT_IDENTITY')
        timings['realization_ms']=(perf_counter()-t)*1000; target['realization']=realization
        if realization['evidence_status']!='AVAILABLE': return abstain('REALIZATION_COMPUTED','AMBIGUOUS_VARIANT_IDENTITY')
        mark('REALIZATION_COMPUTED'); target['availability']['realization']=True
        missing=[k for k in ('raw_f0','rms') if not target['availability'][k]]
        target['evidence_status']='PARTIAL' if missing else 'AVAILABLE'
        output['status']='PARTIAL_EVIDENCE' if missing else 'COMPLETED'
        for channel in missing:
            target['reasons'].append({'stage':'EVIDENCE_RECONCILED','reason_code':channel.upper()+'_UNAVAILABLE',
                                     'message':'This acoustic channel is unavailable; duration evidence remains available.'})
        output['warnings']=[{'stage':'REFERENCE_RESOLVED','reason_code':'CROSS_SENTENCE_CONTEXT_NOT_VALIDATED',
                            'message':'Exact lexical compatibility does not establish sentence-context distribution equivalence.'}]
        mark('EVIDENCE_RECONCILED')
        return finish()
