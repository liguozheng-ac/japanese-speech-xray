from dataclasses import dataclass
from enum import StrEnum


class SourceType(StrEnum):
    CONTROLLED_LEARNER_RECORDING = 'CONTROLLED_LEARNER_RECORDING'
    EXTERNAL_LEARNER_CORPUS = 'EXTERNAL_LEARNER_CORPUS'


class HumanCategory(StrEnum):
    LONG_VOWEL_REALIZED = 'LONG_VOWEL_REALIZED'
    LONG_VOWEL_REDUCED_OR_ABSENT = 'LONG_VOWEL_REDUCED_OR_ABSENT'
    UNCERTAIN = 'UNCERTAIN'
    UNUSABLE_AUDIO = 'UNUSABLE_AUDIO'
    TARGET_NOT_REALIZED = 'TARGET_NOT_REALIZED'


class WorkflowState(StrEnum):
    UNANNOTATED = 'UNANNOTATED'
    ANNOTATED_BLIND = 'ANNOTATED_BLIND'
    MODEL_EVIDENCE_ATTACHED = 'MODEL_EVIDENCE_ATTACHED'
    ADJUDICATED = 'ADJUDICATED'


class Split(StrEnum):
    DEVELOPMENT = 'development'
    CALIBRATION = 'calibration'
    HELD_OUT_TEST = 'held_out_test'


@dataclass(frozen=True)
class LearnerDataset:
    source: str
    sha256: str
    canonical_document: str

    @property
    def data(self):
        from .serialization import decode
        return decode(self.canonical_document)

    @property
    def identity(self):
        d = self.data
        return {'dataset_id':d['dataset_id'], 'dataset_version':d['dataset_version'],
                'source_type':d['source_type'], 'source_manifest_sha256':self.sha256}


@dataclass(frozen=True)
class EvaluationRun:
    run_id: str
    dataset_roles: tuple[tuple[str, str], ...]
    learner_speakers: tuple[str, ...]
    reference_speakers: tuple[str, ...]
    assignments: tuple[tuple[str, str], ...]
    dataset_hashes: tuple[str, ...]

    def to_dict(self):
        return {'schema_version':'0.1','evaluation_run_id':self.run_id,
                'dataset_roles':[{'dataset_id':d,'role':r} for d,r in self.dataset_roles],
                'learner_speakers':list(self.learner_speakers),'reference_speakers':list(self.reference_speakers),
                'dataset_hashes':list(self.dataset_hashes),
                'assignments':[{'speaker_id':s,'split':p} for s,p in self.assignments],
                'selection_allowed_in_task011':False,'held_out_test_selection_forbidden':True}


@dataclass(frozen=True)
class AnnotationSession:
    evaluation_run_id: str
    observation_id: str
    dataset_identity_json: str
    blind_package_sha256: str
    state: WorkflowState = WorkflowState.UNANNOTATED
    primary_annotations: tuple[str, ...] = ()
    model_evidence_json: str | None = None
    adjudication_json: str | None = None

    def to_dict(self):
        from .serialization import decode
        annotations = [decode(a) for a in self.primary_annotations]
        return {'schema_version':'0.1', 'evaluation_run_id':self.evaluation_run_id,
                'observation_id':self.observation_id, 'dataset_identity':decode(self.dataset_identity_json),
                'blind_package_sha256':self.blind_package_sha256, 'state':self.state,
                'human_annotation':annotations,
                'disagreement':len({a['category'] for a in annotations}) > 1,
                'model_evidence':decode(self.model_evidence_json) if self.model_evidence_json else None,
                'adjudication':decode(self.adjudication_json) if self.adjudication_json else None}
