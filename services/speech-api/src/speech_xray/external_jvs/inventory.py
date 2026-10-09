"""Observe stable IDs, transcript agreement and actual WAV availability."""

from collections import Counter,defaultdict
from pathlib import Path
import re
import soundfile as sf

from speech_xray.corpus.batch_plan import digest
from speech_xray.corpus.models import SourceType
from speech_xray.corpus.validation import PRIVATE_ROOT

SPEAKERS=tuple(f"jvs{i:03}" for i in range(1,101))
PROMPTS=tuple(f"VOICEACTRESS100_{i:03}" for i in range(1,101))


def speaker_id(value):
    if value not in SPEAKERS:raise ValueError("INVALID_JVS_SPEAKER_ID")
    return value


def prompt_id(value):
    if value not in PROMPTS:raise ValueError("INVALID_PARALLEL100_PROMPT_ID")
    return value


def private_root(path):
    path=Path(path).resolve()
    if not path.is_relative_to(PRIVATE_ROOT.resolve()):raise ValueError("EXTERNAL_CORPUS_MUST_REMAIN_PRIVATE")
    if not path.is_dir():raise ValueError("EXTERNAL_CORPUS_ROOT_MISSING")
    return path


def contained(path,root):
    path=Path(path).resolve()
    if not path.is_relative_to(root):raise ValueError("EXTERNAL_CORPUS_PATH_ESCAPE")
    return path


def transcripts(path,root):
    path=contained(path,root)
    values={};failures=[]
    for number,line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(),1):
        if not line.strip():continue
        identity,separator,text=line.partition(":")
        if not separator or identity not in PROMPTS or not text.strip():
            failures.append({"line":number,"reason":"UNSUPPORTED_TRANSCRIPT_LINE_OR_ID"});continue
        if identity in values:
            failures.append({"line":number,"reason":"DUPLICATE_TRANSCRIPT_ID","prompt_id":identity})
            values[identity]=None
        else:values[identity]=text.strip()
    return {key:value for key,value in values.items() if value is not None},failures


