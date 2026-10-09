"""Reuse TASK-003 linguistic candidates without constructing any acoustic timing."""

from collections import Counter
from speech_xray.japanese.reading import SudachiReadingProvider
from speech_xray.japanese.mora_tokenizer import tokenize_mora
from speech_xray.japanese.long_vowel_mapper import long_vowel_candidates
from speech_xray.corpus.prompt_manifest import PUNCTUATION,target_pattern


def discover(inventory,provider=None):
    provider=provider or SudachiReadingProvider()
    targets=[];prompts=[]
    for prompt in inventory["prompts"]:
        identity=prompt["corpus_prompt_id"];text=prompt["text"];issues=[];words=[];local_targets=[];mora_offset=0
        if not text:
            issues.append({"reason":"MISSING_OR_CONFLICTING_TRANSCRIPT"})
        else:
            pieces=provider.reading_for(text).pieces
            if not pieces or "".join(p.surface for p in pieces)!=text:
                issues.append({"reason":"READING_PIECES_DO_NOT_COVER_TRANSCRIPT"})
            else:
                for piece in pieces:
                    if piece.surface in PUNCTUATION:continue
                    index=len(words);reading=provider.reading_for(piece.surface)
                    word={"word_index":index,"surface":piece.surface,"reading":reading.reading,"status":"SUPPORTED"}
                    words.append(word)
                    if not reading.resolved:
                        word["status"]="UNSUPPORTED_WORD_READING";issues.append({"word_index":index,"reason":word["status"]});continue
                    tokens=tokenize_mora(reading.reading)
                    if tokens.issue:
                        word["status"]="UNSUPPORTED_MORA_TOKENIZATION";issues.append({"word_index":index,"reason":word["status"]});continue
                    for candidate in long_vowel_candidates(tokens.morae):
                        local=candidate.mora_indices
                        target={"target_id":f"jvs-parallel100-{identity.lower()}-w{index:03}-m{local[0]:03}",
                                "corpus_prompt_id":identity,"text_identity_sha256":prompt["text_identity_sha256"],
                                "candidate_index":len(local_targets),"word_index":index,"surface_hint":piece.surface,
                                "expected_word_reading":reading.reading,"word_mora_indices":list(local),
                                "utterance_mora_indices":[mora_offset+i for i in local],"candidate_type":candidate.mapping_basis,
                                "orthographic_pattern":target_pattern(candidate,tokens.morae),"vowel_class":candidate.vowel_class,
                                "mora_span":2,"reading_region":"".join(tokens.morae[i].reading for i in local),
                                "available_speaker_count":prompt["available_speaker_count"],"available_speaker_ids":prompt["available_speaker_ids"]}
                        local_targets.append(target)
                    mora_offset+=len(tokens.morae)
        if issues:
            for target in local_targets:target["utterance_mora_indices"]=None
        for target in local_targets:
            target["complete_prompt_reading_supported"]=not issues
            target["prompt_mora_count"]=mora_offset if not issues else None
            target["word_position"]= "INITIAL" if target["word_index"]==0 else "FINAL" if target["word_index"]==len(words)-1 else "MEDIAL"
        targets.extend(local_targets)
        prompts.append({"corpus_prompt_id":identity,"text_identity_sha256":prompt["text_identity_sha256"],"target_count":len(local_targets),
                        "words":words,"unsupported":issues,"complete_prompt_reading_supported":not issues,
                        "prompt_mora_count":mora_offset if not issues else None,"target_ids":[t["target_id"] for t in local_targets]})
    return {"schema_version":"0.1","source_type":inventory["source_type"],"scope":inventory["scope"],"total_parallel_prompts":len(prompts),
            "prompts_with_targets":sum(p["target_count"]>0 for p in prompts),"prompts_without_targets":sum(p["target_count"]==0 for p in prompts),
            "prompts_with_unsupported_reading":sum(bool(p["unsupported"]) for p in prompts),"supported_target_count":len(targets),
            "candidate_type_counts":dict(sorted(Counter(t["candidate_type"] for t in targets).items())),
            "orthographic_pattern_counts":dict(sorted(Counter(t["orthographic_pattern"] for t in targets).items())),
            "vowel_class_counts":dict(sorted(Counter(t["vowel_class"] for t in targets).items())),
            "mora_span_counts":dict(sorted(Counter(str(t["mora_span"]) for t in targets).items())),
            "targets":targets,"targets_by_prompt":prompts,
            "evidence_role":"LEXICAL_CANDIDATES_ONLY_NO_ACOUSTIC_BOUNDARIES_OR_REFERENCE_READINESS"}


