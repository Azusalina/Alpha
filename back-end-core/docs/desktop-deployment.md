# Linux portable desktop deployment — 2026-10-02

Supported build target: Linux x86_64, glibc 2.34 or newer (the pinned PyNaCl
wheel sets this floor). The desktop also needs the host WebKitGTK 4.1/GTK and
related system libraries. This is a portable application directory, not a
fully static binary or a cross-platform installer.

## Reproducible build

Run from the repository root. Downloads require explicit network approval in
the restricted environment; the subsequent runtime build uses local assets only.
All output paths below must be new absolute paths. They are ephemeral examples,
not a durable asset cache. No Git command is required.

```sh
python3 scripts/release/download_assets.py --output /tmp/alpha-release-assets-20261002
python3 scripts/release/build_runtime.py --output /tmp/alpha-runtime-20261002 --archive /tmp/alpha-release-assets-20261002/python.tar.gz --requirements scripts/release/security-requirements.txt --wheelhouse /tmp/alpha-release-assets-20261002/wheels --licenses /tmp/alpha-release-assets-20261002/licenses
python3 scripts/release/acceptance.py --resources /tmp/alpha-runtime-20261002 --security
python3 scripts/release/build.py --output /tmp/alpha-portable-20261002 --archive /tmp/alpha-release-assets-20261002/python.tar.gz --wheelhouse /tmp/alpha-release-assets-20261002/wheels --licenses /tmp/alpha-release-assets-20261002/licenses
```

CPython 3.13.15, upstream license notices and security wheels are checked against
SHA-256 locks. Production dependencies are PyNaCl 1.6.2, cffi 2.1.1 and pycparser
3.0. Test-only jsonschema is not a production runtime dependency. Jieba files
are checked against `scripts/release/jieba-files.lock.json`, captured from the
current vendor tree. The historical commit recorded in `runtime.lock.json` is
provenance metadata; this no-Git build does not independently verify that commit.
Backend files are allowlisted and checked for changes during capture. The resource
manifest records file hashes, symlinks, modes and installed dependency versions.

The production Tauri build embeds the normal frontend and maps resources to
`brain-runtime/` using a directory map. The package contains `bin/alpha` and
`lib/Alpha/brain-runtime/`, plus `release.json` with executable and manifest hashes.
Packaging also produces a deterministically ordered `.tar.gz` archive with fixed
timestamps and ownership. Release resolution fails closed when resources are
missing; it does not fall back to checkout files or PATH Python. Explicit launch
overrides require both absolute `ALPHA_BRAIN_PYTHON` and `ALPHA_BRAIN_ROOT`.

For acceptance launches, set `ALPHA_BRAIN_DB` to a new absolute temporary SQLite
path. Production defaults to the application's local-data database; no migration
or copying of existing data is implicit. Never run these tests against private DBs.

## Native functional acceptance

This command needs GUI/process approval, even with a private Xvfb display:

```sh
python3 scripts/native/run.py --resources /tmp/alpha-runtime-20261002 --output /tmp/alpha-native-20261002 --cases real persistence fault-eof fault-invalid fault-timeout
```

The harness builds separate **instrumented acceptance binaries** from a temporary
frontend copy; it does not edit frontend source or ship instrumentation in the
production package. The test executes the actual native WebKitGTK frontend and
Rust IPC. XTest supplies one activation tap; actions thereafter use synthetic DOM
clicks and input events. Passing is native DOM functional acceptance, not full
pointer/keyboard interaction acceptance or physical GPU performance acceptance.
Xvfb is explicitly configured for software rendering.

The real case covers paging 50 → 100 → 137, rejected-source edit/delete cancellation,
edit clearing consent, review/fit, revoke/reagree and agreed-source deletion with
actual model-state checks. A second application process verifies persistence.
The harness also checks the real backend's `/proc` executable and working directory
against the relocated packaged runtime, with empty PATH and no source overrides.
Fault cases deliberately commit one synthetic submit, then lose its response via
EOF, malformed response or timeout; the UI must show the uncertainty and an
explicit read must recover exactly one source. Fixture method logs reject any
automatic write retry. Those cases use explicit test-only runtime overrides.

Every case uses a temporary synthetic DB. HOME is preserved; XDG data/config/cache
and TMPDIR are isolated. Native reports contain process outcomes and at most
4,000 characters of synthetic DOM text on failure; no screenshots are required.

## Evidence and handoff

- Release script unit tests: 3/3 passed on 2026-10-02; syntax checks passed.
- Relocated runtime acceptance: passed with empty PATH, API 30 methods, schema 1,
  contract revision 2, 137 unique records, F6 backend lifecycle, restart persistence,
  access lock/unlock and encrypted backup/restore into a fresh temporary target.
- Coordinator reported Rust offline library tests: 16/16 passed, including runtime
  paths, real Python host and ACL. This desktop worker did not duplicate that run.
