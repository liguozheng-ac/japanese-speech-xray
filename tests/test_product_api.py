"""Public HTTP/contract/resource tests using explicitly synthetic analysis injection."""
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal as D
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
import wave
from fastapi.testclient import TestClient
from pydantic import ValidationError
from reference_test_support import ROOT
from product_test_support import FakeAnalyzer,fixture
from speech_xray.api.app import create_app
from speech_xray.product.config import Settings
from speech_xray.product.models import SpeechXRayAnalysisResponse,TimeSpan
from speech_xray.product.prompts import PromptRegistry
from speech_xray.product.serialization import InternalAnalysisResult,project,response_bytes,identity
from speech_xray.product.errors import ProductError,ERRORS
from speech_xray.product.orchestrator import ProductOrchestrator


def wav(frames=16000,rate=16000,channels=1,width=2):
    buffer=BytesIO()
    with wave.open(buffer,'wb') as stream:
        stream.setnchannels(channels);stream.setsampwidth(width);stream.setframerate(rate)
        stream.writeframes(b'\0'*(frames*channels*width))
    return buffer.getvalue()


@contextmanager
def client(mode='available',delay=0,**kwargs):
    with TemporaryDirectory() as folder:
        settings=Settings(alignment_engine='mfa',workspace_root=Path(folder)/'requests',**kwargs)
        app=create_app(settings,FakeAnalyzer(settings,mode,delay))
        with TestClient(app,raise_server_exceptions=False) as transport:
            yield transport,app,settings


def upload(transport,body=None,prompt='learner-v1-001',name='../../unsafe.wav'):
    return transport.post('/api/v1/analyses',data={'prompt_id':prompt},files={'audio':(name,wav() if body is None else body,'audio/wav')})


class ProductModels(unittest.TestCase):
    def test_fixture_validates(self):
        self.assertEqual(SpeechXRayAnalysisResponse.model_validate(fixture()).schema_version,'1.0.0')
    def test_nan_rejected(self):
        row=fixture();row['audio']['duration_ms']=D('NaN')
        with self.assertRaises(ValidationError):SpeechXRayAnalysisResponse.model_validate(row)
    def test_infinity_rejected(self):
        row=fixture();row['targets'][0]['deviation']['mad_distance']=D('Infinity')
        with self.assertRaises(ValidationError):SpeechXRayAnalysisResponse.model_validate(row)
    def test_reverse_span(self):
        with self.assertRaises(ValidationError):TimeSpan(start_ms=5,end_ms=2)
    def test_negative_span(self):
        with self.assertRaises(ValidationError):TimeSpan(start_ms=-1,end_ms=2)
    def test_timeline_overlap(self):
        row=fixture();row['timeline']['phones']*=2
        with self.assertRaises(ValidationError):SpeechXRayAnalysisResponse.model_validate(row)
    def test_abstention_reason_required(self):
        row=fixture();row['status']='ABSTAINED';row['targets'][0]['evidence_status']='ABSTAINED'
        with self.assertRaises(ValidationError):SpeechXRayAnalysisResponse.model_validate(row)
    def test_target_cannot_disappear(self):
        row=fixture();row['targets']=[]
        with self.assertRaises(ValidationError):SpeechXRayAnalysisResponse.model_validate(row)
    def test_numeric_decimal_wire(self):
        row=fixture();row['targets'][0]['deviation']['signed_delta']=D('0.123456789012345678901234567890123456789')
        raw=response_bytes(SpeechXRayAnalysisResponse.model_validate(row))
        self.assertIn(b'0.123456789012345678901234567890123456789',raw)
        self.assertEqual(json.loads(raw,parse_float=D)['targets'][0]['deviation']['signed_delta'],row['targets'][0]['deviation']['signed_delta'])
    def test_null_zero_mad(self):
        row=fixture();row['targets'][0]['deviation'].update(mad_distance=None,warnings=['ZERO_MAD'])
        self.assertIsNone(json.loads(response_bytes(SpeechXRayAnalysisResponse.model_validate(row)))['targets'][0]['deviation']['mad_distance'])
    def test_privacy_projection(self):
        result=InternalAnalysisResult(fixture(),private_debug={'private_path':'PRIVATE_SECRET','speaker_id':'SECRET_SPEAKER','debug_command':'COMMAND_SECRET'})
        raw=response_bytes(project(result)).decode()
        for secret in ('PRIVATE_SECRET','SECRET_SPEAKER','COMMAND_SECRET','private_path','speaker_id','debug_command'):self.assertNotIn(secret,raw)
    def test_unknown_nested_field_rejected(self):
        row=fixture();row['targets'][0]['speaker_id']='secret'
        with self.assertRaises(ValidationError):project(InternalAnalysisResult(row))
    def test_projection_deterministic(self):
        self.assertEqual(response_bytes(project(InternalAnalysisResult(fixture()))),response_bytes(project(InternalAnalysisResult(fixture()))))
    def test_shared_long_span_no_midpoint(self):
        row=fixture();m=row['timeline']['morae']
        self.assertEqual(m[0]['shared_span'],m[1]['shared_span']);self.assertEqual(row['targets'][0]['mora_span'],2)
    def test_numeric_schema_matches_wire(self):
        schema=SpeechXRayAnalysisResponse.model_json_schema(mode='serialization')
        self.assertEqual(schema['$defs']['Audio']['properties']['duration_ms']['type'],'number')


