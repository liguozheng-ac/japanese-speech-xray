# Reproduction guide

Verified on Windows x64 / Python 3.13.15 in TASK-021, 2026-10-09 and 2026-10-10. External packages are obtained from official conda-forge and PyPI sources. The public checkout does not require copying the original product directory or private audio.

## 1. Exact environment and source installation

An independent prefix and the frozen HTTP dependencies were actually installed. An initial run without environment activation could not resolve libsndfile.dll; activate the environment or set the process-local PATH as shown below.

```powershell
conda create --prefix ./.venv --file environment-public-win-64.explicit.txt
conda activate "$PWD/.venv"
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps
python -m pip check
```

The recorded installation used an existing official package cache and the official pip registry. It did not reuse the original Python prefix or private configuration. URL/MD5 locks identify packages but do not guarantee that upstream downloads remain available indefinitely.

If the prefix already exists but the current PowerShell is not activated, this process-local alternative was also verified:

```powershell
$prefix = Join-Path $PWD '.venv'
$env:PATH = "$prefix;$prefix/Library/bin;$prefix/Scripts;$env:PATH"
& "$prefix/python.exe" -m pip check
& "$prefix/python.exe" scripts/run_tests.py
```

Tests and examples locate source relative to the checkout. Editable installation makes the package importable to uvicorn. The wheel contains Python modules and notices, not the prompt registry, full configuration, models or website; normal reproduction therefore uses the source checkout.

## 2. Engineering tests and actual F0 extraction

```powershell
python scripts/run_tests.py
python -m compileall -q services scripts tests examples
python examples/prosody_smoke.py
```

The example generates a two-second, 16 kHz Mono PCM16 220 Hz sine input with approximately 0.3 seconds of silence at each end. It is explicitly labeled ENGINEERING_TONE_NOT_HUMAN_SPEECH. The recorded run produced 100 frames, 75 accepted voiced frames and a median of approximately 220.64 Hz. It does not read private Haruka or JVS audio.

To inspect your own compatible, lawfully obtained WAV:

```powershell
python examples/prosody_smoke.py --audio ./my-input.wav --save-json ./my-curve.json
```

Each frame contains time_ms, f0_hz (possibly null), voiced, pyin_voiced, voiced_probability and rms_dbfs. The audio remains a local input; do not commit recordings or personal curves to the repository.

## 3. Start the local API

Use a clean shell without an old product configuration environment variable, or clear that obsolete setting first. Default configuration refers only to the current checkout.

```powershell
python -m uvicorn speech_xray.api.app:app --host 127.0.0.1 --port 8000
```

In another shell, activate the same environment, generate an engineering WAV under an ignored directory and call the API:

```powershell
New-Item -ItemType Directory -Force data/private/smoke | Out-Null
python examples/prosody_smoke.py --generate-wav data/private/smoke/engineering.wav
curl.exe http://127.0.0.1:8000/api/v1/health/live
curl.exe http://127.0.0.1:8000/api/v1/health/ready
curl.exe http://127.0.0.1:8000/api/v1/prompts
curl.exe -X POST http://127.0.0.1:8000/api/prosody/v1/curves -F "prompt_id=learner-v1-001" -F "audio=@data/private/smoke/engineering.wav;type=audio/wav"
```

These localhost URLs are API examples, not a hosted interactive demo.

| Check | Expected without optional resources |
| --- | --- |
| /api/v1/health/live | 200 / LIVE |
| /api/v1/prompts | 200 / three controlled prompts |
| /openapi.json | 200, including the independent prosody route |
| /api/v1/health/ready | 503 / NOT_READY, experimental alignment/reference resources missing |
| Engineering pitch POST | 200, learner AVAILABLE; reference null / SYNTHETIC_REFERENCE_UNAVAILABLE |
| Silence POST | 200, learner ABSTAINED / LOW_ENERGY_NO_F0 |
| Stereo or MP3 POST | 422, explicitly rejected |
| /api/v1/analyses | 503 / REFERENCE_ARTIFACT_MISSING; no fabricated result |

Input pitch WAV data is decoded in memory and is not added to the reference cache. The HTTP multipart parser may still use operating-system temporary spooling; this is not a guarantee that uploads never touch disk. Experimental alignment uses a temporary workspace owned by the orchestrator; debug_retention defaults to false.

## 4. Extraction parameters

Original PCM rate, no resampling; fmin=50 Hz, fmax=600 Hz; frame length is the next power of two at or above 80 ms, with an approximately 20 ms hop; center=true and constant padding; n_thresholds=100, beta=(2,18), resolution=0.1. Display gates require RMS > -60 dBFS and voiced probability >= 0.1; fewer than five supported frames yields abstention. The exact remaining parameters are returned by prosody/extract.py and remain consistent with the frozen implementation. These engineering gates are not human-accuracy calibration.

## 5. Optional experiment boundaries

MFA resources, reference profiles, Haruka audio, Narabas weights and actual corpora are not included; see [optional resources](OPTIONAL-RESOURCES.md). Offline tools can process separately obtained compatible data, but this documentation update does not rebuild a corpus or change resources. Private integration files were not deleted; public resource-dependent skips are skips, not passes.
