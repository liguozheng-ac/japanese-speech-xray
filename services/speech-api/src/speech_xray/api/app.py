"""Thin synchronous-analysis HTTP contract; heavy work leaves the event loop."""
from contextlib import asynccontextmanager
import importlib.metadata
import logging
from pathlib import Path
from tempfile import TemporaryFile
from typing import Annotated
from uuid import uuid4, UUID
from fastapi import FastAPI, File, Form, UploadFile, Request, Header
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from speech_xray.product.config import Settings, load_settings
from speech_xray.product.errors import ProductError
from speech_xray.product.models import Live, Ready, ReadinessComponent, Prompt, PromptCatalog, SpeechXRayAnalysisResponse, ErrorResponse
from speech_xray.product.prompts import PromptRegistry
from speech_xray.product.resources import ReferenceStore, NarabasReferenceStore
from speech_xray.product.runtime import MFARuntime
from speech_xray.product.pipeline import ProductPipeline
from speech_xray.product.orchestrator import ProductOrchestrator
from speech_xray.product.serialization import response_bytes, serialize


def json_response(model, status=200):
    return Response(serialize(model.model_dump(mode='python')), status_code=status, media_type='application/json')


class BodyLimit:
    """Bound the multipart envelope before the framework's spool/parser allocates it."""
    def __init__(self, app, limit): self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') != 'POST':
            return await self.app(scope, receive, send)
        total = 0
        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get('body', b''))
            if total > self.limit:
                scope.setdefault('state', {})['body_too_large'] = True
                raise ProductError('UPLOAD_TOO_LARGE', 'INPUT_VALIDATED', 'MULTIPART_ENVELOPE_LIMIT')
            return message
        await self.app(scope, bounded_receive, send)