class RegistryTests(unittest.TestCase):
    def setUp(self):
        s=Settings();self.registry=PromptRegistry(s.prompt_registry,s.binding_registry)
    def test_three_authored_ids(self):
        self.assertEqual(list(self.registry.bindings),['learner-v1-001','learner-v1-002','learner-v1-003'])
    def test_public_catalog_no_answer_leak(self):
        raw=self.registry.catalog().model_dump_json()
        for key in ('median','mad','reference_target_id','canonical_pronunciation','duration'):self.assertNotIn(key,raw)
    def test_bindings_actual_pack(self):
        self.assertEqual(self.registry.resolve('learner-v1-001').surface,'スマートフォン')
        self.assertEqual(self.registry.resolve('learner-v1-002').vowel_class,'U')
        self.assertEqual(self.registry.resolve('learner-v1-003').reference_target_id,'jvs-parallel100-voiceactress100_074-w001-m001')
    def test_unknown_prompt(self):
        with self.assertRaises(ProductError):self.registry.resolve('053')
    def test_changed_prompt_refused(self):
        with TemporaryDirectory() as folder:
            s=Settings();row=json.loads(s.prompt_registry.read_text());row['prompts'][0]['text']='変更'
            path=Path(folder)/'pack.json';path.write_text(json.dumps(row),encoding='utf-8')
            with self.assertRaises(ValueError):PromptRegistry(path,s.binding_registry)
    def test_binding_identity_stable(self):
        s=Settings();other=PromptRegistry(s.prompt_registry,s.binding_registry)
        self.assertEqual(self.registry.resolve('learner-v1-001').binding_sha256,other.resolve('learner-v1-001').binding_sha256)
    def test_changed_binding_refused(self):
        with TemporaryDirectory() as folder:
            s=Settings();row=json.loads(s.binding_registry.read_text());row['bindings'][0]['reference_target_id']='changed'
            path=Path(folder)/'bindings.json';path.write_text(json.dumps(row),encoding='utf-8')
            with self.assertRaises(ValueError):PromptRegistry(s.prompt_registry,path)


