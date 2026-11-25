# Typed runtime bridge — Milestone 04

`get_runtime_info` is a read-only, argument-free Tauri command. Its camelCase JSON:

```json
{
  "applicationVersion": "0.1.0",
  "operatingSystem": "windows",
  "cpuArchitecture": "x86_64",
  "nativeRuntimeAvailable": true
}
```

Version comes from Tauri package metadata; OS and architecture from Rust's target
constants. Availability means this native command executed, not that Python, GPU,
processing, or export services exist. No file or subprocess access occurs.

`src/runtime.ts` centralizes invoke, explicit response/status types, runtime shape
validation, browser detection, caught failures, and presentation. Browser mode never
invokes native commands. React starts with Checking runtime and updates only after
resolution; unmounted components ignore results. No polling or backend initialization.
The focusable status exposes details through a hover/focus tooltip.

## Permissions

The local main window gets only `allow-get-runtime-info`. Build-time AppManifest
registration generates the checked-in allow/deny permission definitions and enables
application-command ACL enforcement. No remote origins, plugins, shell or filesystem
permissions are granted. CSP permits `ipc:` and `http://ipc.localhost` for Tauri IPC.
The optional JS API is imported as a module, not exposed globally.

## Run and checks

From repository root:

```powershell
npm --prefix desktop run tauri -- dev
npm --prefix desktop test
npm --prefix desktop run build
cargo check --locked --manifest-path desktop/src-tauri/Cargo.toml
cargo test --locked --manifest-path desktop/src-tauri/Cargo.toml
npm --prefix desktop run tauri -- build --debug --no-bundle
```

Browser mode remains `npm --prefix desktop run dev`. Keep the development server
running while using development mode. The no-bundle build embeds frontend assets
and can run standalone; it creates no installer.

Verified locally: eight Node built-in tests and one Rust test pass; TypeScript,
Vite production build, locked Cargo check and native executable build pass.
The compiled Windows application displayed Desktop ready and actual values
0.1.0 / windows / x86_64. Studio -> Review -> Exports -> Studio navigation worked.
Browser development mode displayed Browser preview. Rejected invocation, malformed
responses and unavailable runtime behavior are tested through injected transports;
no deliberate native IPC failure was introduced into the application.

Manual review remains appropriate for screen-reader announcements, tooltip behavior
with Windows display scaling, and other OS/architecture targets. This is runtime
metadata only: no Python worker, video ingestion, analysis, or export connection.
