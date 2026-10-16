# Optional alignment and reference resources

WAV admission, prompt discovery and pYIN do not require a large speech model. The following resources belong to optional experimental or reference paths; obtaining a model alone does not reproduce private research results.

## MFA

MFA 3.4.2 is MIT-licensed software. Historical Windows package URLs are recorded in task002-conda-win-64.explicit.txt; the large alignment environment is not installed automatically. The pitch environment is not a replacement for the MFA/Kaldi environment.

Japanese acoustic model v3.0.0, dictionary v3.0.0 and G2P v2.0.1a identities are recorded in task002-resources.json. Resource binaries are not included. Official model pages identify CC BY 4.0; retain the McAuliffe / Sonderegger attribution, source, resource license and modification notice where applicable. Do not substitute the MFA software MIT license for a model license. See [third-party sources](../THIRD_PARTY.md).

The full experimental API also requires compatible, verified reference profiles, manifests, descriptors and measurement identities. These private research resources are not published. Missing resources return 503; automatic alignment does not become ground truth because it ran successfully. Use SPEECH_XRAY_CONFIG for explicit configuration; Settings, Resource and ReferenceResource are defined in source. File paths and SHA-256 must correspond to actual resources. SPEECH_XRAY_ALIGNER=mfa must agree with an explicit configuration.

## Synthetic reference

Haruka Desktop WAV redistribution remains under review, so no reference audio is distributed. Missing references return SYNTHETIC_REFERENCE_UNAVAILABLE without discarding input F0. The optional directory is data/optional-reference-audio or SPEECH_XRAY_REFERENCE_AUDIO_DIR. The reader still verifies manifest voice/type, exact sentence and frozen SHA-256; an arbitrary same-named WAV is not accepted as the frozen reference.

Static, source-labeled analytical product panels are separately included for display following the owner's 2026-10-16 request. This does not grant rights to the audio, publish private response JSON or resolve resource redistribution. No Azure neural-TTS terms are substituted for Windows Desktop voice terms. Synthetic speech is not a native-speaker accuracy standard.

## JVS and offline research

JVS audio, manual labels, speaker-level reference profiles and complete distributions remain excluded. Static product captures show only the already-displayed aggregate summary; they are not a downloadable reference dataset or a validated target standard.

Narabas source identity and MIT provenance are recorded, but ONNX weights, frozen phone sequences, acceptance configuration and 300 research records remain excluded. MFA is the default; Narabas is not activated for production. WhisperX and Silero VAD are historical offline research sources, not default runtime dependencies of this checkout.