class APIContractTests(unittest.TestCase):
    def test_live(self):
        with client() as (c,_,s):self.assertEqual(c.get('/api/v1/health/live').json(),{'status':'LIVE','service':'JapaneseSpeechXRay','api_version':'v1'})
    def test_ready_fake(self):
        with client() as (c,_,s):self.assertEqual(c.get('/api/v1/health/ready').json()['status'],'READY')
    def test_public_checkout_not_ready_import_openapi(self):
        with TemporaryDirectory() as folder:
            app=create_app(Settings(workspace_root=Path(folder)))
            self.assertIn('/api/v1/analyses',app.openapi()['paths'])
            with TestClient(app) as c:
                self.assertEqual(c.get('/api/v1/health/ready').status_code,503)
                self.assertEqual(c.get('/api/v1/health/live').status_code,200)
    def test_prompts_and_detail(self):
        with client() as (c,_,s):
            rows=c.get('/api/v1/prompts').json()['prompts'];self.assertEqual(len(rows),3)
            self.assertEqual(c.get('/api/v1/prompts/learner-v1-002').json(),rows[1])
    def test_unknown_detail(self):
        with client() as (c,_,s):
            response=c.get('/api/v1/prompts/unknown');self.assertEqual(response.status_code,404)
            self.assertEqual(response.json()['error_code'],'UNKNOWN_PROMPT')
    def test_unknown_upload_before_worker(self):
        with client() as (c,_,s):self.assertEqual(upload(c,prompt='unknown').status_code,404)
    def test_valid_multipart_and_cleanup(self):
        with client() as (c,app,s):
            response=upload(c);self.assertEqual(response.status_code,200,response.text)
            row=response.json();self.assertEqual(row['analysis_id'],response.headers['x-request-id'])
            self.assertEqual(row['status'],'COMPLETED');self.assertEqual(list(s.workspace_root.iterdir()),[])
            self.assertIn('stage_trace',app.state.service.last_metrics)
    def test_empty_audio(self):
        with client() as (c,_,s):self.assertEqual(upload(c,b'').json()['error_code'],'INVALID_AUDIO')
    def test_malformed_wav(self):
        with client() as (c,_,s):self.assertEqual(upload(c,b'RIFF1234WAVEbad').json()['error_code'],'INVALID_AUDIO')
    def test_wrong_real_format_ignores_suffix(self):
        with client() as (c,_,s):self.assertEqual(upload(c,b'ID3'+b'x'*30,name='valid.wav').json()['error_code'],'UNSUPPORTED_FORMAT')
    def test_stereo_not_mixed(self):
        with client() as (c,_,s):self.assertEqual(upload(c,wav(channels=2)).json()['error_code'],'UNSUPPORTED_FORMAT')
    def test_oversize(self):
        with client(max_upload_bytes=100) as (c,_,s):self.assertEqual(upload(c).status_code,413)
    def test_duration_limit(self):
        with client(max_duration_ms=100) as (c,_,s):self.assertEqual(upload(c).json()['error_code'],'AUDIO_TOO_LONG')
    def test_multipart_envelope_limit(self):
        with client(max_upload_bytes=100) as (c,_,s):self.assertEqual(upload(c,b'x'*(1024*1024+200)).status_code,413)
    def test_missing_audio(self):
        with client() as (c,_,s):self.assertEqual(c.post('/api/v1/analyses',data={'prompt_id':'learner-v1-001'}).status_code,422)
    def test_json_is_not_analysis_contract(self):
        with client() as (c,_,s):self.assertEqual(c.post('/api/v1/analyses',json={'prompt_id':'learner-v1-001','path':'secret'}).status_code,422)
    def test_extra_transcript_or_path_refused(self):
        with client() as (c,_,s):
            for key in ('transcript','local_path'):
                response=c.post('/api/v1/analyses',data={'prompt_id':'learner-v1-001',key:'untrusted'},files={'audio':('a.wav',wav())})
                self.assertEqual(response.status_code,422)
    def test_abstention_http200_retains_target(self):
        with client('abstain') as (c,_,s):
            response=upload(c);self.assertEqual(response.status_code,200,response.text)
            row=response.json();self.assertEqual(row['status'],'ABSTAINED');self.assertEqual(len(row['targets']),1)
            self.assertTrue(row['targets'][0]['reasons']);self.assertEqual(list(s.workspace_root.iterdir()),[])
    def test_missing_f0_keeps_duration(self):
        with client('partial') as (c,_,s):
            row=upload(c).json();self.assertEqual(row['status'],'PARTIAL_EVIDENCE')
            self.assertIsNotNone(row['targets'][0]['duration']);self.assertIsNone(row['targets'][0]['acoustics']['raw_f0_median_hz'])
    def test_operational_error_and_cleanup(self):
        with client('operational') as (c,_,s):
            self.assertEqual(upload(c).status_code,503);self.assertEqual(list(s.workspace_root.iterdir()),[])
    def test_internal_failure_safe_error(self):
        with client('unexpected') as (c,_,s):
            response=upload(c);self.assertEqual(response.status_code,500)
            self.assertNotIn('PRIVATE_PATH',response.text);self.assertNotIn('traceback',response.text)
            self.assertEqual(list(s.workspace_root.iterdir()),[])
    def test_hard_timeout_cleans_worker(self):
        with client(delay=20,timeout_seconds=1) as (c,_,s):
            start=time.monotonic();response=upload(c)
            self.assertEqual(response.json()['error_code'],'ANALYSIS_TIMEOUT',response.text)
            self.assertLess(time.monotonic()-start,6);self.assertEqual(list(s.workspace_root.iterdir()),[])
    def test_capacity_and_workspace_isolation(self):
        with client(delay=2) as (c,_,s):
            results=[];thread=threading.Thread(target=lambda:results.append(upload(c)));thread.start()
            for _ in range(100):
                if any(s.workspace_root.iterdir()):break
                time.sleep(.01)
            busy=upload(c);self.assertEqual(busy.status_code,503,busy.text)
            self.assertEqual(busy.json()['error_code'],'SERVICE_BUSY')
            self.assertEqual(c.get('/api/v1/health/live').status_code,200)
            thread.join(10);self.assertEqual(len(results),1);self.assertEqual(results[0].status_code,200,results[0].text)
            second=upload(c,wav(frames=16001));self.assertEqual(second.status_code,200)
            self.assertNotEqual(results[0].json()['audio']['sha256'],second.json()['audio']['sha256'])
            self.assertNotEqual(results[0].json()['analysis_id'],second.json()['analysis_id'])
            self.assertEqual(list(s.workspace_root.iterdir()),[])
    def test_cors_explicit(self):
        with client() as (c,_,s):
            allowed=c.options('/api/v1/analyses',headers={'Origin':'http://localhost:3000','Access-Control-Request-Method':'POST'})
            denied=c.options('/api/v1/analyses',headers={'Origin':'https://untrusted.example','Access-Control-Request-Method':'POST'})
            self.assertEqual(allowed.headers['access-control-allow-origin'],'http://localhost:3000')
            self.assertNotIn('access-control-allow-origin',denied.headers)
            self.assertNotIn('access-control-allow-credentials',allowed.headers)
    def test_two_allowed_requests_have_independent_workspaces(self):
        with client(delay=1,max_concurrent_analyses=2) as (c,_,s):
            results=[]
            threads=[threading.Thread(target=lambda body=wav(frames=n):results.append(upload(c,body))) for n in (16000,16001)]
            for thread in threads:thread.start()
            for thread in threads:thread.join(10)
            self.assertEqual(len(results),2)
            self.assertTrue(all(r.status_code==200 for r in results),[r.text for r in results])
            self.assertEqual(len({r.json()['audio']['sha256'] for r in results}),2)
            self.assertEqual(list(s.workspace_root.iterdir()),[])
    def test_wildcard_config_refused(self):
        with self.assertRaises(ValidationError):Settings(origins=('*',))
    def test_retention_not_outside_private(self):
        with TemporaryDirectory() as folder:
            with self.assertRaises(ValidationError):Settings(workspace_root=Path(folder),debug_retention=True)
    def test_openapi_typed_contract(self):
        app=create_app();schema=app.openapi();paths=schema['paths']
        self.assertEqual(len([p for p in paths if p.startswith('/api/v1/')]),7)
        self.assertIn('post',paths['/api/prosody/v1/curves'])
        self.assertIn('get',paths['/api/v1/analyses/progress/{control_token}'])
        self.assertIn('post',paths['/api/v1/analyses/cancel/{control_token}'])
        operation=paths['/api/v1/analyses']['post'];self.assertIn('multipart/form-data',operation['requestBody']['content'])
        self.assertEqual(operation['responses']['200']['content']['application/json']['schema']['$ref'],'#/components/schemas/SpeechXRayAnalysisResponse')
        text=json.dumps(schema);self.assertNotIn('speaker_id',text);self.assertNotIn('private_path',text)
    def test_error_taxonomy(self):
        for code,(status,message) in ERRORS.items():
            with self.subTest(code=code):
                value=ProductError(code,'INPUT_VALIDATED',code);self.assertEqual(value.http_status,status)
                self.assertEqual(value.response('request').request_id,'request')


if __name__=='__main__':unittest.main()
