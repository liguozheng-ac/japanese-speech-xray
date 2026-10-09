"""Bounded real-audio compatibility only, using existing TASK-002–004 modules."""

from collections import Counter
from pathlib import Path
import shutil

from speech_xray.alignment.textgrid_parser import parse_textgrid
from speech_xray.japanese.long_vowel_mapper import analyze_mora
from speech_xray.japanese.reading import SudachiReadingProvider
from speech_xray.acoustics.mora_input import load_mora_analysis
from speech_xray.acoustics.pipeline import extract_acoustic_evidence
from speech_xray.corpus.batch_plan import digest,object_hash,pipeline_configuration
from speech_xray.corpus.pipeline import mfa_align,new_text
from speech_xray.corpus.models import SourceType
from speech_xray.acoustics.models import evidence_json
from .inventory import PRIVATE_ROOT,contained,private_root
from .discovery import recommend


def aligned_word_identity(target,prompt_words,aligned_words):
    """Link exact text intervals; MFA may merge earlier words and shift indices.

    This never splits a merged target word or guesses from a repeated surface.
    TASK-003 still owns all linguistic candidates and acoustic span mapping.
    """
    if "".join(w["surface"] for w in prompt_words)!="".join(w.surface for w in aligned_words):
        return None,"ALIGNED_TRANSCRIPT_CHARACTER_SEQUENCE_DIFFERS"
    declared=target["word_index"]
    start=sum(len(w["surface"]) for w in prompt_words[:declared])
    end=start+len(prompt_words[declared]["surface"])
    cursor=0
    for index,word in enumerate(aligned_words):
        right=cursor+len(word.surface)
        if cursor==start and right==end and word.surface==target["surface_hint"]:
            return index,None
        cursor=right
    return None,"DECLARED_WORD_BOUNDARY_NOT_PRESERVED"


def choose_smoke(inventory,discovery,prompt_limit=3,speaker_limit=3):
    if not 1<=prompt_limit<=5 or not 1<=speaker_limit<=5:raise ValueError("SMOKE_BOUND_MUST_BE_1_TO_5")
    eligible={p["corpus_prompt_id"] for p in discovery["targets_by_prompt"] if p["complete_prompt_reading_supported"] and p["target_count"]}
    preferred=[t["corpus_prompt_id"] for t in recommend(discovery)["selected_targets"]]
    priority={identity:index for index,identity in reversed(list(enumerate(preferred)))}
    prompts=sorted((p for p in inventory["prompts"] if p["corpus_prompt_id"] in eligible and p["available_speaker_count"]),
                   key=lambda p:(priority.get(p["corpus_prompt_id"],len(preferred)),-p["available_speaker_count"],p["corpus_prompt_id"]))[:prompt_limit]
    keys={(speaker,p["corpus_prompt_id"]) for p in prompts for speaker in p["available_speaker_ids"][:speaker_limit]}
    return tuple(r for r in inventory["records"] if (r["speaker_id"],r["prompt_id"]) in keys)