def inventory(path,layout="official",source_type=SourceType.EXTERNAL_RESEARCH_CORPUS):
    if layout not in {"official","mfa-demo"}:raise ValueError("UNKNOWN_JVS_LAYOUT")
    if source_type not in {SourceType.EXTERNAL_RESEARCH_CORPUS,SourceType.TEST_FIXTURE}:raise ValueError("JVS_CANNOT_BECOME_SELF_COLLECTED")
    root=private_root(path)
    speakers=[];parallel_speakers=[];unexpected=[];failures=[];records=[];texts=defaultdict(dict);transcript_sources=[];root_metadata=[]
    for folder in sorted(root.iterdir()):
        contained(folder,root)
        if folder.is_file() and not folder.name.startswith("jvs"):
            root_metadata.append(folder.name)
            if folder.suffix.lower()==".wav":unexpected.append({"path":folder.name,"reason":"UNEXPECTED_AUDIO_OUTSIDE_SPEAKER_TREE"})
        if folder.name.startswith("jvs"):
            if not folder.is_dir() or folder.name not in SPEAKERS:
                unexpected.append({"path":folder.name,"reason":"INVALID_SPEAKER_DIRECTORY"});continue
            contained(folder,root);speakers.append(folder.name)
            if layout=="official":
                parallel=folder/"parallel100"
                if not parallel.exists():continue
                if not parallel.is_dir():unexpected.append({"path":parallel.relative_to(root).as_posix(),"reason":"PARALLEL_DIRECTORY_NOT_DIRECTORY"});continue
                contained(parallel,root);parallel_speakers.append(folder.name)
                candidates=[parallel/name for name in ("transcript_utf8.txt","transcripts_utf8.txt") if (parallel/name).is_file()]
                if len(candidates)!=1:
                    failures.append({"speaker_id":folder.name,"reason":"MISSING_OR_AMBIGUOUS_OFFICIAL_TRANSCRIPT"})
                else:
                    values,issues=transcripts(candidates[0],root)
                    texts[folder.name]=values
                    failures.extend({"speaker_id":folder.name,**issue} for issue in issues)
                    transcript_sources.append({"speaker_id":folder.name,"path":str(candidates[0]),"sha256":digest(candidates[0]),"authority":"OFFICIAL_JVS_TRANSCRIPT_FILE"})
                audio_dir=parallel/"wav24kHz16bit"
                wavs=sorted(audio_dir.glob("*.wav")) if audio_dir.is_dir() else []
                canonical={p.resolve() for p in wavs}
                for item in sorted(parallel.rglob("*")):
                    contained(item,root)
                    if item.is_file() and (item.suffix.lower()==".wav" and item.resolve() not in canonical or
                                           item.suffix.lower() not in {".wav",".lab",".txt"}):
                        unexpected.append({"path":item.relative_to(root).as_posix(),"reason":"UNEXPECTED_PARALLEL_FILE"})
            else:
                wavs=sorted(folder.glob(folder.name+"_parallel100_*.wav"))
                if wavs:parallel_speakers.append(folder.name)
                for item in sorted(folder.glob("*.wav")):
                    contained(item,root)
                    if not re.fullmatch(folder.name+r"_(parallel100|nonpara30|whisper10|falsetto10)_.+\.wav",item.name):
                        unexpected.append({"path":item.relative_to(root).as_posix(),"reason":"UNEXPECTED_DEMO_FILE"})
            for wav in wavs:
                contained(wav,root)
                identity=wav.stem if layout=="official" else wav.stem.removeprefix(folder.name+"_parallel100_")
                if identity not in PROMPTS:
                    unexpected.append({"path":wav.relative_to(root).as_posix(),"reason":"UNEXPECTED_PROMPT_FILENAME"});continue
                if layout=="mfa-demo":
                    lab=contained(wav.with_suffix(".lab"),root)
                    if lab.is_file():
                        original=lab.read_text(encoding="utf-8-sig").strip()
                        texts[folder.name][identity]="".join(original.split())
                        transcript_sources.append({"speaker_id":folder.name,"prompt_id":identity,"path":str(lab),"sha256":digest(lab),
                            "authority":"OFFICIAL_MFA_DEMO_LAB_NOT_FULL_JVS_TRANSCRIPT","analysis_transform":"REMOVE_MFA_WORD_SEPARATION_WHITESPACE"})
                record={"speaker_id":folder.name,"prompt_id":identity,"audio_path":str(wav),"audio_sha256":digest(wav),"status":"HEADER_VALID"}
                try:
                    info=sf.info(wav)
                    record["audio"]={"sample_rate_hz":info.samplerate,"channels":info.channels,"frames":info.frames,
                                     "duration_seconds":info.frames/info.samplerate,"format":info.format,"subtype":info.subtype}
                    if info.frames<=0 or info.samplerate<16000 or info.format not in {"WAV","WAVEX"} or info.subtype not in {"PCM_16","PCM_24"}:
                        record["status"]="UNSUPPORTED_OR_EMPTY_AUDIO_HEADER"
                except (OSError,ValueError,sf.LibsndfileError):record["status"]="UNREADABLE_AUDIO_HEADER"
                records.append(record)
    duplicate_hashes=Counter(row["audio_sha256"] for row in records)
    prompts=[];matrix=[]
    for identity in sorted({row["prompt_id"] for row in records}|{key for values in texts.values() for key in values}):
        variants=defaultdict(list)
        for speaker,values in sorted(texts.items()):
            if identity in values:variants[values[identity]].append(speaker)
        stable=len(variants)==1
        text=next(iter(variants)) if stable else None
        available=[];present=[];cells={}
        for speaker in sorted(speakers):
            matching=[row for row in records if row["speaker_id"]==speaker and row["prompt_id"]==identity]
            row=matching[0] if len(matching)==1 else None
            if row:present.append(speaker)
            verified=bool(row and row["status"]=="HEADER_VALID" and stable and texts[speaker].get(identity)==text and duplicate_hashes[row["audio_sha256"]]==1)
            if verified:available.append(speaker)
            cells[speaker]={"audio_present":row is not None,"transcript_matches":bool(stable and texts[speaker].get(identity)==text),
                            "available_for_engineering_selection":verified,"audio_sha256":row["audio_sha256"] if row else None}
        import hashlib
        prompts.append({"corpus_prompt_id":identity,"text":text,"text_identity_sha256":hashlib.sha256(text.encode()).hexdigest() if text else None,
                        "transcript_status":"CONSISTENT_OBSERVED_TRANSCRIPTS" if stable else "MISSING_OR_CONFLICTING_TRANSCRIPTS",
                        "transcript_speaker_count":sum(len(s) for s in variants.values()),
                        "transcript_variant_count":len(variants),"audio_present_speaker_count":len(present),
                        "available_speaker_count":len(available),"available_speaker_ids":available,
                        "missing_expected_speaker_count":100-len(present),"missing_observed_speaker_ids":sorted(set(speakers)-set(present))})
        matrix.append({"corpus_prompt_id":identity,"speakers":cells})
    formats=Counter();rates=Counter();channels=Counter();durations=[]
    for row in records:
        if "audio" in row:
            meta=row["audio"];formats[meta["format"]+"/"+meta["subtype"]]+=1;rates[str(meta["sample_rate_hz"])]+=1;channels[str(meta["channels"])]+=1;durations.append(meta["duration_seconds"])
    return {"schema_version":"0.1","source_type":source_type,"speaker_identity_source":"CORPUS_METADATA_NOT_BIOMETRICALLY_VERIFIED",
            "corpus_root":str(root),"layout":layout,"scope":"OFFICIAL_LOCAL_TREE" if layout=="official" else "MFA_DEMO_SUBSET_NOT_FULL_JVS",
            "expected":{"speaker_count":100,"parallel100_prompts_per_speaker":100,"parallel100_wav_count":10000},
            "observed":{"speaker_count":len(speakers),"parallel100_speaker_count":len(parallel_speakers),"prompt_count":len(prompts),
                        "parallel100_wav_count":len(records),"shared_prompt_count":sum(p["available_speaker_count"]>=2 for p in prompts),
                        "five_speaker_prompt_count":sum(p["available_speaker_count"]>=5 for p in prompts)},
            "speaker_ids":sorted(speakers),"parallel100_speaker_ids":sorted(parallel_speakers),"missing_expected_speaker_ids":sorted(set(SPEAKERS)-set(speakers)),
            "missing_expected_prompt_audio":[{"speaker_id":speaker,"prompt_ids":sorted(set(PROMPTS)-{r["prompt_id"] for r in records if r["speaker_id"]==speaker})} for speaker in sorted(speakers)],
            "duplicate_audio_hashes":[{"sha256":sha,"count":count} for sha,count in sorted(duplicate_hashes.items()) if count>1],
            "audio_formats":dict(sorted(formats.items())),"sample_rates":dict(sorted(rates.items())),"channel_counts":dict(sorted(channels.items())),
            "duration_seconds_range":{"minimum":min(durations) if durations else None,"maximum":max(durations) if durations else None},
            "unexpected_files":unexpected,"root_metadata_files":root_metadata,"transcript_failures":failures,"transcript_sources":transcript_sources,
            "records":records,"prompts":prompts,"coverage_matrix":{"speaker_ids":sorted(speakers),"rows":matrix},
            "controlled_self_collected_reference_ready":False,"external_jvs_reference_ready":False,
            "availability_role":"HEADER_AND_HASH_AND_SHARED_TEXT_ONLY_NOT_MAPPED_REFERENCE_READINESS"}
