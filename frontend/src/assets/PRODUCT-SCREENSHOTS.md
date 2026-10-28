# Page 0 product screenshots

Captured from the local product on 2026-10-09 at a 1920 × 1080 viewport.
Source UI baseline: `f03bb5daa84d88669577051c81d515747a3c5cd2`.
DEMO: `#/workspace?demo=learner-v1-001` (Haruka synthetic audio with saved MFA analysis).
The screenshots preserve the displayed measurements and evidence limitations.

| Asset | Actual product component | Captured state |
| --- | --- | --- |
| `demo-structure.jpg` | `.xray-structure` | Target word スマートフォン selected |
| `demo-prosody.jpg` | `.prosody-panel` | Real frequency (Hz); both saved DEMO and same-sentence Haruka curves visible |
| `demo-reference.jpg` | `.reference-sketch` | Reference median selected; speaker provenance visible |
| `demo-evidence.jpg` | `.evidence-notes` | Candidate timing, audition controls and evidence limitations |

`workspace-preview.png` shows the empty workspace with a gray plus and blue arrow,
as requested for Page 0. Its two composer guidance paragraphs are hidden for the
static promotional image. The blue arrow styling is capture-only; the real
workspace submission requirements and disabled states are unchanged.

Rollback baseline: `snapshot/before-real-product-screenshots`.

The prosody screenshot was added from UI commit
`7d3f406e6569f409007f464195b0c2c0a85cbefa`, with the unchanged DEMO data.
Rollback before adding the prosody section: `snapshot/before-landing-prosody`.