def run_smoke(inventory,discovery,records,output_root,aligner=mfa_align,run_label="default"):
    root=Path(output_root).resolve()
    if not root.is_relative_to(PRIVATE_ROOT.resolve()):raise ValueError("SMOKE_OUTPUT_MUST_REMAIN_PRIVATE")
    if len(records)>25:raise ValueError("SMOKE_MAXIMUM_25_UTTERANCES")
    if len({r["prompt_id"] for r in records})>5 or len({r["speaker_id"] for r in records})>5:raise ValueError("SMOKE_MAXIMUM_5_PROMPTS_AND_5_SPEAKERS")
    config={**pipeline_configuration(run_label=run_label),
            "external_jvs_code_sha256":{p.name:digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))}}
    prompt_info={p["corpus_prompt_id"]:p for p in discovery["targets_by_prompt"]}
    prompt_sources={p["corpus_prompt_id"]:p for p in inventory["prompts"]}
    corpus_root=private_root(inventory["corpus_root"])
    outcomes=[]
    for record in records:
        source=contained(record["audio_path"],corpus_root)
        identity=record["prompt_id"];info=prompt_info[identity];transcript=prompt_sources[identity]
        if record not in inventory["records"] or record["speaker_id"] not in transcript["available_speaker_ids"] or not info["complete_prompt_reading_supported"]:
            raise ValueError("SMOKE_SELECTION_NOT_VERIFIED_BY_INVENTORY")
        signature=object_hash({"source":record["audio_sha256"],"path":str(source),"text":transcript["text_identity_sha256"],"configuration":config})
        folder=root/signature[:32]/(record["speaker_id"]+"__"+identity)
        stem=record["speaker_id"]+"__"+identity
        paths={"run_directory":str(folder),"prepared_audio":str(folder/"input"/(stem+".wav")),
               "transcript":str(folder/"input"/(stem+".lab")),"textgrid":str(folder/"aligned"/(stem+".TextGrid"))}
        result={"speaker_id":record["speaker_id"],"corpus_prompt_id":identity,"source_type":inventory["source_type"],
                "audio_path":str(source),"audio_sha256":record["audio_sha256"],"text_identity_sha256":transcript["text_identity_sha256"],
                "configuration_sha256":object_hash(config),"outputs":paths,"alignment_status":"NOT_RUN","mora_status":"NOT_RUN", "acoustic_status":"NOT_RUN",
                "targets":[{"target_id":t["target_id"],"mapping_status":"NOT_RUN","reason":"UPSTREAM_STAGE_NOT_COMPLETED",
                            "long_vowel_span":None,"raw_duration_ms":None,"mora_span":2,"acoustic_status":"NOT_RUN"}
                           for t in discovery["targets"] if t["corpus_prompt_id"]==identity]}
        stage="ALIGNMENT_FAILED"
        try:
            folder.mkdir(parents=True,exist_ok=False)
            if digest(source)!=record["audio_sha256"]:raise ValueError("SOURCE_CHANGED_AFTER_INVENTORY")
            for ref in inventory["transcript_sources"]:
                if ref["speaker_id"]==record["speaker_id"] and ref.get("prompt_id",identity)==identity:
                    if digest(contained(ref["path"],corpus_root))!=ref["sha256"]:raise ValueError("TRANSCRIPT_CHANGED_AFTER_INVENTORY")
            Path(paths["prepared_audio"]).parent.mkdir(parents=True)
            shutil.copyfile(source,paths["prepared_audio"])
            if digest(paths["prepared_audio"])!=record["audio_sha256"]:raise ValueError("PREPARED_SOURCE_HASH_MISMATCH")
            # MFA performs its own Japanese tokenization. Artificial spaces are
            # converted into underscores and can merge the entire sentence.
            new_text(paths["transcript"],transcript["text"]+"\n")
            aligner(paths,record)
            alignment=parse_textgrid(Path(paths["textgrid"]))
            new_text(folder/"alignment.json",alignment.to_json());result["alignment_status"]="PASS"
            stage="MORA_MAPPING_FAILED"
            mora=analyze_mora(alignment,SudachiReadingProvider())
            new_text(folder/"mora-analysis.json",mora.to_json())
            result["targets"]=[]
            for target in (t for t in discovery["targets"] if t["corpus_prompt_id"]==identity):
                aligned_index,identity_reason=aligned_word_identity(target,info["words"],mora.words)
                if aligned_index is not None and mora.words[aligned_index].reading_result.reading!=target["expected_word_reading"]:
                    aligned_index=None;identity_reason="ALIGNED_WORD_READING_DIFFERS"
                spans=[span for span in mora.long_vowel_spans if span.word_index==aligned_index
                       and tuple(mora.morae[i].word_mora_index for i in span.mora_indices)==tuple(target["word_mora_indices"])
                       and span.mapping_basis==target["candidate_type"] and span.vowel_class==target["vowel_class"]
                       and mora.words[span.word_index].surface==target["surface_hint"]]
                mapped=len(spans)==1
                span=spans[0] if mapped else None
                result["targets"].append({"target_id":target["target_id"],"mapping_status":"MAPPED" if mapped else "UNRESOLVED",
                        "reason":None if mapped else identity_reason or "DECLARED_LEXICAL_TARGET_NOT_UNIQUELY_MAPPED", "long_vowel_span":span.to_dict() if span else None,
                        "raw_duration_ms":span.duration_ms if span else None,"mora_span":2,"acoustic_status":"NOT_RUN"})
            result["mora_status"]="PASS" if result["targets"] and all(t["mapping_status"]=="MAPPED" for t in result["targets"]) else "PARTIAL_MAPPING"
            result["mora_unresolved_counts"]=dict(sorted(Counter(item.reason for item in mora.unresolved_items).items()))
            stage="ACOUSTIC_EXTRACTION_FAILED"
            acoustic=extract_acoustic_evidence(source,load_mora_analysis(folder/"mora-analysis.json"))
            new_text(folder/"acoustic-evidence.json",acoustic.to_json());result["acoustic_status"]=acoustic.extraction_status
            evidence={span.original_span.id:span for span in acoustic.spans}
            for target in result["targets"]:
                span=target["long_vowel_span"]
                if span and span["id"] in evidence:target["acoustic_status"]=evidence[span["id"]].extraction_status
                elif span:target["acoustic_status"]="SPAN_EVIDENCE_MISSING"
            result["status"]="COMPATIBILITY_OBSERVED" if any(t["mapping_status"]=="MAPPED" and t["acoustic_status"]=="OK" for t in result["targets"]) else "REVIEW_REQUIRED"
            result["derived_sha256"]={p.name:digest(p) for p in (folder/"alignment.json",folder/"mora-analysis.json",folder/"acoustic-evidence.json",Path(paths["transcript"]))}
        except (OSError,ValueError,RuntimeError):
            result["status"]=stage;result["reason"]="STAGE_FAILED_OR_EXISTING_RUN_REQUIRES_REVIEW"
            result[{"ALIGNMENT_FAILED":"alignment_status","MORA_MAPPING_FAILED":"mora_status",
                    "ACOUSTIC_EXTRACTION_FAILED":"acoustic_status"}[stage]]="FAILED"
            for target in result["targets"]:
                if target["mapping_status"]=="NOT_RUN":target["reason"]=stage
        outcomes.append(result)
        if folder.is_dir() and not (folder/"smoke-outcome.json").exists():new_text(folder/"smoke-outcome.json",evidence_json(result))
    return {"schema_version":"0.1","source_type":inventory["source_type"],"scope":inventory["scope"],"configuration":config,
            "speaker_count":len({r["speaker_id"] for r in records}),"prompt_count":len({r["prompt_id"] for r in records}),"utterance_count":len(records),
            "outcomes":outcomes,"status_counts":dict(sorted(Counter(r["status"] for r in outcomes).items())),
            "counts_toward_controlled_readiness":False,"external_jvs_reference_ready":False,
            "boundary":"SMOKE_ONLY_NO_FULL_REFERENCE_BUILD_OR_DIAGNOSIS"}
