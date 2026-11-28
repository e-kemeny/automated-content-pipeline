# Milestone 07B: targeted UI stabilization

Changes are limited to desktop UI/bridge code; all preexisting Milestone 07 work
is preserved. No production engine, Rust lifecycle or dependency changes.

## Findings and fixes

- Source metadata contained literal mojibake in TSX, not corrupt FFprobe values.
  Corrected separators/ellipsis; source and export durations share `formatDuration`
  (`231.43 s`), byte sizes use MiB. Missing/invalid formatter values say Unavailable.
  Unicode source names are retained and long names wrap.
- Confirmed live-event target mismatch: Rust uses emit_to("main"), React used
  listen's default Any target. Installed Tauri 2.12.7 manager target filtering
  excludes Any listeners from AnyLabel emissions. Subscription now explicitly
  targets main. Revision ordering and subscribe-before-reconcile are unchanged.
  Actual stage text occupies its own sticky status row with indeterminate progress;
  no polling, percentage or estimates were introduced. Studio remains mounted
  across navigation.
- Review/Exports blankness was not reproduced in the initial native inspection.
  Earlier 03B correctly restricted decorative pause, and that restriction remains.
  Removed the remaining opacity-zero entrance animation from essential screen
  content as a defensive fix, not a claim of a reproduced WebView compositor bug.
  Both pages retain honest empty layouts; artifact integration is still out of scope.
- The selected-nav marker was positioned left:-10px, outside its button and at the
  clipped viewport edge. It is now inset. Workspace scrollbar gutters are balanced,
  long paths/names wrap, and processing controls wrap without added overflow hiding.
  The reported right-edge clipping was not independently reproduced, so its exact
  original cause remains unconfirmed. No native dimensions or decorations changed.

## Verification

84 desktop tests passed: Python 22, frontend 33 (four new), Rust 29. New tests cover
formatting, exact event target forwarding, live ordered processing snapshots and
source/CSS regression guards. The latter are static guards, not browser layout tests.
Existing real subprocess tests and mocked bridge tests passed. TypeScript, Vite
production build, locked Cargo check, native debug build and git diff --check passed.
The 900-test production suite was intentionally not rerun: no production code changed.

One actual standalone native Both-mode run used the existing ignored 80-second
synthetic source with Unicode/spaces. Metadata displayed `320 × 180 · 80.00 s ·
3.04 MiB`. Starting advanced to Exporting long-form without refocusing; Completed
reported six videos. Navigation through Review/Exports and back retained completion.
The fast run did not allow every intermediate stage to be visually captured.
Outputs are confined to the new owned job folder beneath output/desktop_smoke_v07.

Native restored, maximized and minimum 800x600-client layouts were exercised.
Source controls remained reachable by scrolling at minimum size, with visible
processing controls; Review/Exports rendered with decorative motion paused.
No clipped controls were observed. Other DPI/monitor combinations, OS reduced-motion
settings and the user's intermittent blank-page reproduction remain manual checks.
Nothing was staged, committed or pushed; the unusual untracked filename is untouched.
