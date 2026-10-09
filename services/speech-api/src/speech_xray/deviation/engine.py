"""Candidate/reference duration comparison with explicit descriptive abstention."""
from dataclasses import asdict
from .duration import FEATURES, FORMULAS, describe_duration
from .models import DeviationResult, EvidenceStatus as S
from .validation import Abstention, candidate_validation, reference_validation, paired_validation
from .provenance import abstention_context


def abstain(status,reason,candidate,reference):
    c,r=abstention_context(candidate,reference)
    return DeviationResult(status,(reason,),c,r)


def compare_duration(candidate, reference):
    try:
        candidate_validation(candidate)
    except Abstention as error:
        return abstain(error.status,str(error),candidate,reference)
    except (OSError,ValueError,TypeError,KeyError,IndexError,AttributeError,ArithmeticError):
        return abstain(S.ABSTAIN_INVALID_CANDIDATE,'CANDIDATE_SOURCE_OR_SCHEMA_INVALID',candidate,reference)
    try:
        reference_validation(reference)
    except Abstention as error:
        return abstain(error.status,str(error),candidate,reference)
    except (OSError,ValueError,TypeError,KeyError,IndexError,AttributeError,ArithmeticError):
        return abstain(S.ABSTAIN_INVALID_REFERENCE,'REFERENCE_SOURCE_OR_SCHEMA_INVALID',candidate,reference)
    try:
        paired_validation(candidate,reference)
    except Abstention as error:
        return abstain(error.status,str(error),candidate,reference)
    profile = reference.profile
    descriptor = profile.to_dict()
    stat = dict(profile.statistics)
    candidate_value = {**candidate.entry.to_dict(), 'target':candidate.manifest.target.to_dict(),
                       'original_span':candidate.original_span.to_dict(), 'rate_context':candidate.rate.to_dict(),
                       **asdict(candidate.duration), 'source_manifest':{'path':candidate.manifest.source,'sha256':candidate.manifest.sha256}}
    reference_value = {'identity':profile.manifest.reference_set_id, 'version':reference.version,
                       'origin_identity':reference.origin_reference_set_id,
                       'profile_artifact':asdict(reference.profile_artifact),
                       'origin_profile_artifact':asdict(reference.origin_profile_artifact),
                       'source_manifest':{'path':profile.manifest.source,'sha256':profile.manifest.sha256},
                       'target_id':profile.manifest.target.target_id, 'target':profile.manifest.target.to_dict(),
                       'mora_span':profile.manifest.target.mora_span, 'n':len(profile.speakers),
                       'speaker_ids':sorted(s.speaker_id for s in profile.speakers),
                       'feature_statistics':{key:stat[key].to_dict() for key in FEATURES},
                       'normalization':descriptor['normalization'],
                       'rate_definition':descriptor['rate_definition'],
                       'statistics_implementation':descriptor['statistics_implementation'],
                       'feature_units':{'raw_duration_ms':'MILLISECONDS',
                           'rate_normalized_duration':'DIMENSIONLESS_MEAN_MORA_PERIODS',
                           'rate_normalized_duration_per_mora':'DIMENSIONLESS_PER_MORA'}}
    try:
        evidence = {'formulas':FORMULAS, 'features':{key:describe_duration(getattr(candidate.duration,key),stat[key]) for key in FEATURES}}
    except (ArithmeticError,ValueError):
        return abstain(S.ABSTAIN_INVALID_CANDIDATE,'DERIVED_EVIDENCE_NOT_REPRESENTABLE',candidate,reference)
    return DeviationResult(S.OK,(),candidate_value,reference_value,evidence)
