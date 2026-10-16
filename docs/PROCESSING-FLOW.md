# End-to-end processing

![End-to-end processing](images/processing-flow.svg)

## Editable Mermaid

```mermaid
flowchart TD
  prompt["Select a controlled Japanese prompt"] --> input["Capture or upload audio"]
  input --> wav["Validate Mono PCM16 WAV / rate / duration / size"]
  wav --> asset["Session audio asset / original timeline"]
  asset --> local["Local waveform and manual selection"]
  local --> listen["Original / segment / loop playback"]
  asset --> pitchPost["Explicit prosody request"]
  pitchPost --> frames["pYIN F0 / timestamps / voicing evidence / RMS"]
  frames --> gate["Frame evidence and minimum-support gates"]
  gate --> curves["Hz or per-track relative semitones / preserve gaps"]
  synth["Optional same-sentence synthetic reference"] -.-> pitchPost
  asset --> xrayPost["Optional X-Ray submission / serial client queue"]
  xrayPost --> capacity["Resource validation and bounded server capacity"]
  capacity --> mfa["Isolated MFA alignment worker"]
  mfa --> mapping["TextGrid intervals / Japanese reading and Mora mapping"]
  mapping --> acoustic["Duration and acoustic evidence"]
  acoustic --> compare["Descriptive reference comparison and variant probe"]
  reference["Optional historical JVS reference profiles"] -.-> compare
  compare --> json["Typed evidence JSON or explicit failure / abstention"]
  json --> view["Experimental structure and evidence panels"]
  curves --> practice["Observe / compare / record again"]
  listen --> practice
  control["Stage polling and cancel control"] -.-> capacity
  control -.-> cleanup["Stop worker tree / clean workspace / release slot"]
```

## Input and time coordinates

Uploads preserve the accepted WAV bytes: no silent downmixing, resampling or fabricated header rates. Browser capture separately documents actual input channels and AudioContext processing rate; a supported stereo microphone input is explicitly averaged to mono and recorded as provenance. The upload path does not perform that conversion.

Local selection and playback remain on the original WAV timeline. F0 uses its own original-rate timestamps; synthetic and input tracks are not phoneme-aligned or time-stretched. Experimental Word / Mora / Phone intervals retain their candidate status.

## Request and cancellation semantics

The experimental analysis endpoint waits for one bounded calculation; it is not a durable distributed job queue. The browser polls real runtime stages. A cancel request uses the same per-analysis control token; CANCELLED is acknowledged only after worker termination, workspace cleanup and capacity release. Aborting a browser fetch alone is not proof that server-side computation stopped.

The independent prosody endpoint has a separate capacity lock. Its client-side abort does not promise immediate cancellation of an in-progress pYIN calculation. Missing references, insufficient voiced evidence, transport failure and experimental resource errors remain distinct outcomes.

## Data retention

The browser keeps session assets in memory and releases Object URLs. Prosody decodes the submitted WAV in memory and caches only the fixed synthetic reference, not learner audio; HTTP multipart spooling may still use an operating-system temporary file. Experimental analysis uses a random request workspace with cleanup by default; explicit debug retention changes that behavior. Public multi-user security has not been accepted for production.
