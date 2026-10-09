from .models import EvaluationRun,Split
from .validation import identifier
from .learner_manifest import validate_import


def create_run(run_id, datasets, assignments, reference_speakers=()):
    identifier(run_id)
    if len({d.data['dataset_id'] for d in datasets})!=len(datasets):raise ValueError('DUPLICATE_DATASET_ID')
    speakers=set();roles=[]
    for dataset in datasets:
        validate_import(dataset)
        if dataset.data['evaluation_run_id']!=run_id or dataset.data['dataset_role']!='LEARNER':
            raise ValueError('IMMUTABLE_EVALUATION_ROLE_OR_RUN_MISMATCH')
        roles.append((dataset.data['dataset_id'],'LEARNER'))
        speakers.update(r['speaker_id'] for r in dataset.data['observations'])
    refs=tuple(sorted(reference_speakers))
    if len(set(refs))!=len(refs) or speakers & set(refs):raise ValueError('LEARNER_REFERENCE_ROLE_FIREWALL')
    pairs=[];seen=set()
    for speaker,split in assignments:
        identifier(speaker);Split(split)
        if speaker in seen:raise ValueError('SPEAKER_IN_MULTIPLE_SPLITS')
        seen.add(speaker);pairs.append((speaker,str(split)))
    if seen!=speakers:raise ValueError('EXACT_SPEAKER_SPLIT_COVERAGE_REQUIRED')
    return EvaluationRun(run_id,tuple(sorted(roles)),tuple(sorted(speakers)),refs,
                         tuple(sorted(pairs)),tuple(sorted(d.sha256 for d in datasets)))


def selection_contract(run, speaker):
    split=dict(run.assignments)[speaker]
    return {'speaker_id':speaker,'split':split,'selection_allowed_in_task011':False,
            'selection_allowed_in_later_task':split==Split.CALIBRATION,
            'held_out_test_selection_forbidden':True}


def require_reference_speaker(run, speaker):
    if speaker in run.learner_speakers or speaker not in run.reference_speakers:
        raise ValueError('LEARNER_REFERENCE_ROLE_FIREWALL')


def load_splits(path, datasets, reference_speakers=()):
    from speech_xray.reference.json_input import read_json
    from speech_xray.reference.manifest import keys
    from .serialization import private_path
    value,_=read_json(private_path(path))
    keys(value,('schema_version','evaluation_run_id','dataset_hashes','assignments'))
    if value['schema_version']!='0.1' or sorted(value['dataset_hashes'])!=sorted(d.sha256 for d in datasets):
        raise ValueError('SPLIT_DATASET_VERSION_MISMATCH')
    if not isinstance(value['assignments'],list):raise ValueError('INVALID_SPLIT_ARRAY')
    pairs=[]
    for row in value['assignments']:
        keys(row,('speaker_id','split'));pairs.append((row['speaker_id'],row['split']))
    return create_run(value['evaluation_run_id'],datasets,pairs,reference_speakers)
