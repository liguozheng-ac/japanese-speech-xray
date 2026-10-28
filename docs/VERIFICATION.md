# Verification receipts

Phase A: 2026-10-09. Phase B: 2026-10-10. Platform: Windows x64, independent Conda prefix, Python 3.13.15. The 2026-10-16 update changes documentation and display assets only; the table below is explicitly historical, not a new test run.

| Scope | Total | Passed | Failures | Errors | Skipped | Receipt |
| --- | --- | --- | --- | --- | --- | --- |
| Accepted local V1 frontend | 95 | 95 | 0 | 0 | 0 | Historical user-accepted result; not rerun here |
| Accepted local V1 backend | 565 | 565 | 0 | 0 | 0 | Historical result; broader than the public checkout |
| Public checkout, Phase A | 548 | 543 | 0 | 0 | 5 | Actually run 2026-10-09, about 65.76 seconds |
| Public checkout, Phase B | 548 | 543 | 0 | 0 | 5 | Actually run 2026-10-10; runner 67.212 seconds |

The full local V1 also passed its historical TypeScript/build checks. That historical release did not include React source; the 2026-10-28 source extension below now verifies its build. Public editable install, pip check, compileall and wheel build were actually verified in Phase B. The wheel contains 129 backend Python modules and license notices, not product assets or all runtime configuration.

The five skips are two optional JVS corpus checks and three Haruka audio/resource checks. They remain skips, not passes. Private integrations and frozen research-resource tests were not all exported; individual exclusion records remain private. No test was deleted in this documentation update.

## Real TCP checks

Nine checks ran against a real uvicorn service, without an injected analyzer:

- Liveness, prompt catalog and OpenAPI: 200.
- Experimental readiness: 503 with missing resource components; independent input-pitch extraction still available.
- A generated 220 Hz tone: 100 frames, 75 accepted voiced frames, median 220.6358 Hz; reference unavailable explicitly.
- Silence: ABSTAINED / LOW_ENERGY_NO_F0, all F0 values null.
- Stereo and MP3-header input: 422.
- Experimental analysis: 503 / REFERENCE_ARTIFACT_MISSING, no fabricated result.

Phase A observed approximately 0.73 seconds startup and 1.26 seconds tone HTTP processing. Phase B observed 0.888 seconds startup and 1.34 seconds tone HTTP processing. These are individual engineering observations, not human-speech accuracy or latency guarantees. The generated tone example is not a real learner recording.

Phase B wheel SHA-256: 1145699167b0a5da457c71ba5f7075ab1267c49a3b3236de65ef85539a6df796; 222808 bytes. The artifact and raw receipts remain private and were not published to a package registry.

## Documentation update checks

The English showcase is checked separately for relative links, image dimensions, source-matched diagram paths, English explanatory labels, unchanged numeric demo values, unchanged backend implementation blobs, separately reviewed frontend source, excluded audio/model binaries, and final Git/remote consistency. This is not a fresh acoustic experiment or performance benchmark.

## Frontend publication checks — 2026-10-28

| Check | Actual result |
| --- | --- |
| Clean public frontend npm install | `npm ci` completed using the committed lock; 69 packages installed |
| Frontend tests | 101 total: **97 passed, 4 skipped, 0 failed**; 6.945 s |
| TypeScript and production build | **PASS**; 74 modules; Vite build 859 ms |
| Public backend regression | 548 total: **543 passed, 5 skipped, 0 failures/errors**; runner 131.101 s |
| Backend resource isolation | No implicit private configuration; excluded WAV/video remain absent |
| Product implementation | Accepted private product and deployed website not modified |

The four frontend skips need the exact excluded Haruka WAVs: three saved DEMO checks and one three-reading audio-integrity check. Missing/corrupt DEMO rejection and cancellation still run using deliberately non-matching engineering bytes; structural MVP tests use an explicitly authored tone. No engineering tone is presented as speech or a successful saved DEMO. Backend skips retain the historical two JVS / three Haruka requirements.

One initial frontend run reported a remaining original-audio dependency; the resource-dependent test was made explicit and the complete suite rerun to the result above. The publication changes the public-checkout isolation test to expect frontend source while continuing to reject implicit private resources; scientific/backend implementation code is unchanged.

Raw test logs and source/candidate audits remain in the local private publication receipt, not in the repository. These checks establish engineering reproducibility, not human pronunciation accuracy.
