"""Explicit mathematical duration fixtures; no native or learner recordings."""
from pathlib import Path
import tempfile
from dataclasses import replace

from reference_test_support import ROOT, make_manifest, read, write_json
from speech_xray.reference.manifest import load_manifest
from speech_xray.reference.profile_builder import build_reference_profile
from speech_xray.deviation.inputs import candidate_from_bundle
from speech_xray.deviation.models import ReferenceObservation
from speech_xray.deviation.serialization import save_canonical


def workspace(test):
    root=ROOT/'data/private/deviation-tests';root.mkdir(parents=True,exist_ok=True)
    temp=tempfile.TemporaryDirectory(dir=root);test.addCleanup(temp.cleanup)
    return Path(temp.name)


def reference(directory, raw=None, count=5):
    directory.mkdir(parents=True,exist_ok=True)
    raws=raw if raw is not None else [100+i*20 for i in range(count)]
    path=make_manifest(directory,[(f'AUTHORED-REF-{i:03}','take',str(raws[i]),'2000') for i in range(count)])
    profile=build_reference_profile(load_manifest(path))
    artifact=save_canonical(directory/'profile.json',profile.to_dict())
    return ReferenceObservation(profile,artifact,'AUTHORED_REFERENCE_V1',profile.manifest.reference_set_id,artifact)


def candidate(directory, raw='140', core='2000', speaker='AUTHORED-CANDIDATE'):
    directory.mkdir(parents=True,exist_ok=True)
    path=make_manifest(directory,[(speaker,'take',raw,core)])
    manifest=load_manifest(path)
    return candidate_from_bundle(manifest,manifest.entries[0])


def rewritten_reference(ref,profile,directory):
    artifact=save_canonical(directory/'altered-profile.json',profile.to_dict())
    return replace(ref,profile=profile,profile_artifact=artifact)
