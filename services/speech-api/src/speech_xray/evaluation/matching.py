"""Exact linguistic compatibility, without sentence rebinding or model outcomes."""
from pathlib import Path
from speech_xray.reference.json_input import read_json
from .validation import target
from .serialization import identity

SIGNATURE_FIELDS=('target_surface','target_reading','target_mora_span','target_vowel_class',
                  'word_mora_indices','mapping_basis','lexical_identity')


def signature(value):
    target(value)
    return tuple(tuple(value[k]) if isinstance(value[k],list) else value[k] for k in SIGNATURE_FIELDS)


def reference_descriptor(reference):
    from speech_xray.deviation.validation import reference_validation
    reference_validation(reference)
    p=reference.profile;t=p.manifest.target
    lexical=[];sources=[]
    for speaker in p.speakers:
        for take in speaker.takes:
            source=dict(take.entry.sources)['mora_analysis']
            mora,sha=read_json(Path(source.path))
            if sha!=source.sha256:raise ValueError('REFERENCE_LINGUISTIC_SOURCE_CHANGED')
            word=next(w for w in mora['words'] if w['index']==t.word_index)
            value={'target_id':t.target_id,'target_surface':word['surface'],'target_reading':word['reading'],
                'target_mora_span':t.mora_span,'target_vowel_class':t.vowel_class,
                'word_mora_indices':list(t.word_mora_indices),'mapping_basis':t.mapping_basis,
                'lexical_identity':word['surface']}
            lexical.append(value);sources.append({'path':source.path,'sha256':source.sha256})
    if not lexical or any(signature(x)!=signature(lexical[0]) for x in lexical):
        raise ValueError('REFERENCE_LEXICAL_IDENTITY_NOT_UNANIMOUS')
    return {'schema_version':'0.1','dataset_role':'REFERENCE_SPEAKER','reference_identity':p.manifest.reference_set_id,
        'reference_version':reference.version,'reference_target':lexical[0],
        'profile_artifact':{'path':reference.profile_artifact.path,'sha256':reference.profile_artifact.sha256},
        'linguistic_sources':sources,'feature_contract':{'normalization_version':'0.1',
            'primary_feature':'rate_normalized_duration','rate_definition':p.to_dict()['rate_definition']}}


def match_target(candidate, descriptors):
    wanted=signature(candidate);matches=[]
    for ref in descriptors:
        contract=ref.get('feature_contract',{})
        if (ref.get('dataset_role')=='REFERENCE_SPEAKER' and signature(ref['reference_target'])==wanted
                and contract.get('normalization_version')=='0.1'
                and contract.get('primary_feature')=='rate_normalized_duration'
                and contract.get('rate_definition')=='FIRST_NONEMPTY_WORD_ONSET_TO_LAST_NONEMPTY_WORD_OFFSET_INCLUDING_INTERNAL_PAUSES'):
            matches.append(ref)
    if len(matches)!=1:
        return {'status':'NO_COMPATIBLE_REFERENCE','reason_codes':['AMBIGUOUS_REFERENCE' if matches else 'NO_LINGUISTIC_FEATURE_MATCH'],
                'candidate_target':candidate,'reference':None}
    ref=matches[0]
    return {'status':'COMPATIBLE_LINGUISTIC_TARGET','reason_codes':[], 'candidate_target':candidate,'reference':ref,
        'matching_policy':'EXACT_SURFACE_READING_LOCAL_MORA_VOWEL_BASIS_FEATURE_V1',
        'matching_identity':identity({'candidate':candidate,'reference':ref}),
        'sentence_identity_required':False,'outcome_dependent_matching':False}
