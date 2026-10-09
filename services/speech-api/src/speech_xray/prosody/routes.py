"""Local-only descriptive curves, independent of alignment readiness and queue."""
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Annotated
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from speech_xray.product.config import ROOT
from speech_xray.product.errors import ProductError
from .extract import VERSION, extract

REFERENCE_HASHES = {
    'learner-v1-001': 'b66a61fa50369bbec2939265a351a9efa1971770f630b7a81abbba6f746b4a74',
    'learner-v1-002': '21e0ef4f83a94038464b19c10dfc7ab71ad897a483d8db9b5f754030d96d3e56',
    'learner-v1-003': '8b7b852d31cd8053bdb9fa2cd1efe4aeb3d5b6b14355fda7139cf7e72fd047b4',
}


def make_router(settings, registry):
    router = APIRouter(prefix='/api/prosody/v1', tags=['Independent prosody'])
    capacity = Lock()
    reference_cache = {}  # At most three published synthetic readings; no learner cache.

    def compute(raw, prompt_id):
        started = perf_counter()
        prompt = registry.resolve(prompt_id).prompt
        learner = extract(raw, settings)
        reference = None
        source = None
        reference_reason = None
        try:
            reference_dir = Path(os.environ.get('SPEECH_XRAY_REFERENCE_AUDIO_DIR', str(ROOT / 'data/optional-reference-audio')))
            manifest = json.loads((reference_dir / 'manifest.json').read_text(encoding='utf-8-sig'))
            asset = next(a for a in manifest['assets'] if a['prompt_id'] == prompt_id)
            if asset['type'] != 'synthetic' or asset['voice'] != 'Microsoft Haruka Desktop' or asset['text'] != prompt.display_text:
                raise ValueError('REFERENCE_SENTENCE_OR_SOURCE_MISMATCH')
            ref_raw = (reference_dir / f'{prompt_id}.wav').read_bytes()
            digest = sha256(ref_raw).hexdigest()
            if digest != REFERENCE_HASHES[prompt_id] or digest != asset['sha256']:
                raise ValueError('REFERENCE_HASH_MISMATCH')
            if digest not in reference_cache:
                candidate = extract(ref_raw, settings)
                # A transient extraction failure must not poison the cache.
                if candidate['status'] == 'AVAILABLE':
                    reference_cache[digest] = candidate
                reference = candidate
            else:
                reference = reference_cache[digest]
            source = {k: asset[k] for k in ('prompt_id', 'type', 'voice', 'engine', 'text', 'sha256', 'path')}
            source['label'] = '合成参考，非母语者准确性标准'
        except Exception as error:
            reference_reason = 'SYNTHETIC_REFERENCE_UNAVAILABLE'
            logging.getLogger('speech_xray.prosody').warning('reference_abstained reason=%s message=%s', type(error).__name__, str(error))
        return dict(schema_version='prosody-1.0', algorithm=VERSION, prompt_id=prompt_id,
                    learner=learner, reference=reference, reference_source=source,
                    reference_reason=reference_reason, total_ms=(perf_counter()-started)*1000)

    @router.post('/curves', description='Mono PCM16 WAV, 8–48 kHz, up to 30 seconds. In-memory pYIN; no alignment, score or retained learner audio.')
    async def curves(request: Request, audio: Annotated[UploadFile, File()], prompt_id: Annotated[str, Form()]):
        acquired = False
        try:
            fields = await request.form()
            if set(fields) != {'audio', 'prompt_id'} or any(len(fields.getlist(k)) != 1 for k in fields):
                raise ProductError('INVALID_REQUEST', 'INPUT_VALIDATED', 'UNEXPECTED_MULTIPART_FIELDS')
            registry.resolve(prompt_id)
            acquired = capacity.acquire(blocking=False)
            if not acquired:
                return JSONResponse({'reason': 'PROSODY_BUSY', 'message': '音高提取正在处理另一段音频，请稍后重试。'}, status_code=503)
            raw = await audio.read(settings.max_upload_bytes + 1)
            if len(raw) > settings.max_upload_bytes:
                raise ProductError('UPLOAD_TOO_LARGE', 'INPUT_VALIDATED', 'UPLOAD_LIMIT')
            value = await run_in_threadpool(compute, raw, prompt_id)
            return JSONResponse(value)
        finally:
            if acquired:
                capacity.release()
            await audio.close()
    return router
