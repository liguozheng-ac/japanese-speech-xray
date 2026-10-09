"""Independent human records: no deviation or reference evidence import."""
from dataclasses import replace
from decimal import Decimal
from speech_xray.reference.manifest import keys,text,sha256
from .models import HumanCategory,WorkflowState,AnnotationSession
from .serialization import serialize,decode,identity,private_path
from .validation import identifier,artifact

ANNOTATION_FIELDS = ('schema_version','annotation_id','evaluation_run_id','observation_id',
    'blind_package_sha256','annotator_id','category','blind_attestation',
    'target_start_ms','target_end_ms','boundary_method','annotation_tool','notes')


def blind_package(dataset, observation_id):
    from .learner_manifest import validate_import
    validate_import(dataset)
    rows=[r for r in dataset.data['observations'] if r['observation_id']==observation_id]
    if len(rows)!=1:raise ValueError('OBSERVATION_ID_UNKNOWN')
    row=rows[0]
    if row['audio_identity'] is None:raise ValueError('BLIND_PACKAGE_AUDIO_REQUIRED')
    # The whitelist hides corpus labels, L1, analysis, references and boundaries.
    return {'schema_version':'0.1','package_type':'BLIND_HUMAN_ANNOTATION',
        'evaluation_run_id':dataset.data['evaluation_run_id'],'dataset_identity':dataset.identity,
        'observation_id':observation_id,'audio_identity':row['audio_identity'],
        'transcript':row['transcript'],'target':row['target'],
        'allowed_human_categories':[v.value for v in HumanCategory]}


def begin_annotation(package):
    keys(package,('schema_version','package_type','evaluation_run_id','dataset_identity','observation_id',
                  'audio_identity','transcript','target','allowed_human_categories'))
    if (package['schema_version']!='0.1' or package['package_type']!='BLIND_HUMAN_ANNOTATION'
            or package['allowed_human_categories']!=[v.value for v in HumanCategory]):
        raise ValueError('BLIND_PACKAGE_SCHEMA_INVALID')
    keys(package['dataset_identity'],('dataset_id','dataset_version','source_type','source_manifest_sha256'))
    from .validation import target
    if package['target'] is not None:target(package['target'])
    keys(package['audio_identity'],('path','sha256'))
    sha256(package['audio_identity']['sha256'])
    return AnnotationSession(package['evaluation_run_id'],package['observation_id'],
                             serialize(package['dataset_identity']),identity(package))


def validate_annotation(record):
    keys(record,ANNOTATION_FIELDS)
    if record['schema_version']!='0.1' or record['blind_attestation'] is not True:
        raise ValueError('PRIMARY_ANNOTATION_MUST_BE_BLIND')
    for key in ('annotation_id','evaluation_run_id','observation_id','annotator_id'):identifier(record[key])
    sha256(record['blind_package_sha256']);HumanCategory(record['category'])
    text(record['annotation_tool'],'annotation tool')
    if not isinstance(record['notes'],str):raise ValueError('ANNOTATION_NOTES_INVALID')
    start,end=record['target_start_ms'],record['target_end_ms']
    if start is None and end is None:
        if record['boundary_method']!='NOT_MEASURED':raise ValueError('UNMEASURED_BOUNDARY_METHOD_REQUIRED')
    elif (not all(isinstance(v,Decimal) and v.is_finite() for v in (start,end))
            or start<0 or end<=start or record['boundary_method']!='MANUAL_ACOUSTIC_REVIEW'):
        raise ValueError('INVALID_MANUAL_BOUNDARIES')
    return record


def submit_annotation(session, record):
    validate_annotation(record)
    if session.model_evidence_json is not None or session.adjudication_json is not None:
        raise ValueError('PRIMARY_ANNOTATION_LOCKED_AFTER_UNBLINDING_OR_ADJUDICATION')
    if (record['evaluation_run_id']!=session.evaluation_run_id
            or record['observation_id']!=session.observation_id
            or record['blind_package_sha256']!=session.blind_package_sha256):
        raise ValueError('ANNOTATION_IDENTITY_MISMATCH')
    prior=[decode(a) for a in session.primary_annotations]
    if any(a['annotator_id']==record['annotator_id'] or a['annotation_id']==record['annotation_id'] for a in prior):
        raise ValueError('ANNOTATION_CANNOT_OVERWRITE_PRIOR_JUDGMENT')
    records=tuple(sorted(session.primary_annotations+(serialize(record),),key=lambda a:decode(a)['annotator_id']))
    return replace(session,state=WorkflowState.ANNOTATED_BLIND,primary_annotations=records)


def attach_model_evidence(session, evidence_artifact):
    if not session.primary_annotations:raise ValueError('PRIMARY_BLIND_ANNOTATION_REQUIRED_BEFORE_MODEL')
    if session.model_evidence_json is not None:raise ValueError('MODEL_EVIDENCE_ALREADY_ATTACHED')
    from speech_xray.reference.json_input import read_json
    pinned=artifact(evidence_artifact,private_path(evidence_artifact['path']).parent)
    evidence,_=read_json(private_path(pinned['path']))
    if (evidence.get('representation')!='LEARNER_TARGET_DURATION_EVIDENCE'
            or evidence.get('evaluation_run_id')!=session.evaluation_run_id
            or evidence.get('observation_id')!=session.observation_id
            or serialize(evidence.get('dataset_identity'))!=session.dataset_identity_json):
        raise ValueError('MODEL_EVIDENCE_OBSERVATION_IDENTITY_MISMATCH')
    return replace(session,state=WorkflowState.ADJUDICATED if session.adjudication_json else WorkflowState.MODEL_EVIDENCE_ATTACHED,
                   model_evidence_json=serialize(pinned))


def adjudicate(session, adjudicator_id, category, notes, exposed_to_model):
    identifier(adjudicator_id);HumanCategory(category);text(notes,'adjudication notes')
    if type(exposed_to_model) is not bool:raise ValueError('ADJUDICATION_EXPOSURE_REQUIRED')
    if session.adjudication_json is not None or len(session.primary_annotations)<2:
        raise ValueError('ADJUDICATION_REQUIRES_MULTIPLE_PRIMARY_RECORDS')
    if session.model_evidence_json is not None and not exposed_to_model:
        raise ValueError('ADJUDICATION_CANNOT_CLAIM_BLIND_AFTER_MODEL_ATTACHMENT')
    value={'adjudicator_id':adjudicator_id,'category':category,'notes':notes,
           'exposed_to_model':exposed_to_model,
           'primary_annotation_ids':[decode(a)['annotation_id'] for a in session.primary_annotations]}
    return replace(session,state=WorkflowState.ADJUDICATED,adjudication_json=serialize(value))


def restore_session(package, records, model_evidence=None, adjudication=None):
    """Replay validated primary records; never trust a serialized state flag."""
    session=begin_annotation(package)
    for record in records:session=submit_annotation(session,record)
    if adjudication is not None and not adjudication['exposed_to_model']:
        session=adjudicate(session,adjudication['adjudicator_id'],adjudication['category'],adjudication['notes'],False)
    if model_evidence is not None:session=attach_model_evidence(session,model_evidence)
    if adjudication is not None and adjudication['exposed_to_model']:
        session=adjudicate(session,adjudication['adjudicator_id'],adjudication['category'],adjudication['notes'],True)
    return session
