# Native stabilization — Milestone 03B

Status: targeted fixes and native smoke checks passed; awaiting owner acceptance.
Base commit: 76610de. No React handlers, Tauri permissions, backend or dependencies changed.

## Findings and fixes

- Review/Exports: with Motion paused, the previous universal animation-pause rule
  froze the newly mounted `.screen-transition` at its starting opacity of zero.
  Browser reproduction showed heading `Review`, animation state `paused`, opacity
  `0`. Pause now affects only timeline clips/playhead. Repeated paused navigation
  reaches opacity `1`. This is a confirmed frontend defect, not proof that it
  explains every native navigation report.
- Importing a file only stores metadata. Empty Review/Exports are intentional;
  no candidates or exports are produced. The user's clarification described this
  expectation mismatch. No processing has been added to make those screens populate.
- Motion: animations previously ended after two 12-second cycles. Pause/resume
  could not restart a finished animation. They now loop while enabled; pause
  preserves position. Returning to Studio remounts the artwork at the start while
  preserving the user's motion preference. Hidden-page pause and reduced-motion
  overrides remain. Screen transitions are independent of decorative pause.
- Compact layout: the content-sized outer grid pushed Motion below the viewport
  (bottom 710px in a 600px viewport). The shell now fits the viewport and the main
  workspace scrolls independently. Studio/Exports stack at <=900px; inspector
  children may shrink and destination text wraps. After the change, Motion's bottom
  was 578px at 800x600. Native minimum-size testing now confirms all three layouts remain reachable
  without right-edge clipping. The original reported disappearance was not
  independently reproduced before the fix; do not claim a proven WebView2 bug.

The new independently scrolling workspace initially retained scroll when changing
screens. Native testing caught this; a layout effect now resets only workspace
scroll to the top before painting a new screen, preserving navigation focus.

No blocking overlay was identified in the inspected CSS; no evidence supports a
React/WebView2 event compatibility bug or missing Tauri permission. React state
changes work in the browser. Do not infer native acceptance from those results.

## Verification

Browser development regression checks (not native passes):
- Pause, navigate to Review/Exports, confirm visible content and completed transition.
- Return to Studio while paused: clips/playhead are paused; enable resumes movement.
- Repeat all three routes at 800x561, 1440x900 and 1920x1080: document and workspace
  have no horizontal overflow; Motion stays inside the viewport.
- Keyboard Enter activates Review; captured error/warning log is empty.

Native development mode launched and exposed Studio through WebView2 accessibility.
Native automation initially reported unavailable input geometry. The screenshot
list actually contained a tiny icon before the full window; selecting the full
window screenshot explicitly enabled native mouse input. Keyboard window sizing
via the standard system menu worked. The standalone app loaded embedded assets
from http://tauri.localhost/, with Vite stopped.

Verified in the native standalone app:
- Review and Exports rendered; repeated navigation and paused navigation remained visible.
- Artwork was static while paused and moved after resume; Studio reentry honored pause.
- Import opened the Windows file picker; Escape cancelled without selecting footage.
- Minimum 800x600 client size: Source, Inspector and Output location were reachable
  by scrolling, with persistent navigation/Motion and no observed right-edge clipping.
- Scrolling Studio then navigating to Review reset to the heading after the final fix.
- Maximize, minimize, Alt+F4 close and executable reopen worked.
- Tab/Enter activated Exports with a visible keyboard focus outline.

Build checks: TypeScript, Vite production build, locked Cargo check, native debug
build with embedded assets/no installer, and Git whitespace checks passed.
No new dependencies. No Python, video, cache, export or backend changes.

One initial build failed because a test instance held the executable open. Close
all Content Pipeline instances before rebuilding. A development executable loads
Vite and reports connection refused when Vite is stopped. For standalone testing,
rebuild with `npm run tauri -- build --debug --no-bundle` and then launch
`src-tauri/target/debug/content-pipeline-desktop.exe`. A later `tauri dev` rebuild
can replace that executable with the development variant. No installer is created.

## Native smoke-check record and owner review

From desktop/: `npm run tauri -- dev`.

| Check | Current status |
| --- | --- |
| Own Windows window | Passed: development and standalone |
| Studio rendering | Passed: development and standalone |
| Review navigation | Passed in native smoke check |
| Exports navigation | Passed in native smoke check |
| Timeline animation / pause | Passed in native smoke check |
| Import opens picker; cancel works | Passed in native smoke check |
| Resize: minimum size, maximized, reachable controls | Passed in native smoke check |
| Minimize / maximize / close | Passed in native smoke check |
| Reopen | Passed in native smoke check |

Test navigation repeatedly with Motion both on and off. Wait beyond 24 seconds,
pause/resume, leave/return to Studio, and enable OS reduced motion (static artwork
is expected). Use Tab/Enter and the skip link. At minimum size scroll the workspace
to reach the Source, Inspector and Output location panels. File import is
metadata-only; no actual footage or production artifacts are needed.

All nine categories were exercised successfully in native smoke testing, but owner
acceptance is still required. Remaining manual coverage: OS reduced-motion toggle,
other Windows DPI/scaling settings, screen reader audit and full WebView console
audit. No OS accessibility settings were changed during testing. The CSS reduced-
motion rules remain intact. Full interaction testing was on the standalone build;
development mode received launch/render verification, with browser regression tests
against its Vite server. No claim of exhaustive native compatibility is made.
