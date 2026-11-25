# Content Pipeline desktop - Milestone 04

A React/TypeScript/Vite/Tailwind presentation layer inside a Tauri 2 window. No Python
bridge, social API, authentication or processing integration.

## Run

From the repository root, using Node 24.12.0 / npm 11.6.2 (verified here):

```powershell
npm --prefix desktop ci
npm --prefix desktop run dev
npm --prefix desktop run typecheck
npm --prefix desktop run build
npm --prefix desktop run preview
```

Vite binds to 127.0.0.1; open its printed URL. Dependencies and dist are ignored.
The existing Python CLI is unchanged. No global packages are required.

## Visual direction — 02C

Orange (#F2A65A) is the primary interactive and decorative accent. Green (#39FF88)
is reserved as `--color-success` for genuine future success states; none are shown.
Near-black surfaces and warm-white text retain the portfolio palette. Brand.tsx
centralizes the temporary Content Pipeline name and a monochrome cut-frame SVG with
one orange diagonal cut. The icon uses a 32-unit viewBox and scales to 24px.

Studio's lightweight SVG shows an abstract source strip, stylized waveform, three
selected regions, a moving playhead and segments separating into clips. This is
static illustrative geometry, not footage, analysis, timestamps or progress. Its
screen-reader description identifies it as decorative; the compact runtime status
indicator describes the unconnected interface. No slogans or data claims are shown.

CSS-only animation loops while enabled. Hidden-page and
manual pause behavior are preserved. Reduced motion shows a static separated layout.
No rendering loop, 3D or new dependencies. Review retains its viewer/candidate/timeline
and disabled inspector; Exports retains an empty library and unconnected destination.

Inter, Space Mono and JetBrains Mono remain self-hosted via the existing Fontsource
packages. No font CDN requests. Colors and type tokens remain centralized.

## File selection boundary

Choose a video opens the browser's file picker. Only name, byte size and MIME type are
copied to volatile React state. Common video extensions are accepted when MIME is absent;
this is a picker convenience, not media validation. Files are not read/decoded, uploaded,
saved, ingested, analyzed or exported. Cancel keeps the previous selection; Clear removes
it. Selection survives screen switches, not a refresh. No localStorage or object URL is used.

## Verification and manual checks

Build and strict TypeScript checks must pass. Browser review covered Studio, Review
and Exports at 1440px desktop and 390px narrow layouts, keyboard navigation activation,
no horizontal overflow and manual motion pause. No full screen-reader audit or real
file-selection ingestion test is claimed. Reduced motion is enforced through CSS;
no functionality depends on movement. No production video/caches are needed for review.

Manual checklist: Tab to skip navigation and each rail item; activate with Enter;
check the visible focus outline; toggle Motion; enable OS reduced motion; resize the
window; select/cancel/clear a local video and verify only metadata appears. Test long
filenames and refresh. Existing source videos and output artifacts must remain untouched.

The native shell preserves the approved visual presentation. UI review is still required before
acceptance. Future media and backend work must use explicit contracts, never reinterpret
the decorative artwork or empty timelines as analysis.

## Native Windows development

Prerequisites: Node >=22.12, stable MSVC Rust, Microsoft C++ desktop build tools
and Windows SDK, and Edge WebView2 Runtime. Inspected here: Node 24.12.0,
npm 11.6.2, Rust/Cargo 1.100.0, Visual Studio Community 2026 C++ tools,
Windows SDK 10.0.26100.0 and WebView2 157.0.4341.60. No system dependencies are
installed by the project. Restart your terminal after installing Rust so Cargo
is on PATH. See https://v2.tauri.app/start/prerequisites/.

From the repository root:

```powershell
npm --prefix desktop ci
npm --prefix desktop run tauri -- dev
```

This starts Vite at 127.0.0.1:1420 and opens the native application automatically.
Port 1420 must be free; strict port selection prevents connecting to the wrong
server. The first run downloads Rust crates and compiles the shell. Close the
window and stop the command with Ctrl+C if needed; repeat the command to reopen.
The separate browser workflow (`npm --prefix desktop run dev`) is unchanged.

Checks from desktop/:

```powershell
npm run typecheck
npm run build
cargo check --locked --manifest-path src-tauri/Cargo.toml
npm run tauri -- build --debug --no-bundle
```

The last command builds a standalone debug executable with embedded frontend
assets under src-tauri/target/debug/. It does not create an installer.
Cargo.lock and package-lock.json pin dependency resolution; target/, gen/,
node_modules/ and dist/ are ignored.

### Window and security

Content Pipeline opens at 1440x900 logical pixels (minimum 800x600), resizable,
with standard Windows controls, dark theme and #0B0D10 initial background.
The native icon is derived from the approved cut-frame SVG in icons/source.svg.
No custom title bar, Python bridge, commands, plugins, updater, shell/filesystem
permissions or global Tauri JavaScript API are enabled. Capabilities are empty.
CSP limits production content to local assets; development additionally allows
Vite's local WebSocket and React refresh inline script. Inline styles remain
allowed for existing frontend rendering. Native file-drop interception is off;
the existing browser file picker remains metadata-only. WebView2 may create its
own local application profile; the app does not access production artifacts.

### Native manual review

Check Studio, Review and Exports, keyboard focus and skip navigation, Motion
pause, OS reduced-motion behavior, resize/minimum size, minimize/maximize,
close/reopen, and file-picker cancel/clear. Animation remains illustrative, and
all unavailable processing/export actions remain disabled. No installer,
backend processing or GPU integration is implemented.
Milestone 03 verification: TypeScript, Vite production build, cargo check, and
`tauri build --debug --no-bundle` passed. Both Tauri development mode and the
standalone embedded-asset executable launched and rendered Studio with the
native title bar and cut-frame icon. The separate browser dev server returned
HTTP 200 for the page and transformed React module. Native interaction automation
reported inconsistent window bounds (13x13 despite a full-size screenshot), so
Review/Exports activation, keyboard navigation, resize, close/reopen via window
controls, and OS reduced-motion testing remain manual checks. No runtime crash
was observed; a full WebView console audit has not been performed.

## Native stabilization (03B)

See [native-stabilization.md](docs/native-stabilization.md) for reproduced defects,
regression results and the still-required native acceptance checklist.

## Typed runtime bridge (04)

The header distinguishes Browser preview, Desktop ready (validated native response),
and Runtime unavailable (failed or malformed response). Hover or keyboard-focus the
status for version/OS/architecture and the explicit disconnected Python status.
See [runtime-bridge.md](docs/runtime-bridge.md) for the contract and verification.
Run `npm test` for lightweight bridge tests (verified with Node 24.12.0), and
`cargo test --locked --manifest-path src-tauri/Cargo.toml` for the Rust test.
