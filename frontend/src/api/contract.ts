// Generated from the frozen API v1 serialization schema; run node scripts/generate-contract.mjs.
export type Acoustics = {
    selected_frame_count: number;
    voiced_frame_count: number;
    raw_f0_median_hz: number | null;
    rms_median: number | null;
    extraction_status: string;
    f0_interpretation?: "RAW_ACOUSTIC_MEASUREMENT";
};
export type AlignmentProvenance = {
    aligner_commit: string;
    model_sha256: string;
    phone_sequence_version: "narabas-ja-1.0.0";
    phone_sequence_sha256: string;
    alignment_sample_rate_hz: 16000;
    resample_method: "SCIPY_RESAMPLE_POLY_PCM16_1.0.0";
    runtime_lock_sha256: string;
};
export type Audio = {
    sha256: string;
    duration_ms: number;
    sample_rate_hz: number;
    channels: number;
    sample_count: number;
    decoded_format: "WAV";
};
export type Availability = {
    duration: boolean;
    reference: boolean;
    deviation: boolean;
    realization: boolean;
    raw_f0: boolean;
    rms: boolean;
};
export type Deviation = {
    signed_delta: number;
    ratio_to_median: number;
    mad_distance: number | null;
    direction: "BELOW_REFERENCE_MEDIAN" | "AT_REFERENCE_MEDIAN" | "ABOVE_REFERENCE_MEDIAN";
    inside_iqr: boolean;
    inside_observed_min_max: boolean;
    warnings: Array<string>;
    formula_version?: "0.1";
};
export type Duration = {
    raw_duration_ms: number;
    rate_normalized_duration: number;
    rate_normalized_duration_per_mora: number;
    normalization_version?: "0.1";
};
export type Mora = {
    index: number;
    word_index: number;
    word_mora_index: number;
    representation: string;
    kind: string;
    shared_span: TimeSpan | null;
    timing_basis: "SHARED_ORIGINAL_LONG_PHONE" | "NO_INDIVIDUAL_ACOUSTIC_BOUNDARY" | "SHARED_NATIVE_PHONE_ENVELOPE";
};
export type Phone = {
    start_ms: number;
    end_ms: number;
    index: number;
    symbol: string;
    word_index: number | null;
};
export type Prompt = {
    prompt_id: string;
    display_text: string;
    language?: "ja";
    prompt_version: string;
};
export type Provenance = {
    pipeline_version?: "product-m1-1.0.0" | "product-m1-1.1.0";
    analysis_policy_version: string;
    prompt_binding_version: string;
    prompt_binding_sha256: string;
    prompt_pack_sha256: string;
    reference_version?: string;
    deviation_version?: "0.1";
    realization_version?: "0.1";
    alignment_engine?: "MFA_CPU_CLI" | "NARABAS_CPU_WORKER";
    alignment_engine_version: string;
    acoustic_model_sha256: string;
    dictionary_sha256: string | null;
    g2p_model_sha256: string | null;
    runtime_identity_sha256: string;
    alignment_provenance?: AlignmentProvenance | null;
    compatibility_policy?: "EXACT_SURFACE_READING_LOCAL_MORA_VOWEL_BASIS_FEATURE_V1";
    sentence_context_equivalence_validated?: false;
    candidate_audio_in_reference: boolean;
    comparison_role: "DESCRIPTIVE_ONLY" | "IN_POPULATION_NATIVE_INTEGRATION_SMOKE";
    real_labelled_learner_data_ready?: false;
    calibrated_diagnosis_ready?: false;
    cross_condition_likelihood_comparable?: false;
};
export type Realization = {
    canonical_pronunciation: Array<string>;
    experimental_reduced_pronunciation: Array<string> | null;
    selected_variant: "CANONICAL_SELECTED" | "REDUCED_SELECTED" | "AMBIGUOUS_OR_UNRESOLVED" | "ALIGNMENT_FAILED";
    variant_identity_status: string;
    evidence_status: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE" | "ABSTAINED";
    interpretation?: "EXPERIMENTAL_ENGINEERING_PROBE";
    hypothesis_version?: "0.1";
};
export type Reason = {
    stage: string;
    reason_code: string;
    message: string;
};
export type Reference = {
    target_id: string;
    version: string;
    profile_sha256: string;
    independent_speaker_count: number;
    primary_feature?: "rate_normalized_duration";
    median: number;
    mad: number;
    q25: number;
    q75: number;
    iqr: number;
    minimum: number;
    maximum: number;
    readiness: string;
};
export type Target = {
    target_id: string;
    surface: string;
    reading: string;
    word_index: number | null;
    mora_indices: Array<number>;
    mora_span?: 2;
    vowel_class: "A" | "I" | "U" | "E" | "O";
    mapping_basis: "PROLONGED_MARK" | "KANA_SEQUENCE";
    time_span: TimeSpan | null;
    duration: Duration | null;
    reference: Reference | null;
    deviation: Deviation | null;
    realization: Realization | null;
    acoustics: Acoustics | null;
    availability: Availability;
    evidence_status: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE" | "ABSTAINED";
    reasons: Array<Reason>;
};
export type TimeSpan = {
    start_ms: number;
    end_ms: number;
};
export type Timeline = {
    start_ms: number;
    end_ms: number;
    basis?: "PRIMARY_ANALYSIS_ALIGNMENT";
    words: Array<Word>;
    phones: Array<Phone>;
    morae: Array<Mora>;
};
export type Word = {
    start_ms: number;
    end_ms: number;
    index: number;
    surface: string;
    reading: string | null;
};
export type SpeechXRayAnalysisResponse = {
    schema_version?: "1.0.0" | "1.1.0";
    analysis_id: string;
    analysis_fingerprint: string;
    status: "COMPLETED" | "PARTIAL_EVIDENCE" | "ABSTAINED";
    prompt: Prompt;
    audio: Audio;
    timeline: Timeline | null;
    targets: Array<Target>;
    warnings: Array<Reason>;
    provenance: Provenance;
};