def create_app(settings=None, analyzer=None, registry=None):
    settings = settings or load_settings()
    registry = registry or PromptRegistry(settings.prompt_registry, settings.binding_registry)
    components = []
    service = None

    @asynccontextmanager
    async def lifespan(app):
        nonlocal service
        components.clear()
        components.append(ReadinessComponent(component='prompt_registry', ready=True, reason_code='LOADED'))
        current = analyzer
        owned_runtime = None
        if current is None:
            references, runtime = None, None
            try:
                references = NarabasReferenceStore(settings) if settings.alignment_engine == 'narabas' else ReferenceStore(settings)
                expected = {b.reference_target_id for b in registry.bindings.values()}
                if not expected <= references.loaded.keys(): raise ValueError('REFERENCE_NOT_CONFIGURED')
                components.append(ReadinessComponent(component='reference_profiles', ready=True, reason_code='HASH_PINNED'))
            except (OSError, ValueError, KeyError) as error:
                reason = ('REFERENCE_DISTRIBUTION_REVIEW_REQUIRED'
                          if str(error) == 'REFERENCE_DISTRIBUTION_REVIEW_REQUIRED'
                          else 'REFERENCE_UNAVAILABLE')
                components.append(ReadinessComponent(component='reference_profiles', ready=False, reason_code=reason))
            try:
                if settings.alignment_engine == 'narabas':
                    from speech_xray.product.narabas_runtime import NarabasRuntime, NarabasSpec
                    from speech_xray.product.resources import verify
                    n = settings.narabas
                    if n is None: raise ValueError('NARABAS_NOT_CONFIGURED')
                    for resource in (n.model,n.runtime_lock,n.phone_sequence): verify(resource)
                    runtime = NarabasRuntime(NarabasSpec(n.python,n.repository,n.model.path,n.runtime_lock.path,
                                           n.runtime_lock.sha256,n.private_root,n.worker_timeout_seconds))
                    owned_runtime = runtime
                else:
                    runtime = MFARuntime(settings)
                components.append(ReadinessComponent(component='alignment_runtime', ready=True,
                    reason_code='PINNED_NARABAS_LAZY_CPU' if settings.alignment_engine == 'narabas' else 'PINNED_MFA'))
            except (OSError, ValueError, KeyError):
                components.append(ReadinessComponent(component='alignment_runtime', ready=False, reason_code='RUNTIME_UNAVAILABLE'))
            if references is not None and runtime is not None:
                if settings.alignment_engine == 'narabas':
                    from speech_xray.product.narabas_pipeline import NarabasPipeline
                    current = NarabasPipeline(settings,references,runtime)
                else:
                    current = ProductPipeline(settings, references, runtime)
        else:
            components.append(ReadinessComponent(component='injected_analyzer', ready=True, reason_code='TEST_OR_LOCAL_INJECTION'))
        try:
            expected = {'librosa':'1.0.0','numpy':'2.5.3','soundfile':'0.14.0','scipy':'1.18.1',
                        'sudachipy':'0.6.11','sudachidict-core':'20260116'}
            if any(importlib.metadata.version(k) != v for k,v in expected.items()): raise ValueError('RUNTIME_CHANGED')
            components.append(ReadinessComponent(component='acoustics_runtime', ready=True, reason_code='ACCEPTED_VERSIONS'))
        except (ValueError, importlib.metadata.PackageNotFoundError):
            components.append(ReadinessComponent(component='acoustics_runtime', ready=False, reason_code='RUNTIME_UNAVAILABLE'))
        try:
            settings.workspace_root.mkdir(parents=True, exist_ok=True)
            with TemporaryFile(dir=settings.workspace_root): pass
            components.append(ReadinessComponent(component='temporary_workspace', ready=True, reason_code='WRITABLE'))
        except OSError:
            components.append(ReadinessComponent(component='temporary_workspace', ready=False, reason_code='WORKSPACE_UNAVAILABLE'))
        components.append(ReadinessComponent(component='analysis_policy', ready=True, reason_code=settings.policy_version))
        if current is not None: service = ProductOrchestrator(settings, registry, current)
        app.state.service = service
        try:
            yield
        finally:
            if owned_runtime is not None:
                await run_in_threadpool(owned_runtime.close)

    app = FastAPI(title='Japanese Speech X-Ray M1', version='1.0.0', lifespan=lifespan)
    from speech_xray.prosody.routes import make_router
    app.include_router(make_router(settings, registry))
    app.add_middleware(BodyLimit, limit=settings.max_upload_bytes+1024*1024)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.origins), allow_credentials=False,
                       allow_methods=['GET','POST'], allow_headers=['Content-Type','X-Analysis-Token'], expose_headers=['X-Request-ID'])

    @app.middleware('http')
    async def correlation(request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers['X-Request-ID'] = request.state.request_id
        return response

    @app.exception_handler(ProductError)
    async def product_error(request, error):
        return json_response(error.response(request.state.request_id), error.http_status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return await product_error(request, ProductError('INVALID_REQUEST','INPUT_VALIDATED','MULTIPART_FIELDS_REQUIRED'))

    @app.exception_handler(HTTPException)
    async def parser_error(request, error):
        code = 'UPLOAD_TOO_LARGE' if error.status_code == 413 or getattr(request.state,'body_too_large',False) else 'INVALID_REQUEST'
        return json_response(ProductError(code,'INPUT_VALIDATED','MULTIPART_PARSE_FAILED').response(request.state.request_id),
                             413 if code=='UPLOAD_TOO_LARGE' else error.status_code)

    @app.exception_handler(Exception)
    async def unexpected(request, error):
        logging.getLogger('speech_xray.product').exception('http_failed request_id=%s',request.state.request_id)
        return json_response(ProductError('INTERNAL_PIPELINE_ERROR','HTTP','UNEXPECTED_FAILURE').response(request.state.request_id),500)

    errors={code:{'model':ErrorResponse} for code in (404,409,413,422,500,503)}

    @app.post('/api/v1/analyses/cancel/{control_token}', description='Cancel only the analysis identified by its private client-generated UUID token. CANCELLED means cleanup has completed.')
    async def cancel_analysis(control_token: UUID):
        if service is None:
            return {'status': 'NOT_FOUND'}
        status = await run_in_threadpool(service.cancel, str(control_token))
        return {'status': status}

    @app.get('/api/v1/health/live', response_model=Live)
    def live(): return Live()

    @app.get('/api/v1/analyses/progress/{control_token}', description='Runtime stage only, not elapsed-time percentage or ETA. Uses the same X-Analysis-Token as analysis/cancel.')
    def analysis_progress(control_token: UUID):
        return service.progress(str(control_token)) if service is not None else {'state': 'NOT_FOUND'}

    @app.get('/api/v1/health/ready', response_model=Ready, responses={503:{'model':Ready}})
    def ready():
        value=Ready(status='READY' if components and all(c.ready for c in components) else 'NOT_READY',components=components)
        return json_response(value,200 if value.status=='READY' else 503)

    @app.get('/api/v1/prompts', response_model=PromptCatalog)
    def prompts(): return registry.catalog()

    @app.get('/api/v1/prompts/{prompt_id}', response_model=Prompt, responses={404:{'model':ErrorResponse}})
    def prompt_detail(prompt_id:str): return registry.resolve(prompt_id).prompt

    @app.post('/api/v1/analyses', response_model=SpeechXRayAnalysisResponse, responses=errors,
              description='Synchronous evidence analysis. Mono PCM16 RIFF WAV only, 8–48 kHz; default engineering limits 10 MiB and 30 seconds. Uploads are ephemeral. Linguistic abstention returns HTTP 200.')
    async def analyses(request:Request, audio:Annotated[UploadFile,File()], prompt_id:Annotated[str,Form()],
                       x_analysis_token:Annotated[str | None,Header()] = None):
        fields = await request.form()
        if set(fields) != {'audio','prompt_id'} or any(len(fields.getlist(k)) != 1 for k in fields):
            raise ProductError('INVALID_REQUEST','INPUT_VALIDATED','UNEXPECTED_MULTIPART_FIELDS')
        registry.resolve(prompt_id)
        if x_analysis_token is not None:
            try:
                parsed_token = UUID(x_analysis_token)
                if parsed_token.version != 4 or str(parsed_token) != x_analysis_token:
                    raise ValueError('NON_CANONICAL_TOKEN')
            except ValueError:
                raise ProductError('INVALID_REQUEST','INPUT_VALIDATED','INVALID_CONTROL_TOKEN')
        if service is None or not all(c.ready for c in components):
            code='REFERENCE_ARTIFACT_MISSING' if any(c.component=='reference_profiles' and not c.ready for c in components) else 'ALIGNMENT_RUNTIME_UNAVAILABLE'
            raise ProductError(code,'INPUT_VALIDATED','SERVICE_NOT_READY')
        # Context owns capacity and cleanup on success, abstention and every exception.
        try:
            with service.session(prompt_id,request.state.request_id,x_analysis_token) as analysis_request:
                size=0
                with analysis_request.audio_path.open('xb') as output:
                    while chunk := await audio.read(65536):
                        service.check_cancelled(analysis_request)
                        size+=len(chunk)
                        if size>settings.max_upload_bytes: raise ProductError('UPLOAD_TOO_LARGE','INPUT_VALIDATED','UPLOAD_LIMIT')
                        output.write(chunk)
                result=await run_in_threadpool(service.analyse,analysis_request)
                return Response(response_bytes(result),media_type='application/json')
        finally:
            await audio.close()
    return app


app = create_app()
