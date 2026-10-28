# Japanese Speech X-Ray frontend

The complete React / TypeScript / Vite interface: Page 0 product introduction and Page 1 continuous practice workspace. The source includes browser PCM recording, strict WAV admission, waveform selection and loop playback, pYIN result visualization, session/queue handling, cancellation, and the experimental X-Ray views.

## Run

Node.js >=22.12.0 and npm are required. From this repository root:

```powershell
cd frontend
npm ci
npm test
npm run typecheck
npm run build
npm run dev
```

Open http://127.0.0.1:5173/ or http://127.0.0.1:5173/#/workspace. `npm run preview` serves the production build on port 4173. The interface currently uses Chinese labels and Japanese practice text. Documentation renders may localize labels; an English product release is not implied.

In a second terminal, start the Python API using the root README. Vite forwards `/api` to `http://127.0.0.1:8000`. Recording, original-audio playback, waveform selection and looping work in the browser; automatic pitch needs the API. Experimental MFA additionally needs separately obtained, validated resources. The development proxy is not a production backend deployment.

## Optional display resources

- Haruka WAV files and `public/local-backgrounds/` are not distributed while their redistribution terms remain unresolved. The original static background is the existing video-failure fallback.
- `public/demo/` contains the three existing, synthetic-input service receipts, and the manifest retains their content hashes. No personal recordings, speaker-level reference records, private configuration or research archive is included. Saved results are not new inference or learner-validation evidence.
- The saved DEMO requires the exact original audio hashes. Without those WAVs it reports a load/validation error; it does not substitute a tone, a new voice or fabricated results. For a fresh clone, use the ordinary practice workspace with your own recording instead.
- Four exact-audio resource tests explicitly skip without the optional Haruka files. Structural tests use a generated, clearly identified engineering tone; no tone is substituted into a successful DEMO test.
- Product screenshots under `src/assets/` are display assets with rights retained, outside the MIT source-code grant. Their sources and capture-only styling are documented in `src/assets/PRODUCT-SCREENSHOTS.md`.

## Reproduction boundary

Application source is exported from local product commit `68effe8dc04e1cf10579c0ac2143288fa4f24eef`. Publication adjustments remove private receipt-path metadata and decouple tests from excluded audio. The accepted product directory and deployed website are unchanged. The contract generator uses `../data/contracts/` from the repository root; run it with `node scripts/generate-contract.mjs` from `frontend/`.

See [source license scope](../LICENSE-SCOPE.md), [third-party notices](THIRD_PARTY.md), and [verification receipts](../docs/VERIFICATION.md).
