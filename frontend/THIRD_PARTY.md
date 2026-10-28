# Frontend third-party notices

Exact direct/transitive packages and integrity hashes are recorded in `package-lock.json`. Runtime dependencies are React and React DOM; no model, font or third-party source bundle is vendored.

| Package | Locked version | License |
| --- | --- | --- |
| react / react-dom | 19.3.0 | MIT |
| vite | 7.3.1 | MIT |
| @vitejs/plugin-react | 5.1.4 | MIT |
| typescript | 5.9.3 | Apache-2.0 |
| @types/react / @types/react-dom | 19.3.0 | MIT |

Installed package license files remain the authoritative notices for the installed distributions. Dependencies are installed through npm, not relicensed by the project source grant.

The original design work inspected local Web-Design-Kit, Lucide icon concepts, Motion (`f5838ce47b323ce2713cb2effc5afaa5b6120a44`, MIT), and React Bits (`4d6a46d3f401736695c495f1e72ed429e0ed1b93`, MIT with Commons Clause v1.0). No source, shader, icon path, media or component was copied or installed from those design references. The VoiceField/wave geometry and general SVG icons are authored product code. Motion and React Bits are not runtime dependencies.

Prettier and FFmpeg were historical development/capture tools, not frontend runtime dependencies or bundled executables. Fonts use operating-system fallbacks; no font files are distributed.

Haruka WAVs and decorative background video/poster remain excluded pending redistribution review. Saved synthetic-DEMO JSON and product screenshots retain their separately documented provenance and display boundaries; they are not personal recordings or an accuracy benchmark. See [root third-party sources](../THIRD_PARTY.md), [source license scope](../LICENSE-SCOPE.md) and [capture review](../docs/SCREENSHOT-REVIEW.md).
