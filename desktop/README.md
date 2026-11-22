# Content Pipeline desktop - Milestone 02C

An isolated React/TypeScript/Vite/Tailwind presentation layer. No Tauri, Python
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
screen-reader description identifies it as decorative; the single Preview mode
indicator describes the unconnected interface. No slogans or data claims are shown.

CSS-only animation runs twice and settles into separated clips. Hidden-page and
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
check the green focus outline; toggle Motion; enable OS reduced motion; resize the
window; select/cancel/clear a local video and verify only metadata appears. Test long
filenames and refresh. Existing source videos and output artifacts must remain untouched.

This milestone changes visual presentation only. UI review is still required before
acceptance. Future media and backend work must use explicit contracts, never reinterpret
the decorative artwork or empty timelines as analysis.
