# Product capture provenance and display scope

The owner explicitly requested the existing product DEMO visuals for the GitHub showcase on 2026-10-16. The original authorization covered static product presentation. On 2026-10-28 the owner additionally authorized the full frontend source and reviewed saved synthetic-DEMO response JSON. Underlying audio, private reference profiles and model resources remain separately governed. No new grant is asserted on behalf of a third-party resource owner.

## Published captures

| File | Source and visible state | Publication boundaries |
| --- | --- | --- |
| images/workspace-empty.jpg | Previously reviewed local empty workspace, captured 2026-10-09 | Retained historical display asset; no user recording or analysis content |
| images/demo-pitch.png | Actual ProsodyPanel rendered with the existing learner-v1-001 saved pYIN DEMO; both tracks visible in Hz | Haruka synthetic input and reference use the same WAV; no human-performance claim; no audio bytes or private JSON attached |
| images/demo-structure.png | Actual XRay component, target word selected; original waveform and candidate structure | No rewritten phone labels, manufactured intervals or substituted waveform |
| images/demo-reference.png | Actual ReferenceSketch component, median selected | Only the already-displayed aggregate statistical summary; no speaker-level records, raw corpus or histogram frequencies |
| images/demo-evidence.png | Actual Evidence component with candidate intervals and limitations | Displayed numeric values unchanged; no personal identity or private participant metadata |

The source interface is the local product at commit 68effe8dc04e1cf10579c0ac2143288fa4f24eef. The backend public baseline remains the accepted V1 export. The panels are rendered from the existing product React components in a private documentation capture workspace, using the saved DEMO. Visible UI labels are localized to English for documentation; Japanese practice text and model-native phone symbols remain unchanged. No English product release or independent acoustic validation is implied.

The new panels are static document renders, not live-browser screenshots: React static markup and the product CSS are rendered to a private PDF, then exported as PNG. Closed details remain closed; PDF-incompatible form widgets become static labels with equivalent styles, and waveform clipping uses an equivalent SVG clip path. Browser automation could not reliably identify the current URL and was stopped; no further browser control was attempted. The resulting PNGs were inspected locally. These rendering adjustments do not alter the underlying samples, measured values, intervals or model labels.

The saved source is Microsoft Haruka Desktop synthetic speech. Both curves use the same synthetic WAV; the source label must remain visible. JVS appears only as historical aggregate reference context, with the existing cross-sentence and boundary limitations. Resource/audio redistribution remains a separate review item in [THIRD_PARTY.md](../THIRD_PARTY.md).

These captures and documentation diagrams are display assets with rights retained, outside the MIT-covered code list. Private capture helpers, capture HTML, original WAVs and private review records are not added to the public repository. The later source publication includes the React implementation and only the reviewed frontend synthetic-DEMO response files, not the research archives. No account identity, personal recording or background-video frame is included.

## Page 1 workspace added on 2026-10-28

`images/workspace-page1.png` and `images/zh-CN/workspace-page1.png` are documentation renders of the actual `WorkspaceEmpty` React component exported from product commit `68effe8dc04e1cf10579c0ac2143288fa4f24eef`. They show the empty workspace, existing sidebar/DEMO navigation, upload/recording controls and three practice prompts. No completed recording, successful model response or user identity is invented.

The English image localizes visible labels for documentation only. The Chinese image retains the original labels. The renderer freezes desktop styles; PDF-incompatible controls/grid geometry use equivalent static presentation before PNG export. They are clearly described as documentation renders, not live-service screenshots. Private intermediate HTML/PDF and render scripts are not distributed. Existing pitch, structure, reference and evidence images are unchanged.
