from collections import Counter
from .models import HumanCategory
from .learner_manifest import validate_import


def dataset_readiness(datasets, run, sessions=()):
    real_imported=[];fixtures=[];outcomes=[];lookup={}
    for dataset in datasets:
        if dataset.sha256 not in run.dataset_hashes:raise ValueError('READINESS_RUN_DATASET_MISMATCH')
        for outcome in validate_import(dataset):
            outcome={**outcome,'dataset_id':dataset.data['dataset_id'],'dataset_version':dataset.data['dataset_version']}
            outcomes.append(outcome)
            lookup[(dataset.data['dataset_id'],outcome['observation_id'])]=(dataset,outcome)
            if dataset.data['material_kind']=='AUTHORED_STRUCTURAL_FIXTURE':fixtures.append(outcome)
            elif outcome['status']=='IMPORTED':real_imported.append(outcome)
    annotations=[];usable=[];attached=0;comparable=0;disagreements=0
    seen=set()
    for session in sessions:
        value=session.to_dict();key=(value['dataset_identity']['dataset_id'],session.observation_id)
        if key in seen or key not in lookup or session.evaluation_run_id!=run.run_id:raise ValueError('READINESS_ANNOTATION_IDENTITY_MISMATCH')
        seen.add(key);dataset,outcome=lookup[key]
        if value['dataset_identity']!=dataset.identity:raise ValueError('READINESS_ANNOTATION_DATASET_CHANGED')
        if dataset.data['material_kind']!='REAL_LEARNER_AUDIO' or outcome['status']!='IMPORTED':continue
        primary=value['human_annotation']
        from .annotation import validate_annotation,blind_package
        from .serialization import identity,decode
        from .validation import artifact
        from speech_xray.reference.json_input import read_json
        from pathlib import Path
        if session.blind_package_sha256!=identity(blind_package(dataset,session.observation_id)):
            raise ValueError('READINESS_BLIND_PACKAGE_CHANGED')
        for record in primary:
            validate_annotation(record)
            if (record['blind_package_sha256']!=session.blind_package_sha256
                    or record['evaluation_run_id']!=session.evaluation_run_id
                    or record['observation_id']!=session.observation_id):
                raise ValueError('READINESS_PRIMARY_RECORD_MISMATCH')
        if primary:annotations.append(outcome)
        categories={a['category'] for a in primary}
        if session.adjudication_json is not None:categories={decode(session.adjudication_json)['category']}
        if len(categories)==1 and next(iter(categories)) in {HumanCategory.LONG_VOWEL_REALIZED,HumanCategory.LONG_VOWEL_REDUCED_OR_ABSENT}:
            usable.append(outcome)
        if value['disagreement'] and session.adjudication_json is None:disagreements+=1
        if session.model_evidence_json is not None:
            pinned=artifact(decode(session.model_evidence_json),Path(dataset.source).parent)
            model,_=read_json(Path(pinned['path']))
            if model['dataset_identity']!=dataset.identity or model['observation_id']!=session.observation_id:
                raise ValueError('READINESS_MODEL_IDENTITY_MISMATCH')
            attached+=1
            if model['status']=='OK' and model.get('model_evidence') is not None:comparable+=1
    count=len(real_imported);labelled=len(usable)
    if not count:status='TOOLING_READY_NO_LEARNER_DATA'
    elif not annotations:status='LEARNER_DATA_IMPORTED'
    elif len(annotations)<count:status='ANNOTATION_INCOMPLETE'
    elif not labelled:status='INSUFFICIENT_LABELLED_DATA'
    else:status='READY_FOR_BLIND_EVALUATION'
    return {'schema_version':'0.1','evaluation_run_id':run.run_id,'status':status,
        'real_imported_observations':count,'real_learner_speakers':len({r['speaker_id'] for r in real_imported}),
        'real_blind_annotated_observations':len(annotations),'real_usable_labelled_observations':labelled,
        'real_model_evidence_attached':attached,'authored_fixture_observations':len(fixtures),
        'real_comparable_evidence_observations':comparable,'real_unresolved_disagreements':disagreements,
        'split_speaker_counts':dict(sorted(Counter(s for _,s in run.assignments).items())),
        'import_outcomes':outcomes,'scientific_minimum_learner_n':None,
        'LEARNER_EVALUATION_TOOLING_READY':True,
        'REAL_LABELLED_LEARNER_DATA_READY':bool(count and labelled==count and comparable==count and not disagreements),
        'data_gate_meaning':'ALL_DECLARED_REAL_OBSERVATIONS_HAVE_USABLE_BLIND_LABELS_AND_ATTACHED_EVIDENCE_NOT_SCIENTIFIC_SUFFICIENCY',
        'no_diagnostic_performance_estimate':True}
