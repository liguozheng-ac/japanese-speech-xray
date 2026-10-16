# Third-party sources and resource boundaries

Source identities and licenses were reviewed for TASK-021 on 2026-10-09; presentation scope was updated on 2026-10-16. Software source, bundled components, pretrained models, corpora and synthetic audio have distinct rights. The repository vendors none of their binaries or source. The limited MIT grant applies only to the 198 author-owned Python files enumerated in [LICENSE-SCOPE.md](LICENSE-SCOPE.md).

## Runtime dependencies

| Software | Actual version | License evidence | Use / distribution boundary |
| --- | --- | --- | --- |
| librosa | 1.0.0 | [official ISC](https://github.com/librosa/librosa/blob/3e4ff7bf5898ac5b326e7dee56463b4b325b91cb/LICENSE.md)；installed package license reviewed | pYIN / RMS dependency; installed, not vendored |
| NumPy | 2.5.3 | Installed BSD-3-Clause and bundled 0BSD / MIT / Zlib / CC0 notices | Numerical dependency; retain all bundled notices |
| SciPy | 1.18.1 | Installed BSD-3-Clause and bundled-component notices | Numerical dependency |
| Numba | 0.68.0 | Installed BSD-2-Clause and third-party notices | CPU numerical execution |
| llvmlite | 0.50.0 | BSD-2-Clause AND Apache-2.0 WITH LLVM-exception(installed package) | Do not reduce bundled components to one BSD notice |
| SoundFile | 0.14.0 | BSD-3-Clause(installed package) | Audio decoding |
| libsndfile | 1.2.2 | LGPL-2.1-or-later(conda-forge metadata) | Installed separately; DLL not redistributed |
| SudachiPy | 0.6.11 | [official Apache-2.0](https://github.com/WorksApplications/SudachiPy/blob/develop/LICENSE)；installed metadata | Japanese readings; branch documentation does not replace installed-version identity |
| SudachiDict-core | 20260116 | [official license](https://github.com/WorksApplications/SudachiDict/blob/develop/LICENSE-2.0.txt) and installed Apache-2.0 / notices | Dictionary obtained via package manager; binary excluded |
| FastAPI / Pydantic | 0.142.2 / 2.13.5 | Installed MIT | HTTP / data contracts |
| Starlette / Uvicorn / HTTPX | 1.7.0 / 0.54.0 / 0.28.1 | Installed BSD-3-Clause | HTTP engineering |
| python-multipart | 0.0.32 | Installed Apache-2.0 | Multipart upload |

Exact direct/transitive package metadata and official URLs are in [DEPENDENCY-LICENSES.md](docs/DEPENDENCY-LICENSES.md). Retain complete package copyright/NOTICE files. No complete numerical or MFA environment is redistributed. The historical MFA environment contains components such as GPL FFmpeg; it cannot be licensed wholesale as MIT.

The reviewed official librosa repository is librosa/librosa, commit 3e4ff7bf5898ac5b326e7dee56463b4b325b91cb. The project actually uses installed package versions, not a fabricated local Git HEAD for pip/Conda packages.

## Optional alignment and research sources

| Source | Recorded identity | Software license | Current inclusion |
| --- | --- | --- | --- |
| [MFA](https://github.com/MontrealCorpusTools/Montreal-Forced-Aligner) | 3.4.2 | [MIT](https://github.com/MontrealCorpusTools/Montreal-Forced-Aligner/blob/v3.4.2/LICENSE) | Author-owned CLI adapter; no MFA runtime bundle |
| [darashi/narabas](https://github.com/darashi/narabas) | b5e6511ce24dd2f14fc633ed5a23214225ca3eb7 | [Source MIT](https://github.com/darashi/narabas/blob/b5e6511ce24dd2f14fc633ed5a23214225ca3eb7/LICENSE) | Historical adapter, not production-activated; weights excluded |
| [m-bain/whisperX](https://github.com/m-bain/whisperX) | 771b4a14a9486f8fd5aef18ef49e35d639523dd3 | [BSD-2-Clause](https://github.com/m-bain/whisperX/blob/771b4a14a9486f8fd5aef18ef49e35d639523dd3/LICENSE) | Offline research source, not a default runtime dependency |
| [snakers4/silero-vad](https://github.com/snakers4/silero-vad) | 1e261b036686cd0017d500ee96acd1c4ba572a9d | [MIT](https://github.com/snakers4/silero-vad/blob/1e261b036686cd0017d500ee96acd1c4ba572a9d/LICENSE) | Offline research source, not a default runtime dependency |

## MFA pretrained resources

Michael McAuliffe / Morgan Sonderegger: Japanese MFA [acoustic model v3.0.0](https://mfa-models.readthedocs.io/en/latest/acoustic/Japanese/Japanese%20MFA%20acoustic%20model%20v3_0_0.html), [dictionary v3.0.0](https://mfa-models.readthedocs.io/en/latest/dictionary/Japanese/Japanese%20MFA%20dictionary%20v3_0_0.html), and [G2P v2.0.1a](https://mfa-models.readthedocs.io/en/latest/g2p/Japanese/Japanese%20MFA%20G2P%20model%20v2_0_1a.html). Official resource pages identify CC BY 4.0. This repository retains release/hash identities, not model files. Software licensing does not replace model licensing or attribution/modification obligations.

## JVS and Haruka

[JVS official corpus information](https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_corpus) distinguishes research/personal use, commercial use and redistribution. A repository/tag license does not automatically cover every recording. JVS WAVs, transcripts, speaker-level records and complete research profiles remain excluded.

Haruka is a Windows Desktop synthetic voice. [Microsoft SpeechSynthesizer documentation](https://learn.microsoft.com/en-us/uwp/api/windows.media.speechsynthesis.speechsynthesizer) and [system voice documentation](https://support.microsoft.com/en-us/accessibility/windows/narrator/appendix-a-supported-languages-and-voices) establish source identity, not a completed review of GitHub audio redistribution. Desktop WAV redistribution remains LICENSE_REVIEW_REQUIRED; Azure neural-TTS terms are not substituted. Haruka WAVs and private response files are not distributed.

The owner's 2026-10-16 request separately authorizes static product-demo presentation. The new panels show unchanged analytical visualizations from the existing synthetic DEMO and the already-displayed aggregate reference summary. This limited display does not assert a new third-party license, distribute the original audio or unlock private research data. All source labels and evidence limitations remain explicit; see [capture review](docs/SCREENSHOT-REVIEW.md).

## Product presentation rights

The React implementation and original background video remain private. New diagrams are authored documentation; the product captures are English-localized views of existing components with unchanged numeric results. Documentation, diagrams, branding and screenshots are outside the MIT code grant and are included only for repository display with rights retained. No generated concept image is presented as measured product output.
