"""Runtime mathematical WAVs and authored timing: always TEST_FIXTURE, never humans."""

from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"services/speech-api/src"))
from speech_xray.corpus.batch_plan import digest,pipeline_configuration
from speech_xray.corpus.intake import load_corpus_manifest,validate_corpus
from speech_xray.corpus.prompt_manifest import load_prompt_pack,authoring_words
from speech_xray.corpus.speaker_manifest import speaker_from_json,session_from_json
from speech_xray.corpus.models import SourceType
from speech_xray.acoustics.models import evidence_json
from speech_xray.japanese.reading import SudachiReadingProvider

PACK_PATH=ROOT/"data/prompts/reference-long-vowel-v1.json"


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(evidence_json(value),encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def workspace(test):
    parent=ROOT/"data/private/task006-tests"
    parent.mkdir(parents=True,exist_ok=True)
    temporary=tempfile.TemporaryDirectory(dir=parent)
    test.addCleanup(temporary.cleanup)
    return Path(temporary.name)


def speaker_value(speaker="fixture-001",source=SourceType.TEST_FIXTURE):
    return {"schema_version":"0.1","speaker_id":speaker,"source_type":source,
            "self_reported_native_japanese":None,"native_status_metadata_status":"TEST_ASSERTION"}


def session_value(pack,speaker="fixture-001"):
    return {"schema_version":"0.1","session_id":speaker+"-session-01","speaker_id":speaker,
            "prompt_pack_id":pack.prompt_pack_id,"prompt_pack_version":pack.prompt_pack_version,
            "prompt_pack_sha256":pack.sha256,"consent_record_id":None,"consent_metadata_status":"TEST_ASSERTION",
            "permission_local_analysis":None,"permission_derived_numeric_features":None,
            "recording_date_label":"TEST_NOT_PARTICIPANT_DATE","recording_environment_label":"MATH_SIGNAL_TEST"}


def corpus(directory,count=1):
    pack=load_prompt_pack(PACK_PATH)
    value={"schema_version":"0.1","corpus_id":"mathematical-test-corpus","corpus_root":".",
           "prompt_pack":{"prompt_pack_id":pack.prompt_pack_id,"prompt_pack_version":pack.prompt_pack_version,"manifest_sha256":pack.sha256},
           "speaker_manifests":[],"session_manifests":[],"recordings":[],"external_reference_sets":[],"creation_label":"TEST_FIXTURE_NOT_HUMAN_COLLECTION"}
    for index in range(count):
        speaker=f"fixture-{index+1:03}"
        prompt=pack.prompts[index%len(pack.prompts)]
        name=f"{speaker}__{prompt.prompt_id}__take-01.wav"
        path=directory/"audio"/name
        path.parent.mkdir(parents=True,exist_ok=True)
        samples=.2*np.sin(2*np.pi*(220+index)*np.arange(32000)/16000)
        sf.write(path,samples,16000,subtype="PCM_16")
        for kind,payload in (("speaker",speaker_value(speaker)),("session",session_value(pack,speaker))):
            metadata=directory/"manifests"/(speaker+"-"+kind+".json")
            write(metadata,payload)
            value[kind+"_manifests"].append({"path":str(metadata),"sha256":digest(metadata)})
        value["recordings"].append({"speaker_id":speaker,"session_id":speaker+"-session-01","prompt_id":prompt.prompt_id,
                                   "take_id":"take-01","source_type":"TEST_FIXTURE","audio":{"path":str(path),"sha256":digest(path)},"evidence_receipt":None})
    manifest=directory/"corpus.json"
    write(manifest,value)
    return manifest,load_corpus_manifest(manifest),pack


def authored_aligner(pack,fail_key=None):
    """Vowel-only structured TextGrid, not an MFA result or native acoustic gold."""
    def align(paths,recording):
        if recording.key==fail_key:
            raise RuntimeError("SELF_AUTHORED_FAILURE_ISOLATION_TEST")
        prompt=next(p for p in pack.prompts if p.prompt_id==recording.prompt_id)
        words=[]; phones=[]; cursor=Decimal("0.1")
        for surface,reading,morae,candidates in authoring_words(prompt,SudachiReadingProvider()):
            start=cursor
            candidates={c.mora_indices[0]:c for c in candidates}
            index=0
            while index<len(morae):
                mora=morae[index]
                width=2 if index in candidates else 1
                end=cursor+Decimal("0.03")*width
                vowel=candidates[index].vowel_class if width==2 else mora.vowel_class
                label={"A":"a","I":"i","U":"ɨ","E":"e","O":"o"}.get(vowel,"ɴ")+("ː" if width==2 else "")
                phones.append((cursor,end,label));cursor=end;index+=width
            words.append((start,cursor,surface))
        words=[(Decimal(0),Decimal("0.1"),""),*words,(cursor,Decimal(2),"")]
        phones=[(Decimal(0),Decimal("0.1"),""),*phones,(cursor,Decimal(2),"")]
        rows=['File type = "ooTextFile short"','"TextGrid"','0','2','<exists>','2']
        for name,items in (("words",words),("phones",phones)):
            rows += ['"IntervalTier"',f'"{name}"','0','2',str(len(items))]
            for left,right,label in items:
                rows += [str(left),str(right),'"'+label.replace('"','""')+'"']
        target=Path(paths["textgrid"])
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text("\n".join(rows)+"\n",encoding="utf-8")
    return align
