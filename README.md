# Eldude

Eldude is a strict, statically typed functional language design with explicit ownership, effects, and structured concurrency. This repository contains its specification, grammar recognizer, experimental interpreter, example programs, and initial standard-library API. The interpreter implements a subset of the language.

**Start with the [documentation and project map](docs/index.md)** to find the rules, implementation files, and tests for your task. The [manifesto](docs/index.md#the-eldude-manifesto) explains the design goals.

## Quick start

The Python implementation uses only the standard library at runtime. Install [uv](https://docs.astral.sh/uv/getting-started/installation/); the project pins Python in [.python-version](.python-version).

Run from the repository root:

```sh
uv sync --locked
uv run eldude-run examples/07_source_pipeline/combined.eld
# 42
```

## Project CLI

The installed `eldude` command provides the project workflow from
[the tooling design](docs/tooling-design.md). `uv sync` installs the package from
`src/eldude/` and its commands into the pinned Python environment:

```sh
uv run eldude --help
uv run eldude new /tmp/hello --lib
uv run eldude check --manifest-path /tmp/hello/eldude.toml
uv run eldude fmt --manifest-path /tmp/hello/eldude.toml
uv run eldude metadata --manifest-path /tmp/hello/eldude.toml
uv run eldude check examples/09_tooling/application.eld
```

Commands discover the nearest `eldude.toml`, or accept `--manifest-path`.
Workspaces support `--package NAME` and `--workspace`, share a root lockfile, and
reject member toolchain overrides. Path dependencies are resolved by declared
package/module identities; transitive and test-only imports do not leak into
production modules. `lock` and `update` reconcile the path graph; `--locked`
forbids changing its deterministic TOML lock. `--offline` is accepted independently;
this path-only implementation never fetches remote sources.

`check` checks ordinary libraries without a `main` and never executes initializers.
Bare checking includes source and test modules; `--app`, `--embed`, or `--test`
selects a root's import closure. `check FILE.eld` checks an ordinary module without
host conformance. `metadata` reads local project state without creating a lock or
requiring the pin to match. `clean` removes only the owning project's `build/`.

### Experimental Python builds

`build`, `run`, and isolated executable tests support an explicit
`python::experimental` host. For example:

```toml
manifest-version = 1

[package]
name = "hello"
version = "0.1.0"

[[app]]
name = "hello"
entry = "hello::main"
host = "python::experimental"
```

With `src/main.eld` declaring `module hello; pub fn main() -> Int { 0 }`:

```sh
uv run eldude build --manifest-path /tmp/hello/eldude.toml
uv run eldude run --manifest-path /tmp/hello/eldude.toml
uv run eldude test --manifest-path /tmp/hello/eldude.toml --message-format=json
```

The Python host requires an exported, nongeneric, nullary `Int` function, closed
handler evidence, and a result from 0 through 255. That result becomes the process
exit status; other results and execution defects fail. Register tests with
`[[test]]`, `name`, `entry`, and `host` using the same convention. Each runner starts
in its package directory in a separate Python process. No registered runners
reports `No test targets selected` with zero executed tests.

Application artifacts are `.pyz` archives containing checked IR and the interpreter;
they execute without rereading source or recompiling. Libraries produce experimental
`.eldir.json` products. Paths are reported by builds, metadata, and JSON events under
`build/<machine-target>/<dev-or-release>/`. `--release` records a distinct profile
but currently uses the same interpreter. Immutable application artifact names prevent
concurrent builds from launching one another's output; a failed rebuild never runs
an old artifact.

`new` and `init` preserve the design's `cli::standard` application template. That
production host is not implemented: explicitly change its manifest host to
`python::experimental` to run with Python. Native builds, embeddings, cross targets,
an Eldude application-argument API, registry/Git resolution, complete canonical
interfaces, and semantic incremental caching remain unsupported. Checking still
checks imported source closures, and resources/I/O retain the fixture limitations.
See the [implementation guide](docs/implementation.md#project-tooling) for boundaries.

## Format source

The [semantic source formatter](docs/formatter.md) uses the normative grammar to
format blocks, signatures, rows, and expressions. It preserves comments, literal
spelling, contracts, and evaluation order, including code outside the interpreter's
supported subset. It does not require imports to resolve or type checking to pass.

```sh
uv run eldude-format examples/08_formatting/semantics.eld
uv run eldude-format --check path/to/file.eld
uv run eldude-format --write path/to/file.eld
```

Without flags it prints one formatted file to stdout; omit the filename or use `-`
to read stdin. `--check` and `--write` accept multiple files. Check mode exits 1 for
formatting differences; errors exit 2. Write mode validates all inputs before
editing, replaces changed files atomically, and refuses symlinks.

The project CLI reuses this formatter: `eldude fmt` writes the selected packages'
source/test files, `fmt --check` checks them, and `fmt --diff` prints changes without
writing. Explicit files/directories and sole stdin input `fmt -` also work without
a manifest. No-argument formatting requires a project. All selected inputs and
toolchain pins are validated before writing; each replacement preserves permissions
and checks for concurrent edits. The standalone `eldude-format` command keeps its stdout default.

## Checks

These maintenance commands and `eldude-run --examples` require a repository
checkout. Installed wheels include the grammar and standard library for running,
checking, formatting, and building user programs.

```sh
uv run python -m eldude.check_docs
uv run python -m eldude.check_grammar
uv run python -m unittest discover -s tests -p 'test_*.py'
uv run eldude-run --examples --strict
git diff --check
```

The documentation check verifies local links and fragment anchors, chapter/code map coverage, and example tables against [manifest.json](examples/manifest.json). The grammar check verifies syntax and generated publications. The tests check static diagnostics and execution; the strict corpus run executes every positive example. See the [example guide](examples/README.md) for expected values and rejection fixtures.

After editing [eldude.ebnf](docs/eldude.ebnf) or the originating parsing/interface clauses, regenerate the Markdown and JSON grammar publications with `uv run python -m eldude.check_grammar --write`. The [editing guide](docs/index.md#editing-and-checking) identifies the source files.

## Source-to-execution experiment

The [implementation guide](docs/implementation.md#source-to-execution-experiment) describes supported source forms, entry-point conventions, diagnostics, and remaining limits. The [file map](docs/implementation.md#file-map) connects each compiler component to its tests. Resources are simulated; execution uses a bounded cooperative scheduler.

## Inference experiment

The [inference guide](docs/implementation.md#inference-experiment) covers annotated expression checking, effect rows, ownership, captures, and its conservative boundaries.

## Handler and resumption experiment

The [handler guide](docs/implementation.md#handler-and-resumption-experiment) covers clause checking, explicit evidence, resumption, forwarding, and the interpreter API.