def recommend(discovery,minimum_speakers=5,limit=20):
    if type(minimum_speakers) is not int or minimum_speakers<1 or not 1<=limit<=30:raise ValueError("INVALID_STRUCTURAL_SELECTION_POLICY")
    remaining=[t for t in discovery["targets"] if t["complete_prompt_reading_supported"] and t["available_speaker_count"]>=minimum_speakers
               and t["mora_span"]==2 and 1<=t["prompt_mora_count"]<=80]
    selected=[];patterns=set();vowels=set();positions=set();prompts=set()
    while remaining and len(selected)<limit:
        # Lexical diversity and availability only; never voice/diagnostic quality.
        remaining.sort(key=lambda t:(-(t["orthographic_pattern"] not in patterns),-(t["vowel_class"] not in vowels),
                                    -(t["word_position"] not in positions),-(t["corpus_prompt_id"] not in prompts),
                                    -t["available_speaker_count"],t["prompt_mora_count"],t["target_id"]))
        target=remaining.pop(0);selected.append(target)
        patterns.add(target["orthographic_pattern"]);vowels.add(target["vowel_class"]);positions.add(target["word_position"]);prompts.add(target["corpus_prompt_id"])
    return {"schema_version":"0.1","source_type":discovery["source_type"],"scope":discovery["scope"],"minimum_speaker_availability":minimum_speakers,
            "target_limit":limit,"selected_target_count":len(selected),"selected_prompt_count":len(prompts),"selected_targets":selected,
            "selection_role":"ENGINEERING_STRUCTURE_AND_AVAILABILITY_NOT_NATIVE_CORRECTNESS",
            "eligibility_rules":["COMPLETE_SUPPORTED_LEXICAL_READING","UNIQUE_SHARED_TRANSCRIPT","VALID_HEADER_NON_DUPLICATE_AUDIO",
                                 "MORA_SPAN_TWO","PROTOTYPE_SPEAKER_AVAILABILITY","PROMPT_LENGTH_1_TO_80_MORAE"],
            "feasibility_decision":None,"decision_status":"REQUIRES_OFFICIAL_CORPUS_AND_REAL_MFA_SMOKE",
            "self_collection_required_for_m1":None,"next_full_reference_build_recommended":False,
            "external_jvs_reference_ready":False,"controlled_self_collected_reference_ready":False}


def review_recommendation(selection,smoke,discovery=None):
    """Defer structurally selected targets unusable in three aligned smoke IDs.

    Untested targets stay explicitly provisional. These are pipeline evidence
    states, not pronunciation rankings or reference-profile readiness.
    """
    if selection["source_type"]!=smoke["source_type"] or selection["scope"]!=smoke["scope"]:
        raise ValueError("SMOKE_REVIEW_SOURCE_OR_SCOPE_DIFFERS")
    def review_target(target):
        aligned=set();usable=set();attempted=set()
        for row in smoke["outcomes"]:
            if row["corpus_prompt_id"]!=target["corpus_prompt_id"]:continue
            if row["text_identity_sha256"]!=target["text_identity_sha256"] or row["speaker_id"] not in target["available_speaker_ids"]:
                raise ValueError("SMOKE_REVIEW_TEXT_OR_SPEAKER_IDENTITY_DIFFERS")
            jobs=[item for item in row["targets"] if item["target_id"]==target["target_id"]]
            if len(jobs)!=1:raise ValueError("SMOKE_REVIEW_TARGET_MISSING_OR_DUPLICATE")
            attempted.add(row["speaker_id"])
            if row["alignment_status"]=="PASS":aligned.add(row["speaker_id"])
            if row["alignment_status"]=="PASS" and jobs[0]["mapping_status"]=="MAPPED" and jobs[0]["acoustic_status"]=="OK":
                usable.add(row["speaker_id"])
        state="DEFER_NO_USABLE_SMOKE_SPAN" if len(aligned)>=3 and not usable else "USABLE_IN_BOUNDED_SMOKE" if usable else "NOT_SMOKE_TESTED" if not attempted else "PENDING_USABLE_SMOKE_SPAN"
        return {**target,"smoke_review":{"status":state,"attempted_speaker_count":len(attempted),
            "aligned_speaker_count":len(aligned),"usable_speaker_count":len(usable)}}
    reviewed=[];deferred=[];replacements=0
    for target in selection["selected_targets"]:
        value=review_target(target)
        (deferred if value["smoke_review"]["status"]=="DEFER_NO_USABLE_SMOKE_SPAN" else reviewed).append(value)
    if discovery is not None:
        if discovery["scope"]!=selection["scope"] or discovery["source_type"]!=selection["source_type"]:
            raise ValueError("REPLACEMENT_DISCOVERY_SOURCE_OR_SCOPE_DIFFERS")
        used={t["target_id"] for t in selection["selected_targets"]}
        pool=[t for t in discovery["targets"] if t["target_id"] not in used and t["complete_prompt_reading_supported"]
              and t["available_speaker_count"]>=selection["minimum_speaker_availability"]
              and t["mora_span"]==2 and 1<=t["prompt_mora_count"]<=80]
        for failed in deferred:
            alternatives=[review_target(t) for t in pool if t["target_id"] not in used
                          and t["orthographic_pattern"]==failed["orthographic_pattern"] and t["vowel_class"]==failed["vowel_class"]]
            alternatives=[t for t in alternatives if t["smoke_review"]["usable_speaker_count"]>=3]
            alternatives.sort(key=lambda t:(-t["available_speaker_count"],t["prompt_mora_count"],t["target_id"]))
            if alternatives:
                replacement={**alternatives[0],"replaces_deferred_target_id":failed["target_id"]}
                reviewed.append(replacement);used.add(replacement["target_id"]);replacements+=1
    return {**selection,"pre_smoke_selected_target_count":selection["selected_target_count"],
        "selected_targets":reviewed,"selected_target_count":len(reviewed),
        "selected_prompt_count":len({t["corpus_prompt_id"] for t in reviewed}),
        "deferred_targets":deferred,"deferred_target_count":len(deferred),
        "replacement_target_count":replacements,
        "review_role":"KNOWN_PIPELINE_GAPS_DEFERRED_UNTESTED_TARGETS_PROVISIONAL_NO_PROFILE_READINESS"}
