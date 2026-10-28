# Response examples

`api-v1-analysis-response.json` is an authored contract fixture. Its times, statistics and identifiers are not real measurements, speaker distributions or ground truth.

`api-v1-narabas-analysis-response.json` is a retained historical response for the existing Haruka synthetic input, used only by frontend schema/native-phone compatibility tests. Narabas remains research-only; this fixture does not activate it or establish accuracy. No input WAV, model or reference corpus is bundled. Current saved MFA/pYIN synthetic DEMO receipts are separately identified under `frontend/public/demo/`.

For fresh real pYIN execution without speech resources, `examples/prosody_smoke.py` generates an explicitly labeled 220 Hz engineering tone. Neither tones nor saved response examples validate learner pronunciation.
