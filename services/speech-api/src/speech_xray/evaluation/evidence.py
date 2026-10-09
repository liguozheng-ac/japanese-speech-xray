"""Different sentences retain identities; only explicit compatible targets compare."""
from dataclasses import asdict
from speech_xray.deviation.duration import FEATURES,FORMULAS,describe_duration
from speech_xray.deviation.validation import reference_validation
from .serialization import serialize,decode
from .pipeline import load_analysis,observation
from .matching import reference_descriptor,match_target


def compare_learner(analysis, reference, run):
    dataset=analysis.dataset;row=observation(dataset,analysis.observation_id)
    value={'schema_version':'0.1','representation':'LEARNER_TARGET_DURATION_EVIDENCE',
        'evaluation_run_id':run.run_id,'observation_id':analysis.observation_id,
        'dataset_identity':dataset.identity,'dataset_role':'LEARNER',
        'status':'ABSTAIN_INVALID_LEARNER_EVIDENCE','reason_codes':[],
        'candidate':None,'reference':None,'matching':None,'model_evidence':None,
        'interpretation':'DESCRIPTIVE_DURATION_ONLY_NOT_HUMAN_ANNOTATION'}
    try:
        if (dataset.data['evaluation_run_id']!=run.run_id or dataset.sha256 not in run.dataset_hashes
                or row['speaker_id'] not in run.learner_speakers):raise ValueError('EVALUATION_RUN_BINDING_MISMATCH')
        current=load_analysis(dataset,analysis.observation_id,decode(analysis.sources_json),analysis.span_id)
        if current!=analysis:raise ValueError('LEARNER_ANALYSIS_OBJECT_MISMATCH')
        reference_validation(reference)
        refs={s.speaker_id for s in reference.profile.speakers}
        if set(run.learner_speakers)&refs or not refs<=set(run.reference_speakers):
            raise ValueError('LEARNER_REFERENCE_ROLE_FIREWALL')
        candidate_audio=row['audio_identity']['sha256']
        if candidate_audio in {dict(t.entry.sources)['audio'].sha256 for s in reference.profile.speakers for t in s.takes}:
            raise ValueError('LEARNER_AUDIO_INCLUDED_IN_REFERENCE')
        descriptor=reference_descriptor(reference)
        match=match_target(decode(analysis.target_json),[descriptor]);value['matching']=match
        if match['status']!='COMPATIBLE_LINGUISTIC_TARGET':
            value['status']='NO_COMPATIBLE_REFERENCE';value['reason_codes']=match['reason_codes'];return value
        p=reference.profile
        value.update(status='OK',candidate={'speaker_id':row['speaker_id'],'utterance_id':row['utterance_id'],
            'target':decode(analysis.target_json),'original_span':analysis.original_span.to_dict(),
            'rate_context':analysis.rate.to_dict(),'duration':asdict(analysis.duration),'sources':decode(analysis.sources_json)},
            reference={'identity':p.manifest.reference_set_id,'version':reference.version,
                'origin_identity':reference.origin_reference_set_id,'target':p.manifest.target.to_dict(),
                'n':len(p.speakers),'speaker_ids':sorted(refs),'normalization':p.to_dict()['normalization'],
                'profile_artifact':asdict(reference.profile_artifact),'origin_profile_artifact':asdict(reference.origin_profile_artifact),
                'source_manifest':{'path':p.manifest.source,'sha256':p.manifest.sha256},
                'feature_statistics':{k:s.to_dict() for k,s in p.statistics if k in FEATURES}},
            model_evidence={'comparison_scope':'EXPLICIT_LINGUISTIC_TARGET_ACROSS_UTTERANCES',
                'implementation':'UNCHANGED_TASK010_DESCRIBE_DURATION','derived_decimal_precision':50,
                'primary_feature':'rate_normalized_duration','formulas':FORMULAS,
                'features':{k:describe_duration(getattr(analysis.duration,k),dict(p.statistics)[k]) for k in FEATURES}})
    except (OSError,ValueError,TypeError,KeyError,AttributeError,ArithmeticError) as error:
        value.update(status='ABSTAIN_INVALID_LEARNER_EVIDENCE',reason_codes=[str(error)],
                     candidate=None,reference=None,model_evidence=None)
    return value
