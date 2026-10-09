"""Load hash-pinned accepted statistics; never build or modify a population."""
from hashlib import sha256
from pathlib import Path
from speech_xray.reference.json_input import read_json
from speech_xray.reference.models import RobustStatistics
from speech_xray.evaluation.matching import match_target
from .errors import ProductError


def verify(resource):
    if not resource.path.is_file() or sha256(resource.path.read_bytes()).hexdigest() != resource.sha256:
        raise ValueError('PINNED_RESOURCE_UNAVAILABLE')


class ReferenceStore:
    def __init__(self, settings):
        from .measurement_registry import require_pair
        require_pair('MFA_CPU_CLI',settings.reference_version,'product-m1-1.0.0')
        self._load(settings)

    def _load(self, settings):
        self.resources = {r.target_id: r for r in settings.references}
        self.loaded = {}
        for resource in settings.references:
            for item in (resource.profile, resource.manifest, resource.descriptor):
                verify(item)
            profile, _ = read_json(resource.profile.path)
            manifest, _ = read_json(resource.manifest.path)
            descriptor, _ = read_json(resource.descriptor.path)
            if (profile['target_id'] != resource.target_id or profile['target'] != manifest['target']
                or profile['speaker_count'] != 100 or profile['independence_unit'] != 'SPEAKER'
                or profile['profile_status'] != 'READY_FOR_EXPERIMENT'
                or profile['normalization']['formula_version'] != '0.1'
                or profile['source_provenance']['manifest']['sha256'] != resource.manifest.sha256
                or descriptor['profile_artifact']['sha256'] != resource.profile.sha256):
                raise ValueError('ACCEPTED_REFERENCE_IDENTITY_CHANGED')
            self.loaded[resource.target_id] = (profile, descriptor)

    def resolve(self, binding):
        resource = self.resources.get(binding.reference_target_id)
        if resource is None:
            raise ProductError('REFERENCE_ARTIFACT_MISSING', 'REFERENCE_RESOLVED', 'REFERENCE_UNAVAILABLE')
        try:
            for item in (resource.profile, resource.manifest, resource.descriptor):
                verify(item)
        except (OSError, ValueError) as error:
            raise ProductError('REFERENCE_ARTIFACT_MISSING', 'REFERENCE_RESOLVED', 'REFERENCE_UNAVAILABLE') from error
        profile, descriptor = self.loaded[binding.reference_target_id]
        if match_target(binding.candidate(), [descriptor])['status'] != 'COMPATIBLE_LINGUISTIC_TARGET':
            return None
        return profile, resource

    @staticmethod
    def statistics(profile):
        return RobustStatistics(**{k: (int(v) if k == 'count' else v)
            for k, v in profile['feature_statistics']['rate_normalized_duration'].items()})


class NarabasReferenceStore(ReferenceStore):
    def __init__(self, settings):
        from .measurement_registry import require_pair
        self.measurement = require_pair('NARABAS_CPU_WORKER',settings.reference_version,'product-m1-1.1.0')
        if self.measurement['population_review'] != 'ACCEPTED':
            raise ValueError('REFERENCE_DISTRIBUTION_REVIEW_REQUIRED')
        self._load(settings)
        expected = self.measurement['alignment_provenance']
        for resource in settings.references:
            if resource.measurement is None:
                raise ValueError('NATIVE_REFERENCE_MEASUREMENT_REQUIRED')
            verify(resource.measurement)
            method,_ = read_json(resource.measurement.path)
            if (method['alignment_engine'] != 'NARABAS_CPU_WORKER' or
                    any(method[k] != v for k,v in expected.items()) or
                    self.measurement['profile_sha256_by_target'].get(resource.target_id) != resource.profile.sha256):
                raise ValueError('CROSS_ALIGNER_REFERENCE_COMPARISON_FORBIDDEN')
            profile,descriptor = self.loaded[resource.target_id]
            if descriptor['reference_version'] != settings.reference_version or profile['rejected_take_count'] != 0:
                raise ValueError('NATIVE_REFERENCE_INTEGRITY_FAILED')
            for source in descriptor['linguistic_sources']:
                path = Path(source['path'])
                if sha256(path.read_bytes()).hexdigest() != source['sha256']:
                    raise ValueError('NATIVE_REFERENCE_LINGUISTIC_SOURCE_CHANGED')
                mapped,_ = read_json(path)
                if mapped['phone_adapter'] != 'NARABAS_JA_1_0_0':
                    raise ValueError('CROSS_ALIGNER_REFERENCE_COMPARISON_FORBIDDEN')

    def resolve(self, binding):
        resource = self.resources.get(binding.reference_target_id)
        if resource is not None:
            verify(resource.measurement)
        return super().resolve(binding)
