# Known limitations

- Human-recording F0 can be sparse or incorrect. Accent correctness has not been independently calibrated; gaps do not automatically indicate a pause or pronunciation error.
- The product supports three controlled practice sentences. It is not an unrestricted ASR or open-sentence pronunciation diagnosis system.
- MFA CPU analysis can take minutes in the verified local environment. Models, runtime resources and private reference profiles are not bundled; the public checkout reports missing resources explicitly.
- Automatic Word / Mora / Phone intervals are experimental candidates. Duration values, medians and relative reference positions are not individual pass/fail criteria.
- Historical reference statistics, cross-sentence equivalence and automatic target boundaries retain unresolved validation limits. This update does not rebuild references or activate Narabas.
- Haruka Desktop WAV redistribution remains under review. Static product visualization is separately authorized for the repository; the audio and private research-response archives remain excluded. Reviewed synthetic-DEMO frontend JSON is included with its provenance.
- The saved DEMO uses one Haruka synthetic WAV as both input and same-sentence reference. Identical contours demonstrate the interface, not human performance or native-speaker accuracy.
- Engineering tests use tones, authored structural fixtures and adapters. Human acceptance covers product operation, not independently measured acoustic accuracy. Resource-dependent skips remain explicit.
- The exact public environment was verified on Windows x64 / Python 3.13.15. Other platforms and versions have not been accepted; the MFA adapter retains Windows tool assumptions.
- The code license covers the Python and complete frontend source files listed in LICENSE-SCOPE.md. Optional audio, model weights and private research records are not distributed. Documentation and display media are not licensed under that MIT grant.
- A frontend-only preview is hosted at https://liguozheng.com.cn/. The analysis backend is not deployed there. Authentication, global rate limiting, cross-user isolation and public-service operational controls have not been accepted for production.

Before deployment, verify HTTPS microphone capture, upload boundaries, server-side secrets, resource capacity, recording privacy and the rights for every resource actually served. The source release does not supply production authentication, backend hosting or third-party media redistribution rights.

- A fresh clone builds the complete frontend but does not include Haruka audio or decorative video. The saved audio-backed DEMO fails explicitly if its exact WAV is absent; ordinary recording/manual practice and the source screenshots remain available.
