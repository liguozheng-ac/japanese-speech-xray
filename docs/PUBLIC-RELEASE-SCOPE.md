# Publication scope

TASK-021 Phase A reviewed the independent code export. Phase B published it under a limited MIT grant on 2026-10-10. On 2026-10-16 the owner separately requested an English GitHub presentation with visible architecture/data-flow diagrams and the existing product DEMO panels. The presentation update does not publish the frontend, audio, models or private research dataset and does not deploy a website.

| File group | Provenance and rights | Included |
| --- | --- | --- |
| Listed Python backend, tests, tools and example | Author-owned code, explicitly enumerated in LICENSE-SCOPE.md; MIT | Yes |
| Authored JSON schemas, structural fixtures, prompts and configuration | Individually reviewed structural material; not an audio corpus or MIT code grant | Yes |
| Environment locks, requirements and package metadata | Official package identities; dependency binaries not bundled | Yes |
| Technical documentation and file manifest | Reviewed prose and content hashes; no private audit paths | Yes |
| Architecture / processing SVGs | New author-owned documentation figures reflecting existing code; display rights retained | Yes |
| Empty workspace screenshot | Previously reviewed static product display; no private audio/results | Yes |
| Four English-localized DEMO captures | Actual React components with unchanged saved synthetic-demo data; pitch/structure/aggregate reference/evidence panels; display-only | Yes |
| Complete React source, browser recording code, build bundles and source maps | Private product implementation | No |
| Original background video or its frames | Private visual material; not part of the showcase captures | No |
| User recordings, manual annotations, raw response JSON, speaker-level statistics and audit logs | Private / research material | No |
| JVS recordings, Haruka WAVs, Narabas weights, MFA pretrained resources | Separately governed resources; not distributed | No |
| Original Git history and V1 tag objects | Not imported into this independent public history | No |

Only the 198 Python paths in [LICENSE-SCOPE.md](../LICENSE-SCOPE.md) are granted MIT. Documentation, diagrams, screenshots, configuration and fixtures do not inherit that license. Dependencies retain their own terms.

The [file manifest](../TASK-021-PUBLIC-FILE-MANIFEST.md) records the current paths, content hashes and publication category. Historical Phase A/B counts remain historical receipts; new documentation figures increase the current file count. No Git LFS, submodules, frontend build output or deployment workflow is introduced.
