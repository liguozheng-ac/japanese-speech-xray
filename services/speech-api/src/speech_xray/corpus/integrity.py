"""Validate receipts and reuse the original reference integrity adapter."""

from pathlib import Path

from speech_xray.acoustics.mora_input import load_mora_analysis
from speech_xray.reference.integrity import validate_entry
from speech_xray.reference.models import ArtifactReference, ReferenceEntry, ReferenceManifest, TargetIdentity
from .batch_plan import digest,object_hash
from .models import BatchOutcome,RecordingStatus as Status,SourceType,TargetOutcome
from .prompt_manifest import authoring_words
from speech_xray.japanese.reading import SudachiReadingProvider
from .validation import keys,private_path,read_json,sha256


def canonical_transcript(prompt):
    return " ".join(word[0] for word in authoring_words(prompt,SudachiReadingProvider()))+"\n"


def reference_manifest(manifest,pack,target,identity,entries,transcript_hash,source,source_hash):
    real=all(entry.speaker_id in {s.speaker_id for s in manifest.speakers if s.source_type==SourceType.REAL_REFERENCE_RECORDING} for entry in entries)
    dataset=(("name","Speech X-Ray controlled collection"),("source",f"{manifest.corpus_id}:{pack.prompt_pack_id}:v{pack.prompt_pack_version}"),
             ("local_only",True),("usage_restrictions","Local permission-limited analysis/features; raw/aggregate publication requires separate session permission"),
             ("material_kind","REAL_REFERENCE_AUDIO" if real else "STRUCTURED_REFERENCE_FIXTURE"))
    return ReferenceManifest(manifest.corpus_id,entries[0].prompt_id,transcript_hash,identity,dataset,
                             "corpus-reference-input-v1",tuple(entries),str(source),source_hash)


def targets_from_artifacts(manifest,pack,intake,refs,receipt_path,receipt_hash):
    prompt=next(p for p in pack.prompts if p.prompt_id==intake.recording.prompt_id)
    refs=dict(refs)
    if Path(refs["transcript"].path).read_text(encoding="utf-8")!=canonical_transcript(prompt):
        raise ValueError("KNOWN_PROMPT_TRANSCRIPT_MISMATCH")
    mapped=load_mora_analysis(refs["mora_analysis"].path)
    value,_=read_json(Path(refs["mora_analysis"].path))
    targets=[]
    for target in prompt.targets:
        matches=[]
        for span in mapped.long_vowel_spans:
            word=value["words"][span.word_index]
            local=tuple(int(value["morae"][i]["word_mora_index"]) for i in span.mora_indices)
            region="".join(value["morae"][i]["reading"] for i in span.mora_indices)
            if (word["surface"],word["reading"],local,region,span.mapping_basis,span.vowel_class)==(
                    target.surface_hint,target.expected_word_reading,target.word_mora_indices,target.expected_reading_region,
                    target.expected_candidate_type,target.expected_vowel_class):
                matches.append(span)
        if len(matches)!=1:
            targets.append(TargetOutcome(target.target_id,Status.MORA_MAPPING_FAILED,"DECLARED_TARGET_NOT_UNIQUELY_MAPPED"))
            continue
        span=matches[0]
        identity=TargetIdentity(target.target_id,span.word_index,target.word_mora_indices,span.phone_label,span.vowel_class,2,span.mapping_basis)
        recording=intake.recording
        entry=ReferenceEntry(recording.prompt_id,target.target_id,recording.speaker_id,recording.take_id,recording.key,span.id,
                             tuple((key,refs[key]) for key in ("audio","alignment","mora_analysis","acoustic_evidence","transcript")))
        reference=reference_manifest(manifest,pack,target,identity,[entry],refs["transcript"].sha256,receipt_path,receipt_hash)
        try:
            validate_entry(reference,entry)
            targets.append(TargetOutcome(target.target_id,Status.REFERENCE_READY,"UPSTREAM_BUNDLE_VERIFIED",entry,identity))
        except ValueError:
            targets.append(TargetOutcome(target.target_id,Status.REFERENCE_INTEGRITY_FAILED,"UPSTREAM_REFERENCE_INTEGRITY_FAILURE"))
    return tuple(targets)


def assess_receipt(manifest,pack,intake,config,receipt_path,paths,signature):
    try:
        value,receipt_hash=read_json(receipt_path)
        if intake.recording.evidence_receipt_sha256 and receipt_hash!=intake.recording.evidence_receipt_sha256:
            raise ValueError("RECEIPT_HASH_MISMATCH")
        keys(value,("schema_version","recording_id","session_id","source_type","input_audio_sha256","prompt_pack_sha256",
                    "configuration_sha256","input_signature","artifacts"))
        if (value["schema_version"],value["recording_id"],value["session_id"],value["source_type"],value["input_audio_sha256"],
                value["prompt_pack_sha256"],value["configuration_sha256"],value["input_signature"])!=(
                "0.1",intake.recording.key,intake.recording.session_id,intake.recording.source_type,intake.audio_sha256,pack.sha256,
                object_hash(config),signature):
            raise ValueError("INPUT_OR_CONFIGURATION_CHANGED")
        keys(value["artifacts"],("alignment","mora_analysis","acoustic_evidence","transcript"))
        refs={"audio":ArtifactReference(intake.recording.audio_path,intake.audio_sha256)}
        for name,ref in value["artifacts"].items():
            keys(ref,("path","sha256"))
            path=private_path(ref["path"],receipt_path.parent,Path(manifest.corpus_root))
            if digest(path)!=sha256(ref["sha256"]):
                raise ValueError("DERIVED_ARTIFACT_HASH_MISMATCH")
            refs[name]=ArtifactReference(str(path),ref["sha256"])
        targets=targets_from_artifacts(manifest,pack,intake,refs,receipt_path,receipt_hash)
        status=Status.REFERENCE_READY if all(t.status==Status.REFERENCE_READY for t in targets) else Status.MORA_MAPPING_FAILED
        return BatchOutcome(intake,status,"HASH_CONFIG_AND_REFERENCE_INTEGRITY_VERIFIED",tuple(sorted(paths.items())),targets)
    except (OSError,ValueError,KeyError,TypeError,IndexError):
        return BatchOutcome(intake,Status.REBUILD_REQUIRED,"UNVERIFIED_OR_STALE_DERIVED_EVIDENCE",tuple(sorted(paths.items())))
