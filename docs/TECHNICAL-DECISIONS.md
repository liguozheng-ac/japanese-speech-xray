# Engineering decisions

## Evidence before scores

The frozen pYIN implementation returns null for unavailable F0 and does not interpolate across unvoiced gaps. Voiced probability is algorithm evidence, not a calibrated pronunciation accuracy percentage. Exceptions or insufficient support produce ABSTAINED; original audio and manual practice remain available in the private product interface.

Uploaded audio is not silently downmixed or resampled. WAV headers cannot be relabeled to claim an unprocessed rate. Browser microphone capture has a separate, explicitly documented channel-conversion policy. Synthetic readings and native-speaker research resources have different provenance; model alignments are not manual ground truth.

Historical duration normalization, reference medians and pYIN parameters remain unchanged. The reference corpus was not rebuilt and Narabas was not activated.

## Public checkout isolation

The accepted snapshot was exported through a file allowlist into an independent repository. The original repository and V1 tag were preserved.

1. The public Settings defaults to MFA and can start without private resources, reporting experimental NOT_READY honestly.
2. Configuration is read only when explicitly supplied; old private product configuration is not automatically discovered. Conflicting engine choices are rejected.
3. Optional synthetic reference files use data/optional-reference-audio or SPEECH_XRAY_REFERENCE_AUDIO_DIR. Frozen source, text and hash checks remain in place. No reference WAV is bundled.
4. Three Haruka-dependent and two JVS-dependent tests retain explicit resource skips.
5. Authored worksheets, QA, package URL locks and resource identities were individually reviewed. They are not recordings, model binaries or participant data.
6. The public checkout includes a test runner, a non-speech pYIN example, editable package metadata and isolation regression tests.

These changes decouple the public package from private resources; they do not replace the accepted scientific implementation.

## Reproduction and documentation

The Windows numerical environment uses official conda-forge URL locks; HTTP packages have a separate pip lock. Dependencies are obtained through package managers, not redistributed as an environment bundle. The wheel packages Python modules and notices, not the complete product or all runtime configuration.

The 2026-10-16 presentation update adds English documentation, source-matched diagrams and English-localized captures of existing DEMO components. Displayed numeric values are unchanged. Documentation captures are not evidence of a newly deployed English-language application.
