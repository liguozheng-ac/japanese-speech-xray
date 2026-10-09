from speech_xray.reference.manifest import keys, text
from .models import SourceType
from .validation import identifier, artifact

PERMISSIONS = ('local_analysis','derived_feature_publication','aggregate_publication',
               'raw_audio_redistribution','transcript_redistribution')
RIGHTS_FIELDS = ('record_id','dataset_id','dataset_version','source_type','access_basis',
                'access_record','permissions','review_notes')


def validate_rights(record, dataset, base):
    keys(record,RIGHTS_FIELDS)
    identifier(record['record_id'])
    for key in ('dataset_id','dataset_version','source_type'):
        if record[key]!=dataset[key]:raise ValueError('RIGHTS_DATASET_IDENTITY_MISMATCH')
    SourceType(record['source_type']);text(record['access_basis'],'access basis')
    if not isinstance(record['review_notes'],str):raise ValueError('INVALID_RIGHTS_NOTES')
    keys(record['permissions'],PERMISSIONS)
    if any(value not in {'YES','NO','UNKNOWN'} for value in record['permissions'].values()):
        raise ValueError('INVALID_RIGHTS_PERMISSION')
    artifact(record['access_record'],base,required=bool(dataset['observations']))
    if dataset['observations'] and record['permissions']['local_analysis']!='YES':
        raise ValueError('LOCAL_ANALYSIS_NOT_PERMITTED')
    return record