- Coordinator reported real-backend browser tests: 6/6 passed after the additive
  API changes (2.9 minutes). These do not substitute for native or release checks.
- Coordinator reported final backend suite: 283 passed (100.985 seconds), translator
  suite: 7 passed. Only temporary test databases were in scope.
- Production release build passed. Its portable directory and fully extracted
  archive passed executable/resource manifest checks. Archive SHA-256:
  `e8b7c83d4d0f5f5964275b78f475a48b00b83370be7add09efce316d2f76ec2f`.
  Executable SHA-256:
  `3cddaf26687a4ced8cd1f13967a20ba0a1d3c2070135ff80d93a397e24798e58`.
- Historical first native attempt failed in added
  harness process inspection, not a recorded product assertion: Python can be a
  child of a Tokio worker thread. The harness now inspects all application tasks
  and stops processes before workspace cleanup. Rerun output:
  `/tmp/alpha-native-20261002-r2`.
- Rerun `real.json` and `persistence.json` passed: native paging and F6 lifecycle,
  then second-process persistence, with relocated backend executable/cwd checks.
  Rerun `fault-eof.json` failed at `entry-submit`: the form requires a selected
  partition, and the harness had left it unset. Startup failure and explicit UI
  reconnect passed, but fixture logs contain zero submit calls; this is not
  evidence for the post-commit EOF/no-retry path. The owned fault branch now
  explicitly selects `entry-partition-rational` and `entry-kind-philosophy` before
  filling text and submitting. These initial failures were harness failures, not
  product failures; the final main-verified three-case run below supersedes their status.
- Main verified EOF, invalid-response and timeout native DOM cases: command exit 0,
  summary passed=true and all three reports passed=true in
  `/tmp/alpha-native-faults-20261002`. Each verifies startup failure plus explicit
  reconnect, ambiguous submit plus explicit read recovering exactly one source,
  exactly one fixture submit and no_write_autoretry=true. Together with real and
  persistence, all five native DOM scenarios passed; this is not physical input/GPU
  or F13 unlock/cache UI acceptance.
- `cargo fmt --manifest-path src-tauri/Cargo.toml -- --check` passed after formatting
  only the owned `lib.rs` and `runtime_paths.rs`; concurrent frontend/fullscreen
  edits were preserved. The production artifact predates those concurrent frontend
  changes; the instrumented native build is separate. No unnecessary production
  rebuild was performed.

Main's final fault verification command (completed; no duplicate run needed):

```sh
python3 scripts/native/run.py --resources /tmp/alpha-runtime-20261002 --output /tmp/alpha-native-faults-20261002 --cases fault-eof fault-invalid fault-timeout
```

Historical interrupted escalation requests did not launch the proposed
`/tmp/alpha-native-20261002-faults-r3` run or create its output directory.

Verified artifacts available for independent inspection:

- Portable directory: `/tmp/alpha-portable-20261002`.
- Archive: `/tmp/alpha-portable-20261002.tar.gz`.
- Executable/manifest hashes: `/tmp/alpha-portable-20261002/release.json`.
- Packaged resource inventory:
  `/tmp/alpha-portable-20261002/lib/Alpha/brain-runtime/manifest.json`.
- Standalone runtime: `/tmp/alpha-runtime-20261002`.
- Native pass reports: `/tmp/alpha-native-20261002-r2/real.json` and
  `/tmp/alpha-native-20261002-r2/persistence.json`.
- Final native fault reports: `/tmp/alpha-native-faults-20261002/fault-eof.json`,
  `/tmp/alpha-native-faults-20261002/fault-invalid.json` and
  `/tmp/alpha-native-faults-20261002/fault-timeout.json`.

The coordinator independently repeated runtime acceptance with `--security` and
confirmed the documented archive/executable hashes and captured backend hashes.
The standalone runtime and production artifacts are complete; all three native DOM
fault cases passed. Administrative model-reset/reconnect, physical input/GPU and F13
UI acceptance remain pending. Temporary artifacts are not a durable deployment cache.

Frontend ownership handoff: `tests/backend.spec.ts:1852` still expects 23 methods;
the current API advertises 30, schema 1, contract revision 2. The frontend owner
must update that expectation. This worker does not edit frontend tests or `src/`.
The host trace operation whitelist already includes `review_version`,
`correction_reopen` and `replay_reopen`; filter tests reject password, payload,
corrections and text fields without expanding the permitted trace keys.

Separate worker tools are unavailable in this session. Security/model checks here
are read-only; backend business and legacy backend test repairs remain with their
owners. Hardware GPU acceptance and full physical input acceptance remain separate.

Build environment measured locally: tauri-cli 2.12.0, Tauri crate 2.11.5,
Wry 0.55.1, rustc/cargo 1.99.0, WebKitGTK 2.52.6 and GTK 3.24.52. Build output
reported Vite 7.3.6. Native result JSON additionally records its actual user agent.
