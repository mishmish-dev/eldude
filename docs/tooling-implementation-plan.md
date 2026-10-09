# Python project tooling implementation plan

**Spec:** [Tooling design](tooling-design.md), delivery stage 1.

**Goal:** Provide the `eldude` project workflow around the existing Python IR
frontend, preserving the distinction between static checking and fixture execution.

**Architecture:** Strict TOML project selection and a path-only resolver supply an
explicit module index to the existing frontend. The CLI reuses located diagnostics
and the source formatter. No new language syntax or dependencies are needed.

## Scope and constraints

- Keep existing compile/execute and formatter APIs compatible.
- Check libraries without invoking an entry or evaluating initializers.
- Respect package boundaries, direct imports, workspace ownership, and pins.
- Resolve and atomically lock the full owning graph; metadata and formatting never resolve it.
- Expose unsupported production hosts, native builds, remote sources, and complete
  canonical interfaces as implementation limits, not successful implementations.
- User scope clarification: also provide explicitly experimental Python
  build/run/test artifacts, with a separate Python host and isolated test processes.
- Work in the existing checkout and preserve pre-existing documentation edits.

## Tasks

- [x] Add library checking and explicit module discovery inputs in
  `source/pipeline.py`, `source/elaboration.py`, and `source/modules.py`.
  Verify no-main libraries, unused/generic errors, and nonexecuting initializers
  through source tests, plus the existing executable and rejection corpus.
- [x] Add `tooling/model.py` and temporary-project tests for strict manifests,
  versions, workspace selection, source discovery, and package boundaries.
- [x] Add `tooling/resolver.py` and tests for direct dependency environments,
  path constraints, cycles/origins, deterministic atomic locks, and locked/offline behavior.
- [x] Add `eldude` / `src/eldude/tooling/cli.py` for new/init, check, fmt, metadata,
  lock/update, clean, and explicit unsupported commands. Test source diagnostics,
  JSON events, target scope, safe creation, formatting preflight, and symlinks.
- [x] Update the implementation map and user commands, review the diff, and run
  all README checks. Record the supported stage and remaining capabilities.
- [x] Add a Python artifact backend and test exact built-input execution, failed
  rebuild behavior, profiles, runner isolation, exit handling, and reported artifacts.

## Review focus

Tests must cover test dependencies leaking into production, transitive imports,
unrelated broken modules during targeted checks, formatting across project pins,
and failed writes preserving existing files. Source checking remains whole-closure
checking; canonical interface caching and semantic invalidation are later stages.

## Verification

Use the README checks with `UV_CACHE_DIR=/tmp/eldude-uv-cache` because the default
uv cache is outside the writable sandbox. Run focused `unittest` files after each
task and the full suite and strict source corpus before completion.

Verified: 376 tests, all 84 positive source programs, documentation links/maps,
grammar publications, and whitespace checks. IR serialization additionally preserves
every corpus program's result and event trace. Review found and corrected workspace
ownership, symlink boundaries, hardlink formatting, artifact identity collisions,
JSON decoding order, and library artifact metadata regressions. The Python backend
retains the interpreter's runtime limits; native execution and semantic interface
caching are not implemented or claimed.
