"""Typed local configuration; public import/OpenAPI needs no private resources."""
import json
import os
from pathlib import Path
from typing import Literal
from pydantic import Field, model_validator
from .models import Model

ROOT = Path(__file__).resolve().parents[5]


class Resource(Model):
    path: Path
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class ReferenceResource(Model):
    target_id: str
    profile: Resource
    manifest: Resource
    descriptor: Resource
    measurement: Resource | None = None


class NarabasConfiguration(Model):
    python: Path
    repository: Path
    model: Resource
    runtime_lock: Resource
    phone_sequence: Resource
    private_root: Path
    worker_timeout_seconds: float = Field(default=120,gt=0,allow_inf_nan=False)


class Settings(Model):
    alignment_engine: Literal['narabas','mfa'] = 'mfa'
    reference_version: str = 'task009-v2'
    narabas: NarabasConfiguration | None = None
    host: str = '127.0.0.1'
    port: int = Field(default=8000, ge=1, le=65535)
    origins: tuple[str, ...] = ('http://localhost:3000', 'http://127.0.0.1:3000')
    prompt_registry: Path = ROOT / 'data/prompts/learner-pilot-v1.json'
    binding_registry: Path = ROOT / 'data/prompts/product-m1-bindings.json'
    workspace_root: Path = ROOT / 'data/private/product-backend/requests'
    max_upload_bytes: int = Field(default=10*1024*1024, gt=0)
    max_duration_ms: int = Field(default=30000, gt=0)
    timeout_seconds: float = Field(default=900, gt=0, allow_inf_nan=False)
    max_concurrent_analyses: int = Field(default=1, ge=1, le=4)
    debug_retention: bool = False
    policy_version: str = 'm1-resource-policy-1.0.0'
    mfa_version: str = '3.4.2'
    micromamba: Path = ROOT / '.tools/Library/bin/micromamba.exe'
    mfa_environment: Path = ROOT / '.envs/mfa'
    acoustic_model: Resource | None = None
    dictionary: Resource | None = None
    g2p_model: Resource | None = None
    references: tuple[ReferenceResource, ...] = ()
    runtime_resources: tuple[Resource, ...] = ()
    runtime_identity_sha256: str = ''

    @model_validator(mode='after')
    def local_policy(self):
        if self.alignment_engine == 'narabas' and self.max_concurrent_analyses != 1:
            raise ValueError('Narabas heavy concurrency must remain one')
        if '*' in self.origins:
            raise ValueError('CORS origins must be explicit')
        if self.debug_retention and not self.workspace_root.resolve().is_relative_to(ROOT / 'data/private'):
            raise ValueError('Debug retention requires the ignored private root')
        return self


def load_settings():
    location = os.environ.get('SPEECH_XRAY_CONFIG')
    override = os.environ.get('SPEECH_XRAY_ALIGNER')
    if override and override not in {'mfa','narabas'}:
        raise ValueError('Unknown alignment engine')
    if not location:
        if override == 'narabas':
            raise ValueError('NARABAS_ACCEPTED_LOCAL_CONFIGURATION_NOT_AVAILABLE')
        return Settings()
    value = json.loads(Path(location).read_bytes())
    # Historical MFA configurations explicitly identify their three model resources.
    # Reading them retains rollback behavior; new configurations always name the engine.
    if 'alignment_engine' not in value and value.get('dictionary') and value.get('g2p_model'):
        value['alignment_engine'] = 'mfa'
    if override:
        if override != value.get('alignment_engine'):
            raise ValueError('EXPLICIT_CONFIG_ALIGNMENT_ENGINE_MISMATCH')
    return Settings.model_validate(value)
