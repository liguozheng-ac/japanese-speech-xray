"""Count upstream extraction independently of whole-bundle reference admission."""
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
from speech_xray.acoustics.mora_input import load_mora_analysis
from speech_xray.acoustics.models import ExtractionStatus
from speech_xray.corpus.batch_plan import digest
from .cache import read_control,safe_directory
from .observations import map_target


def verify_job_sources(job,bundle):
    """A valid receipt must still belong to this official speaker/prompt input."""
    if bundle['status']!='PASS':return
    refs=bundle['artifacts'];audio=refs['audio'];lab=refs['transcript']
    if (safe_directory(audio['path'])!=safe_directory(job['audio_path'])
            or audio['sha256']!=job['audio_sha256'] or digest(audio['path'])!=job['audio_sha256']):
        raise ValueError('AUDIO_IDENTITY_MISMATCH')
    # Preserve the frozen new_text writer's platform newline, including Windows
    # CRLF. This verifies the actual LAB bytes, not only the official text hash.
    expected=hashlib.sha256((job['text']+'\n').replace('\n',os.linesep).encode('utf-8')).hexdigest()
    if lab['sha256']!=expected or digest(safe_directory(lab['path']))!=expected:
        raise ValueError('TRANSCRIPT_IDENTITY_MISMATCH')


def observed_stages(target,prompt,bundle):
    refs=bundle.get('artifacts',{})
    result={'mapping_success':False,'acoustic_success':False,
        'acoustic_span_status':'NOT_RUN','utterance_acoustic_status':'NOT_RUN'}
    if 'mora_analysis' not in refs:return result
    value,_=read_control(refs['mora_analysis']['path'])
    mapped=load_mora_analysis(refs['mora_analysis']['path'])
    # A view of existing TASK-003 serialization, never a second mora analysis.
    view=SimpleNamespace(words=tuple(SimpleNamespace(surface=w['surface'],
        reading_result=SimpleNamespace(reading=w['reading'])) for w in value['words']),
        morae=tuple(SimpleNamespace(word_mora_index=m['word_mora_index']) for m in value['morae']),
        long_vowel_spans=mapped.long_vowel_spans)
    span,_=map_target(target,prompt,view)
    if span is None:return result
    result.update(mapping_success=True, mapped_span_id=span.id)
    if 'acoustic_evidence' not in refs:return result
    acoustic,_=read_control(refs['acoustic_evidence']['path'])
    result['utterance_acoustic_status']=acoustic['extraction_status']
    evidence=[s for s in acoustic['span_evidence'] if s['span_id']==span.id]
    if len(evidence)!=1:
        result['acoustic_span_status']='ACOUSTIC_SPAN_MISSING_OR_DUPLICATE'
        return result
    status=ExtractionStatus(evidence[0]['extraction_status'])
    result['acoustic_span_status']=str(status)
    # TASK-005 duration evidence remains usable without voiced F0. Full pitch/
    # track status is retained separately; it never enters the duration profile.
    result['acoustic_success']=(status not in {ExtractionStatus.INVALID_AUDIO,
        ExtractionStatus.INVALID_SPAN,ExtractionStatus.SPAN_OUT_OF_AUDIO_RANGE}
        and evidence[0]['sample_interval'] is not None)
    return result
