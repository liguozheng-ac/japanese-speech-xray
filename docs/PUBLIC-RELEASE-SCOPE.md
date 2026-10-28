# Publication scope

The initial TASK-021 release published the reviewed Python implementation. On 2026-10-28 the owner authorized publication of the complete frontend source and requested Page 1 in the GitHub product introduction. This supersedes the earlier frontend-source exclusion; historical release counts remain historical records.

| File group | Current scope |
| --- | --- |
| 198 listed author-owned Python files | Included; MIT |
| 65 listed author-owned frontend source files | Included; MIT: Page 0/Page 1, recording worklet, components, CSS, scripts and tests |
| npm manifest / lock and TypeScript / Vite configuration | Included; dependencies installed separately |
| Reviewed contracts, prompts and structural fixtures | Included; outside the source-code allowlist |
| Saved synthetic DEMO JSON and resource manifests | Included after review; no personal audio, speaker-level corpus or private receipt paths |
| Product screenshots and architecture/processing diagrams | Included for repository display with rights retained; separate English/Chinese documentation assets |
| Page 1 workspace documentation renders | Included; actual React component and desktop styles with renderer-compatible geometry; empty state, no invented results |
| Haruka WAVs and background video/poster | Excluded pending redistribution review; existing missing-resource behavior retained |
| node_modules, dist, build caches, environments and secrets | Excluded |
| JVS recordings, reference profiles, speaker-level data, manual annotations, personal recordings, model weights and private configuration/audits | Excluded |
| Original private Git history and V1 tag objects | Not imported |

The source-code license is defined in [LICENSE-SCOPE.md](../LICENSE-SCOPE.md). Documentation and display media do not inherit MIT. The reviewed frontend response JSON describes existing synthetic DEMOs; it is not a new learner dataset or acoustic accuracy certification.

The frontend comes from product commit `68effe8dc04e1cf10579c0ac2143288fa4f24eef`. Publication changes remove private receipt-path metadata, use an authored tone for structural tests, and mark four original-audio tests as optional. Accepted product application source is otherwise preserved. The private product and the deployed website are not changed by this publication.

The [file manifest](../TASK-021-PUBLIC-FILE-MANIFEST.md) records current staged content hashes. No Git LFS, submodule, deployment workflow or pretrained model is introduced.
