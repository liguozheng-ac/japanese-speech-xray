"""Immutable authored catalog separated from internal evidence bindings."""
from dataclasses import dataclass
from pathlib import Path
import json
from .models import Prompt, PromptCatalog
from .serialization import identity
from .errors import ProductError


@dataclass(frozen=True)
class Binding:
    prompt: Prompt
    target_id: str
    surface: str
    reading: str
    local_mora_indices: tuple[int, int]
    vowel_class: str
    mapping_basis: str
    reference_target_id: str
    canonical: tuple[str, ...]
    phone_index: int
    silence_fields: tuple[str, ...]
    binding_version: str
    binding_sha256: str
    pack_sha256: str

    def candidate(self):
        return {'target_id': self.target_id, 'target_surface': self.surface, 'target_reading': self.reading,
                'target_mora_span': 2, 'target_vowel_class': self.vowel_class,
                'word_mora_indices': list(self.local_mora_indices), 'mapping_basis': self.mapping_basis,
                'lexical_identity': self.surface}


class PromptRegistry:
    def __init__(self, pack_path, bindings_path):
        from hashlib import sha256
        raw = Path(pack_path).read_bytes()
        pack = json.loads(raw)
        binding_bytes = Path(bindings_path).read_bytes()
        if sha256(binding_bytes).hexdigest() != 'f0b7555db69338ee942dd96817d832ea9f72f55a66ca1dba8ce7a9a3131132a4':
            raise ValueError('M1_BINDING_VERSION_IDENTITY_CHANGED')
        bindings = json.loads(binding_bytes)
        if sha256(raw).hexdigest() != bindings['prompt_pack_sha256']:
            raise ValueError('PROMPT_PACK_IDENTITY_CHANGED')
        self.version = str(pack['prompt_pack_version'])
        self.bindings = {}
        for row in pack['prompts']:
            if len(row['targets']) != 1:
                raise ValueError('M1_REQUIRES_ONE_DECLARED_TARGET')
            target = row['targets'][0]
            selected = [b for b in bindings['bindings'] if b['prompt_id'] == row['prompt_id']]
            if len(selected) != 1 or row['prompt_id'] in self.bindings:
                raise ValueError('PROMPT_BINDING_NOT_UNIQUE')
            b = selected[0]
            if b['target_id'] != target['target_id']:
                raise ValueError('PROMPT_TARGET_IDENTITY_CHANGED')
            prompt = Prompt(prompt_id=row['prompt_id'], display_text=row['text'], prompt_version=self.version)
            self.bindings[row['prompt_id']] = Binding(prompt, target['target_id'], target['surface_hint'],
                target['expected_word_reading'], tuple(target['word_mora_indices']), target['expected_vowel_class'],
                target['expected_candidate_type'], b['reference_target_id'], tuple(b['canonical_pronunciation']),
                b['phone_index'], tuple(b['silence_fields']), bindings['binding_version'],
                identity({'prompt': row, 'binding': b, 'version': bindings['binding_version']}), sha256(raw).hexdigest())
        if len(bindings['bindings']) != len(self.bindings):
            raise ValueError('UNAUTHORED_PRODUCT_BINDING')

    def resolve(self, prompt_id):
        if prompt_id not in self.bindings:
            raise ProductError('UNKNOWN_PROMPT', 'PROMPT_RESOLVED', 'UNKNOWN_PROMPT')
        return self.bindings[prompt_id]

    def catalog(self):
        return PromptCatalog(prompt_pack_version=self.version, prompts=[b.prompt for b in self.bindings.values()])
