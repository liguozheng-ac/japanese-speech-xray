"""Retain available abstention identities without serializing invalid measurements."""
import re
from dataclasses import asdict
from speech_xray.reference.models import ReferenceEntry,ReferenceManifest,ReferenceProfile,ArtifactReference
from .models import CandidateObservation,ReferenceObservation


def _text(value):
    return value if isinstance(value,str) else None


def _artifact(value):
    if not isinstance(value,ArtifactReference):
        return None
    sha=_text(value.sha256)
    return {'path':_text(value.path),'sha256':sha if sha and re.fullmatch('[0-9a-f]{64}',sha) else None}


def abstention_context(candidate,reference):
    c=r=None
    if isinstance(candidate,CandidateObservation) and isinstance(candidate.manifest,ReferenceManifest):
        m=candidate.manifest
        c={'source_manifest':{'path':_text(m.source),'sha256':_text(m.sha256)},
           'target_id':_text(getattr(m.target,'target_id',None)),
           'mora_span':m.target.mora_span if type(getattr(m.target,'mora_span',None)) is int else None,
           'provenance_state':'UNVERIFIED_ABSTENTION_CONTEXT'}
        if isinstance(candidate.entry,ReferenceEntry):
            e=candidate.entry
            for key in ('prompt_id','speaker_id','take_id','utterance_id','span_id'):
                c[key]=_text(getattr(e,key,None))
            if isinstance(e.sources,tuple):
                c['sources']={key:_artifact(ref) for item in e.sources
                              if isinstance(item,tuple) and len(item)==2
                              for key,ref in [item] if isinstance(key,str)}
    if isinstance(reference,ReferenceObservation) and isinstance(reference.profile,ReferenceProfile):
        p=reference.profile
        if isinstance(p.manifest,ReferenceManifest):
            r={'identity':_text(p.manifest.reference_set_id),'version':_text(reference.version),
               'origin_identity':_text(reference.origin_reference_set_id),
               'target_id':_text(getattr(p.manifest.target,'target_id',None)),
               'mora_span':p.manifest.target.mora_span if type(getattr(p.manifest.target,'mora_span',None)) is int else None,
               'n':len(p.speakers) if isinstance(p.speakers,(tuple,list)) else None,
               'profile_artifact':_artifact(reference.profile_artifact),
               'origin_profile_artifact':_artifact(reference.origin_profile_artifact),
               'provenance_state':'UNVERIFIED_ABSTENTION_CONTEXT'}
    return c,r
