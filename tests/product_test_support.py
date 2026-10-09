"""Authored structural evidence and replaceable analyzers; no private dependencies."""
from copy import deepcopy
from decimal import Decimal as D
import json
import time
from reference_test_support import ROOT
from speech_xray.product.audio import validate_audio
from speech_xray.product.serialization import InternalAnalysisResult, identity
from speech_xray.product.errors import ProductError


def fixture():
    return json.loads((ROOT/'data/examples/api-v1-analysis-response.json').read_text(encoding='utf-8'),parse_float=D)


class FakeAnalyzer:
    def __init__(self, settings, mode='available', delay=0):
        self.settings, self.mode, self.delay = settings, mode, delay

    def analyse(self, request):
        audio=validate_audio(request.audio_path,self.settings)
        (request.workspace/'private-marker.txt').write_text('private_path speaker_id debug_command')
        time.sleep(self.delay)
        if self.mode=='operational': raise ProductError('ALIGNMENT_RUNTIME_UNAVAILABLE','ALIGNED','TEST_RUNTIME_UNAVAILABLE')
        if self.mode=='unexpected': raise RuntimeError('PRIVATE_PATH_SECRET_SPEAKER_DEBUG_COMMAND')
        row=fixture();row.update(analysis_id=request.request_id,prompt=request.binding.prompt.model_dump())
        row['audio'].update(sha256=audio.sha256,duration_ms=audio.duration_ms,sample_count=audio.frame_count,sample_rate_hz=audio.sample_rate_hz)
        row['analysis_fingerprint']=identity({'audio':audio.sha256,'binding':request.binding.binding_sha256})
        if self.mode=='abstain':
            row['status']='ABSTAINED';row['timeline']=None
            for target in row['targets']:
                for key in ('duration','reference','deviation','realization','acoustics','time_span'):target[key]=None
                target['availability']={k:False for k in target['availability']}
                target['evidence_status']='ABSTAINED';target['reasons']=[{'stage':'TARGET_MAPPED','reason_code':'TARGET_NOT_MAPPED','message':'Declared target is unavailable.'}]
        if self.mode=='partial':
            row['status']='PARTIAL_EVIDENCE';row['targets'][0]['evidence_status']='PARTIAL'
            row['targets'][0]['acoustics']['raw_f0_median_hz']=None
            row['targets'][0]['availability']['raw_f0']=False
            row['targets'][0]['reasons']=[{'stage':'ACOUSTICS_EXTRACTED','reason_code':'RAW_F0_UNAVAILABLE','message':'Raw F0 is unavailable.'}]
        return InternalAnalysisResult(row,[{'stage':'RESPONSE_ASSEMBLED','reason_code':'OK'}],
                                      {'total_ms':self.delay*1000},{'private_path':'secret','speaker_id':'secret','debug_command':'secret'})
