"""Scoped read-only validation cache feeding the unchanged reference builder code."""
from dataclasses import replace
from pathlib import Path
from types import FunctionType

from speech_xray.corpus.batch_plan import digest
from speech_xray.reference import profile_builder
from speech_xray.reference.integrity import validate_entry
from speech_xray.reference.manifest import load_manifest
from speech_xray.reference.models import ReferencePolicy
from .models import CandidateObservation, ReferenceObservation
from .serialization import save_canonical


class VerifiedReferenceSnapshot:
    """Validate each source once; cache context, metadata and verified parsed input.

    The reference builder's exact code object and mathematical dependencies are
    reused with a private globals dictionary. Only its artifact-reader binding
    is memoized. The imported reference module and its files are never patched.
    Hash verification brackets the experiment; cached reads also check metadata.
    """
    def __init__(self, manifest_path, profile_artifact, version):
        self.manifest = load_manifest(manifest_path)
        self.artifact = profile_artifact
        self.version = version
        self._inputs = {}
        self._hashes = {self.manifest.source:self.manifest.sha256,
                        profile_artifact.path:profile_artifact.sha256}
        for entry in self.manifest.entries:
            for _, ref in entry.sources:
                if ref.path in self._hashes and self._hashes[ref.path] != ref.sha256:
                    raise ValueError('SNAPSHOT_CONFLICTING_ARTIFACT_IDENTITY')
                self._hashes[ref.path] = ref.sha256
        self._metadata = {path:self._fingerprint(path) for path in self._hashes}
        self.verify_hashes()
        original = profile_builder.build_reference_profile
        namespace = dict(original.__globals__)
        namespace['validate_entry'] = self._validated_entry
        self.builder = FunctionType(original.__code__, namespace, original.__name__, original.__defaults__, original.__closure__)
        self.profile = self.builder(self.manifest)
        if self.profile.rejected or self.profile.profile_status != 'READY_FOR_EXPERIMENT':
            raise ValueError('SNAPSHOT_SOURCE_REFERENCE_NOT_READY')
        if Path(profile_artifact.path).read_text(encoding='utf-8') != self.profile.to_json():
            raise ValueError('SNAPSHOT_SOURCE_PROFILE_RECONSTRUCTION_MISMATCH')
        self.verify_hashes()

    @staticmethod
    def _fingerprint(path):
        stat = Path(path).stat()
        return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns

    def _unchanged(self, paths):
        if any(self._fingerprint(path) != self._metadata[path] for path in paths):
            raise ValueError('SNAPSHOT_ARTIFACT_CHANGED')

    def verify_hashes(self):
        self._unchanged(self._hashes)
        if any(digest(path) != sha for path,sha in self._hashes.items()):
            raise ValueError('SNAPSHOT_ARTIFACT_HASH_CHANGED')

    def _validated_entry(self, manifest, entry):
        base = self.manifest
        if ((manifest.prompt_id,manifest.target,manifest.transcript_sha256,manifest.dataset)
                != (base.prompt_id,base.target,base.transcript_sha256,base.dataset)
                or entry not in base.entries
                or not (manifest.reference_set_id == base.reference_set_id
                        or manifest.reference_set_id.startswith(base.reference_set_id+'/loo/'))):
            raise ValueError('SNAPSHOT_VALIDATION_CONTEXT_MISMATCH')
        self._unchanged([base.source,self.artifact.path]+[ref.path for _,ref in entry.sources])
        if entry not in self._inputs:
            self._inputs[entry] = validate_entry(manifest,entry)
        return self._inputs[entry]

    def build_excluding(self, speaker_id, output):
        ids = {s.speaker_id for s in self.profile.speakers}
        if speaker_id not in ids:
            raise ValueError('LOO_CANDIDATE_SPEAKER_MISSING')
        entries = tuple(e for e in self.manifest.entries if e.speaker_id != speaker_id)
        fragment = {'schema_version':'0.1', 'reference_set_id':self.manifest.reference_set_id+'/loo/'+speaker_id,
                    'prompt_id':self.manifest.prompt_id,'transcript_sha256':self.manifest.transcript_sha256,
                    'target':self.manifest.target.to_dict(), 'dataset':dict(self.manifest.dataset),
                    'creation_metadata':{'label':'TASK-010 native-reference self-consistency LOO'},
                    'entries':[entry.to_dict() for entry in entries]}
        manifest_ref = save_canonical(Path(output)/'reference-manifest.json',fragment)
        manifest = load_manifest(manifest_ref.path)
        profile = self.builder(manifest,self.profile.policy)
        self.assert_exclusion(speaker_id,profile)
        if profile.rejected or len(profile.speakers) != len(ids)-1:
            raise ValueError('LOO_REFERENCE_RECONSTRUCTION_FAILED')
        artifact = save_canonical(Path(output)/'reference-profile.json',profile.to_dict())
        return ReferenceObservation(profile,artifact,self.version,self.manifest.reference_set_id,self.artifact)

    @staticmethod
    def assert_exclusion(speaker_id,profile):
        if (speaker_id in {s.speaker_id for s in profile.speakers}
                or any(e.speaker_id == speaker_id for e in profile.manifest.entries)):
            raise ValueError('LOO_CANDIDATE_INCLUDED_IN_REFERENCE')

    def candidate(self, speaker_id):
        speaker = next(s for s in self.profile.speakers if s.speaker_id == speaker_id)
        if len(speaker.takes) != 1:
            raise ValueError('LOO_EXPERIMENT_REQUIRES_ONE_CANDIDATE_TAKE')
        take = speaker.takes[0]
        return CandidateObservation(self.manifest,take.entry,take.original_span,take.rate,take.duration)
